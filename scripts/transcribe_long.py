"""Transcribe a long recording in independently resumable blocks."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import subprocess
import tempfile
from time import monotonic
from types import SimpleNamespace
import wave

import numpy as np

from localcaption.backends.faster_whisper import _to_srt, require_faster_whisper


def write_json(path, data):
    partial = path.with_suffix(".tmp")
    partial.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    partial.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audio", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", choices=("small", "medium", "large-v3-turbo"), default="small")
    parser.add_argument("--block-seconds", type=int, default=1800)
    parser.add_argument("--max-blocks", type=int, default=0, help="0 processes all remaining blocks")
    parser.add_argument("--budget-minutes", type=int, default=285)
    args = parser.parse_args()
    if args.block_seconds < 1 or args.max_blocks < 0 or args.budget_minutes < 1:
        parser.error("Invalid block size, block limit, or time budget")

    duration = float(subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(args.audio),
    ], text=True).strip())
    if not math.isfinite(duration) or duration <= 0:
        parser.error("The recording must have a positive, finite duration")
    with args.audio.open("rb") as audio:
        digest = hashlib.file_digest(audio, "sha256").hexdigest()
    parts = args.output / "blocks"
    parts.mkdir(parents=True, exist_ok=True)
    manifest = args.output / "manifest.json"
    settings = {
        "version": 2, "source_sha256": digest, "model": args.model,
        "language": "pt", "block_seconds": args.block_seconds,
    }
    if manifest.exists():
        saved = json.loads(manifest.read_text(encoding="utf-8"))
        if saved.get("version") not in (1, 2) or {**saved, "version": 2} != settings:
            parser.error("The checkpoint belongs to a different audio file or model")
    elif any(parts.glob("*.json")):
        parser.error("The checkpoint is missing its manifest")
    write_json(manifest, settings)

    total = math.ceil(duration / args.block_seconds)
    paths = [parts / f"{index + 1:05d}.json" for index in range(total)]
    blocks = {
        path: json.loads(path.read_text(encoding="utf-8"))
        for path in paths if path.exists()
    }
    # Older artifacts have segment times only. Regenerate those blocks when resumed.
    pending = [
        (index, path) for index, path in enumerate(paths)
        if path not in blocks or any("words" not in row for row in blocks[path])
    ]
    started = monotonic()
    if pending:
        model = require_faster_whisper()(args.model, device="cpu", compute_type="int8")
        for index, path in pending[:args.max_blocks or len(pending)]:
            if monotonic() - started >= args.budget_minutes * 60:
                print("Time budget reached. Resume in a new run.", flush=True)
                break
            offset = index * args.block_seconds
            length = min(args.block_seconds, duration - offset)
            block_started = monotonic()
            with tempfile.TemporaryDirectory() as temp:
                wav = Path(temp) / "block.wav"
                subprocess.run([
                    "ffmpeg", "-nostdin", "-v", "error", "-ss", str(offset),
                    "-i", str(args.audio), "-t", str(length), "-map", "0:a:0",
                    "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", str(wav),
                ], check=True)
                with wave.open(str(wav), "rb") as decoded:
                    samples = np.frombuffer(decoded.readframes(decoded.getnframes()), dtype="<i2")
                pcm = samples.astype(np.float32) / 32768
                segments, _ = model.transcribe(
                    pcm, language="pt", vad_filter=True, word_timestamps=True
                )
                rows = [
                    {
                        "start": offset + segment.start,
                        "end": offset + segment.end,
                        "text": segment.text,
                        "words": [
                            {
                                "word": word.word,
                                "start": offset + word.start,
                                "end": offset + word.end,
                            }
                            for word in (segment.words or [])
                        ],
                    }
                    for segment in segments
                ]
            write_json(path, rows)
            blocks[path] = rows
            print(f"Block {index + 1}/{total}: {monotonic() - block_started:.1f}s", flush=True)

    complete = sum(path in blocks and all("words" in row for row in blocks[path]) for path in paths)
    print(f"Completed blocks: {complete}/{total}", flush=True)
    if complete < total:
        return
    rows = [row for path in paths for row in blocks[path]]
    write_json(args.output / "palavras.json", {"version": 1, "language": "pt", "segments": rows})
    segments = [SimpleNamespace(**row) for row in rows]
    (args.output / "transcricao.srt").write_text(_to_srt(segments), encoding="utf-8")
    (args.output / "transcricao.txt").write_text(
        "\n".join(segment.text.strip() for segment in segments) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
