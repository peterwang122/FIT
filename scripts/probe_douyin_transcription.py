"""Transcribe an already obtained video locally without touching FIT data."""

import argparse
import importlib.metadata
import json
from datetime import datetime
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path)
    parser.add_argument("--source-url", required=True)
    parser.add_argument("--source-date", required=True)
    parser.add_argument("--expected-duration", type=float, required=True)
    parser.add_argument("--model", default="small")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    datetime.strptime(args.source_date, "%Y-%m-%d")
    if not args.video.is_file():
        parser.error("The video file does not exist")

    import av
    from faster_whisper import WhisperModel

    with av.open(str(args.video)) as media:
        if not media.streams.audio:
            raise ValueError("The video has no audio stream")
        if media.duration is None:
            raise ValueError("The video duration cannot be verified")
        duration = media.duration / av.time_base
    if abs(duration - args.expected_duration) > 2:
        raise ValueError("The downloaded duration differs from the source video")

    # Keep the probe small enough to coexist with the production collectors.
    model = WhisperModel(
        args.model, device="cpu", compute_type="int8", cpu_threads=2, num_workers=1
    )
    segments, info = model.transcribe(
        str(args.video),
        language="zh",
        beam_size=5,
        temperature=0,
        vad_filter=True,
        initial_prompt="\u4e2d\u4fe1\u3001\u56fd\u6cf0\u3001\u4e0a\u8bc150\u3001\u6caa\u6df1300\u3001\u4e2d\u8bc1500\u3001\u4e2d\u8bc11000\u3001\u60c5\u7eea\u6307\u6807\u3002",
        hotwords="\u4e0a\u8bc1\u4e94\u5341 \u6caa\u6df1\u4e09\u767e \u4e2d\u8bc1\u4e94\u767e \u4e2d\u8bc1\u4e00\u5343 \u6050\u8d2a\u6570\u503c",
    )
    rows = [
        {"start": segment.start, "end": segment.end, "text": segment.text.strip()}
        for segment in segments
        if segment.text.strip()
    ]
    transcript = "\n".join(row["text"] for row in rows)
    if not transcript:
        raise ValueError("The transcription is empty")

    result = {
        "source_url": args.source_url,
        "source_date": args.source_date,
        "duration_seconds": duration,
        "engine": "faster-whisper",
        "engine_version": importlib.metadata.version("faster-whisper"),
        "model": args.model,
        "compute_type": "int8",
        "language": info.language,
        "segments": rows,
        "text": transcript,
        "requires_numeric_verification": True,
        "production_data_written": False,
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    stem = args.output_dir / f"liwei-{args.source_date}-local-asr"
    stem.with_suffix(".json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    stem.with_suffix(".txt").write_text(transcript + "\n", encoding="utf-8")
    print(json.dumps({"output": str(stem), "characters": len(transcript), "segments": len(rows), "duration_seconds": duration}, ensure_ascii=False))


if __name__ == "__main__":
    main()
