#!/usr/bin/env python3
"""Convert every video on a YouTube channel (or playlist / single video) into
plain-text transcripts and one combined context file.

Strategy (per video):
  1. Try to pull existing captions (manual subtitles first, then auto-generated)
     in the preferred languages using yt-dlp.
  2. If no captions exist and --whisper is enabled, download the audio and
     transcribe it locally with openai-whisper.

Outputs:
  <out>/<NNN>_<slug>.txt   one plain-text transcript per video
  <out>/<combined>         all transcripts concatenated with headers (context)
  <out>/index.json         machine-readable manifest of what was produced

Requires: yt-dlp (pip install yt-dlp). Whisper fallback additionally needs
          openai-whisper + ffmpeg.

This script must run in an environment with network access to YouTube.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path


def eprint(*args: object) -> None:
    print(*args, file=sys.stderr, flush=True)


def check_yt_dlp() -> None:
    try:
        subprocess.run(["yt-dlp", "--version"], capture_output=True, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        eprint("ERROR: yt-dlp not found. Install it with:  pip install -U yt-dlp")
        sys.exit(1)


def slugify(text: str, max_len: int = 60) -> str:
    text = re.sub(r"\s+", "_", text.strip())
    # Keep unicode letters/digits (so Japanese titles stay readable), drop the rest.
    text = re.sub(r"[^\w\-]", "", text, flags=re.UNICODE)
    return (text[:max_len] or "untitled")


def list_videos(url: str, limit: int | None) -> list[dict]:
    """Return [{id, title, url}, ...] for every video reachable from url."""
    cmd = ["yt-dlp", "--flat-playlist", "--ignore-errors", "-J", url]
    if limit:
        cmd[1:1] = ["-I", f"1:{limit}"]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if not proc.stdout.strip():
        eprint("ERROR: could not list videos.")
        eprint(proc.stderr.strip()[-1000:])
        sys.exit(1)
    data = json.loads(proc.stdout)
    entries = data.get("entries")
    if entries is None:  # single video URL
        entries = [data]
    videos: list[dict] = []
    for e in entries:
        if not e:
            continue
        vid = e.get("id")
        if not vid:
            continue
        videos.append(
            {
                "id": vid,
                "title": e.get("title") or vid,
                "url": e.get("url") or f"https://www.youtube.com/watch?v={vid}",
            }
        )
    return videos


# --- VTT -> plain text -------------------------------------------------------
_TS_LINE = re.compile(r"\d{2}:\d{2}:\d{2}[.,]\d{3}\s*-->")
_TAG = re.compile(r"<[^>]+>")


def vtt_to_text(vtt: str) -> str:
    lines: list[str] = []
    for raw in vtt.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith(("WEBVTT", "Kind:", "Language:", "NOTE")):
            continue
        if _TS_LINE.search(line):
            continue
        if line.isdigit():  # cue index
            continue
        line = _TAG.sub("", line)  # strip <c> / <00:00:00.000> inline tags
        line = re.sub(r"\s+", " ", line).strip()
        if not line:
            continue
        # Auto-captions repeat the rolling last line; skip immediate duplicates.
        if lines and lines[-1] == line:
            continue
        lines.append(line)
    return "\n".join(lines)


def fetch_captions(video_url: str, langs: list[str], workdir: Path) -> str | None:
    """Download best available caption track; return plain text or None."""
    outtmpl = str(workdir / "%(id)s.%(ext)s")
    cmd = [
        "yt-dlp",
        "--skip-download",
        "--write-subs",
        "--write-auto-subs",
        "--sub-langs", ",".join(langs) + ",-live_chat",
        "--sub-format", "vtt/srv3/best",
        "--convert-subs", "vtt",
        "-o", outtmpl,
        video_url,
    ]
    subprocess.run(cmd, capture_output=True, text=True)
    vtts = sorted(workdir.glob("*.vtt"))
    if not vtts:
        return None
    # Prefer a file whose language matches the priority order.
    chosen = vtts[0]
    for lang in langs:
        match = [p for p in vtts if f".{lang}." in p.name]
        if match:
            chosen = match[0]
            break
    text = vtt_to_text(chosen.read_text(encoding="utf-8", errors="replace"))
    return text or None


def fetch_whisper(video_url: str, workdir: Path, model_name: str, langs: list[str]) -> str | None:
    try:
        import whisper  # type: ignore
    except ImportError:
        eprint("  (whisper not installed; skipping audio fallback. pip install openai-whisper)")
        return None
    audio_tmpl = str(workdir / "audio.%(ext)s")
    cmd = [
        "yt-dlp", "-f", "bestaudio", "-x", "--audio-format", "mp3",
        "-o", audio_tmpl, video_url,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    audios = list(workdir.glob("audio.*"))
    if proc.returncode != 0 or not audios:
        eprint("  (audio download failed)")
        return None
    model = whisper.load_model(model_name)
    lang = langs[0] if langs else None
    result = model.transcribe(str(audios[0]), language=lang)
    return (result.get("text") or "").strip() or None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("url", help="Channel (…/@handle or …/@handle/videos), playlist, or video URL")
    ap.add_argument("--out", default="transcripts", help="Output directory (default: transcripts)")
    ap.add_argument("--langs", default="ja,en", help="Caption language priority, comma-separated (default: ja,en)")
    ap.add_argument("--limit", type=int, default=None, help="Only process the first N videos")
    ap.add_argument("--combined", default="context.md", help="Combined context filename (default: context.md)")
    ap.add_argument("--whisper", action="store_true", help="Transcribe audio with Whisper when no captions exist")
    ap.add_argument("--whisper-model", default="small", help="Whisper model size (default: small)")
    ap.add_argument("--overwrite", action="store_true", help="Re-fetch videos even if a transcript file already exists")
    args = ap.parse_args()

    check_yt_dlp()
    langs = [l.strip() for l in args.langs.split(",") if l.strip()]
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    eprint(f"Listing videos from: {args.url}")
    videos = list_videos(args.url, args.limit)
    eprint(f"Found {len(videos)} video(s).")
    if not videos:
        return 1

    manifest: list[dict] = []
    combined_parts: list[str] = []
    ok = miss = 0

    for i, v in enumerate(videos, 1):
        num = f"{i:03d}"
        slug = slugify(v["title"])
        txt_path = out / f"{num}_{slug}.txt"
        source = None
        text = None

        if txt_path.exists() and not args.overwrite:
            eprint(f"[{num}/{len(videos)}] skip (exists): {v['title']}")
            text = txt_path.read_text(encoding="utf-8", errors="replace")
            source = "cached"
        else:
            eprint(f"[{num}/{len(videos)}] {v['title']}")
            with tempfile.TemporaryDirectory() as td:
                work = Path(td)
                text = fetch_captions(v["url"], langs, work)
                if text:
                    source = "captions"
                elif args.whisper:
                    eprint("  no captions -> whisper")
                    text = fetch_whisper(v["url"], work, args.whisper_model, langs)
                    if text:
                        source = "whisper"

        if text:
            header = f"{v['title']}\n{v['url']}\n{'=' * 60}\n"
            txt_path.write_text(header + text + "\n", encoding="utf-8")
            combined_parts.append(
                f"\n\n{'#' * 2} {v['title']}\n<{v['url']}>\n\n{text}\n"
            )
            ok += 1
        else:
            miss += 1
            eprint("  (no transcript available)")

        manifest.append(
            {
                "index": i, "id": v["id"], "title": v["title"], "url": v["url"],
                "source": source, "file": txt_path.name if text else None,
            }
        )

    combined_path = out / args.combined
    intro = (
        f"# Transcripts: {args.url}\n\n"
        f"Total videos: {len(videos)} | With transcript: {ok} | Missing: {miss}\n"
    )
    combined_path.write_text(intro + "".join(combined_parts), encoding="utf-8")
    (out / "index.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    eprint("")
    eprint(f"Done. transcripts: {ok}, missing: {miss}")
    eprint(f"Per-video files: {out}/")
    eprint(f"Combined context: {combined_path}")
    eprint(f"Manifest:         {out / 'index.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
