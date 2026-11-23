"""MCP control plane for the LocalCaption workflow. Audio processing stays on GitHub."""

from io import BytesIO
import logging
import os
from time import sleep
from typing import Literal
from urllib.parse import urlsplit
from zipfile import ZipFile

from cryptography.fernet import Fernet
import httpx
from mcp.server.fastmcp import FastMCP


mcp = FastMCP("LocalCaption")
logging.getLogger("httpx").setLevel(logging.WARNING)
REPOSITORY = "vini-ronin/LocalCaption"
WORKFLOW = "transcrever-audio.yml"
MAX_DOWNLOAD = 20 * 1024 * 1024


def github():
    token = os.environ.get("LOCALCAPTION_GITHUB_TOKEN")
    if not token:
        raise ValueError("Configure LOCALCAPTION_GITHUB_TOKEN com acesso de escrita a Actions.")
    return httpx.Client(
        base_url=f"https://api.github.com/repos/{REPOSITORY}/",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2026-03-10",
        },
        timeout=30,
    )


def checked(response):
    if not response.is_success:
        status = response.status_code
        if status == 404:
            raise ValueError("GitHub retornou 404. Confira o ID, o acesso ao repositório e o workflow na main.")
        raise ValueError(f"GitHub retornou HTTP {status}. Confira as permissões e os parâmetros.")
    return response.json()


def transcription_run(client, run_id):
    url = f"actions/runs/{run_id}"
    response = client.get(url)
    # GitHub may return a run ID just before the run is visible to reads.
    for delay in (1, 2, 4):
        if response.status_code != 404:
            break
        sleep(delay)
        response = client.get(url)
    run = checked(response)
    if run["path"].split("@", 1)[0] != f".github/workflows/{WORKFLOW}":
        raise ValueError("O ID informado não pertence ao workflow de transcrição.")
    return run


def artifacts_for(client, run_id):
    response = checked(client.get(f"actions/runs/{run_id}/artifacts", params={"per_page": 100}))
    return {artifact["name"]: artifact for artifact in response["artifacts"] if not artifact["expired"]}


@mcp.tool(structured_output=True)
def iniciar_transcricao(
    audio_url: str = "",
    model: Literal["small", "medium", "large-v3-turbo"] = "small",
    max_blocks: int = 0,
    resume_run_id: int | None = None,
) -> dict[str, str | int | bool | None]:
    """Start a Portuguese transcription on GitHub and return its run ID. Pass a YouTube video URL or a direct HTTPS download URL or leave it empty to use the repository's STT_AUDIO_URL. For a benchmark, set max_blocks to 1. To resume, supply the prior run ID, same source and model."""
    if max_blocks < 0 or (resume_run_id is not None and resume_run_id < 1):
        raise ValueError("max_blocks deve ser >= 0 e resume_run_id deve ser positivo.")
    inputs = {"model": model, "max_blocks": str(max_blocks)}
    if audio_url:
        url = urlsplit(audio_url)
        if url.scheme != "https" or not url.hostname or url.username or url.password:
            raise ValueError("Use um link HTTPS de download direto, sem credenciais no endereço do host.")
        key = os.environ.get("STT_INPUT_KEY")
        if not key:
            raise ValueError("Configure STT_INPUT_KEY no MCP e no GitHub para enviar links.")
        inputs["encrypted_source"] = Fernet(key.encode("ascii")).encrypt(
            audio_url.encode("utf-8")
        ).decode("ascii")
    with github() as client:
        if resume_run_id is not None:
            transcription_run(client, resume_run_id)
            if "blocos-stt" not in artifacts_for(client, resume_run_id):
                raise ValueError("A execução anterior não tem blocos disponíveis para retomada.")
            inputs["resume_run_id"] = str(resume_run_id)
        result = checked(client.post(
            f"actions/workflows/{WORKFLOW}/dispatches",
            json={"ref": "main", "inputs": inputs},
        ))
    run_id = result["workflow_run_id"]
    return {"run_id": run_id, "url": f"https://github.com/{REPOSITORY}/actions/runs/{run_id}"}


@mcp.tool(structured_output=True)
def consultar_transcricao(run_id: int) -> dict[str, str | int | bool | None]:
    """Check whether the transcription is queued, running, incomplete or ready. A completed run without the transcricao artifact can be resumed if blocos-stt is available."""
    with github() as client:
        run = transcription_run(client, run_id)
        artifacts = artifacts_for(client, run_id) if run["status"] == "completed" else {}
    ready = "transcricao" in artifacts
    return {
        "run_id": run_id,
        "status": run["status"],
        "conclusion": run["conclusion"],
        "result_ready": ready,
        "can_resume": run["status"] == "completed" and not ready and "blocos-stt" in artifacts,
        "url": run["html_url"],
    }


@mcp.tool(structured_output=True)
def ler_transcricao(
    run_id: int, formato: Literal["txt", "srt"] = "txt", inicio: int = 0, limite: int = 100
) -> dict[str, str | int | bool | None]:
    """Read a page of TXT or SRT lines from a completed transcription. To read the next page use proximo_inicio. The returned GitHub URL also lets the user download the original artifact."""
    if inicio < 0 or not 1 <= limite <= 200:
        raise ValueError("Use inicio >= 0 e limite entre 1 e 200.")
    with github() as client:
        run = transcription_run(client, run_id)
        artifact = artifacts_for(client, run_id).get("transcricao")
        if not artifact:
            raise ValueError("A transcrição final não está disponível. Consulte o status da execução.")
        response = client.get(f"actions/artifacts/{artifact['id']}/zip")
    if response.status_code != 302:
        raise ValueError(f"GitHub não disponibilizou o ZIP (HTTP {response.status_code}).")
    # The redirect contains a signed URL and needs no GitHub credentials.
    download_url = response.headers.get("location", "")
    if urlsplit(download_url).scheme != "https":
        raise ValueError("GitHub não forneceu um endereço HTTPS para o ZIP.")
    data = bytearray()
    try:
        with httpx.stream("GET", download_url, timeout=60) as download:
            if not download.is_success:
                raise ValueError("Não consegui baixar o ZIP da transcrição.")
            for chunk in download.iter_bytes():
                data.extend(chunk)
                if len(data) > MAX_DOWNLOAD:
                    raise ValueError("O ZIP excede o limite do MCP. Baixe-o pelo GitHub.")
    except httpx.RequestError:
        raise ValueError("Falha de rede ao baixar a transcri??o. Tente novamente.") from None
    with ZipFile(BytesIO(data)) as archive:
        member = archive.getinfo(f"transcricao.{formato}")
        if member.file_size > MAX_DOWNLOAD:
            raise ValueError("A transcrição excede o limite do MCP. Baixe-a pelo GitHub.")
        lines = archive.read(member).decode("utf-8").splitlines()
    stop = min(inicio + limite, len(lines))
    return {
        "conteudo": "\n".join(lines[inicio:stop]),
        "total_linhas": len(lines),
        "proximo_inicio": stop if stop < len(lines) else None,
        "url": f"{run['html_url']}/artifacts/{artifact['id']}",
    }


if __name__ == "__main__":
    mcp.run(transport="stdio")
