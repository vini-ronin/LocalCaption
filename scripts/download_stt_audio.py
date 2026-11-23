"""Fetch media in the runner without exposing URLs or credentials in logs."""

import os
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import parse_qs, urlsplit


def youtube_id(url):
    if url.hostname == "youtu.be":
        candidate = url.path.strip("/")
    elif url.hostname in {"youtube.com", "www.youtube.com", "m.youtube.com"}:
        if url.path == "/watch":
            candidate = parse_qs(url.query).get("v", [""])[0]
        else:
            match = re.fullmatch(r"/(?:shorts|live|embed)/([^/]+)/?", url.path)
            candidate = match[1] if match else ""
    else:
        return None
    if not re.fullmatch(r"[A-Za-z0-9_-]{11}", candidate):
        sys.exit("Use o link de um vídeo do YouTube.")
    return candidate


def download_youtube(video_id, output):
    print("Obtendo o áudio do YouTube no runner.", flush=True)
    try:
        result = subprocess.run([
            sys.executable, "-m", "yt_dlp", "--ignore-config", "--no-playlist",
            "--no-progress", "--socket-timeout", "20", "--retries", "1",
            "--fragment-retries", "1", "-f", "bestaudio[protocol=https]",
            "-o", output, "--", f"https://www.youtube.com/watch?v={video_id}",
        ], capture_output=True, text=True, timeout=1200)
    except subprocess.TimeoutExpired:
        sys.exit("O download do YouTube excedeu 20 minutos.")
    if result.returncode or not Path(output).is_file():
        log = (result.stderr + result.stdout).lower()
        if re.search(r"not a bot|sign in|login required", log):
            sys.exit("O YouTube exigiu login ou verificação no runner. Use um link direto do arquivo.")
        status = re.search(r"http error ([1-5]\d\d)", log)
        if status:
            sys.exit(f"O YouTube recusou o download no runner (HTTP {status[1]}). Use um link direto do arquivo.")
        if "requested format is not available" in log:
            sys.exit("O YouTube não disponibilizou uma faixa de áudio direta para o runner.")
        sys.exit("O runner não conseguiu obter o áudio do YouTube. Use um link direto do arquivo.")


def download_https(source, output):
    result = subprocess.run([
        "curl", "--fail", "--silent", "--location", "--proto", "=https",
        "--proto-redir", "=https", "--connect-timeout", "30", "--max-time", "1200",
        "--write-out", "%{http_code}", "--output", output, "--", source,
    ], capture_output=True, text=True)
    if result.returncode:
        status = result.stdout.strip()
        detail = f"HTTP {status}" if re.fullmatch(r"[1-5]\d\d", status) else f"curl {result.returncode}"
        sys.exit(f"Falha no download do áudio ({detail}). Confira o acesso e a validade do link.")


def main():
    source = os.environ.get("AUDIO_URL", "")
    encrypted = os.environ.get("ENCRYPTED_SOURCE", "")
    if encrypted:
        from cryptography.fernet import Fernet, InvalidToken

        try:
            key = os.environ["STT_INPUT_KEY"].encode("ascii")
            source = Fernet(key).decrypt(encrypted.encode("ascii")).decode("utf-8")
        except (ValueError, InvalidToken):
            sys.exit("Não consegui abrir a fonte. Confira se a chave do MCP e do GitHub é a mesma.")
    try:
        url = urlsplit(source)
        valid = url.scheme == "https" and url.hostname and not url.username and not url.password
    except ValueError:
        valid = False
    if not valid:
        sys.exit("Configure um link HTTPS de áudio ou de um vídeo do YouTube.")
    video_id = youtube_id(url)
    if video_id:
        download_youtube(video_id, sys.argv[1])
    else:
        download_https(source, sys.argv[1])


if __name__ == "__main__":
    main()
