"""Fetch the audio without exposing signed URLs in Actions logs."""

import os
import subprocess
import sys
from urllib.parse import urlsplit


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
        sys.exit("Configure um link HTTPS de download direto no MCP ou em STT_AUDIO_URL.")
    result = subprocess.run([
        "curl", "--fail", "--silent", "--location", "--proto", "=https",
        "--proto-redir", "=https", "--connect-timeout", "30", "--max-time", "1200",
        "--output", sys.argv[1], "--", source,
    ])
    if result.returncode:
        sys.exit(f"Falha no download do áudio (curl {result.returncode}). Confira a validade do link.")


if __name__ == "__main__":
    main()
