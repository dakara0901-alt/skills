---
name: youtube-transcripts
description: Use this skill whenever the user wants to turn YouTube videos into text — transcribing or extracting captions/subtitles from a whole channel, a playlist, or a single video, and collecting them into plain-text files or one combined context file for search, summarization, or RAG. Triggers include mentions of a YouTube channel/handle (e.g. "@somechannel"), "文字起こし", "字幕をテキスト化", "動画を全部テキストに", "transcribe this channel", or building a knowledge/context file out of someone's videos.
license: Proprietary. LICENSE.txt has complete terms
---

# YouTube Transcripts → Text & Context

## Overview

Convert every video on a YouTube channel (or a playlist / single video) into
plain-text transcripts, plus one combined "context" file suitable for feeding
to an LLM, searching, or summarizing.

For each video the bundled script `scripts/youtube_transcripts.py`:
1. Pulls existing captions — manual subtitles first, then auto-generated — in
   the preferred languages (default `ja,en`).
2. Optionally (`--whisper`) falls back to downloading the audio and
   transcribing it locally with Whisper when a video has no captions.

It writes one `.txt` per video, a combined `context.md`, and an `index.json`
manifest.

> A step-by-step Japanese guide for running this on a local Mac/Windows machine
> is in [`USAGE_ja.md`](USAGE_ja.md).

## Requirements & network access

- **`yt-dlp`** is required: `pip install -U yt-dlp`
- **Whisper fallback** (optional) additionally needs `openai-whisper` and
  `ffmpeg`.
- **Network access to YouTube is required.** Some managed/sandboxed
  environments (including Claude Code web sessions with a restricted network
  policy) block YouTube — `yt-dlp` will fail with `403 Forbidden` from the
  proxy. In that case run this skill on a machine with normal internet access
  (e.g. the user's local computer) or in an environment whose network policy
  allows YouTube. Check first: `yt-dlp --version` then a quick
  `yt-dlp --flat-playlist -I 1:1 --print id <channel-url>`.

## Quick start

```bash
pip install -U yt-dlp

# All videos on a channel -> ./transcripts/*.txt + ./transcripts/context.md
python scripts/youtube_transcripts.py "https://www.youtube.com/@SomeChannel/videos"
```

Channel URLs: pass either `https://www.youtube.com/@handle` or
`https://www.youtube.com/@handle/videos` (add `/streams` or `/shorts` to target
those tabs, or a playlist / single-video URL).

## Common options

```bash
# Japanese captions preferred, then English (default is already ja,en)
python scripts/youtube_transcripts.py "<url>" --langs ja,en

# Only the 10 most recent videos, into a custom folder
python scripts/youtube_transcripts.py "<url>" --limit 10 --out ./ai_sennin

# Transcribe audio with Whisper for videos that have no captions
python scripts/youtube_transcripts.py "<url>" --whisper --whisper-model small

# Re-fetch even if a transcript file already exists
python scripts/youtube_transcripts.py "<url>" --overwrite
```

| Option | Meaning | Default |
| --- | --- | --- |
| `--out DIR` | Output directory | `transcripts` |
| `--langs a,b` | Caption language priority | `ja,en` |
| `--limit N` | Process only the first N videos | all |
| `--combined NAME` | Combined context filename | `context.md` |
| `--whisper` | Audio → text fallback when no captions | off |
| `--whisper-model` | Whisper model size (`tiny`…`large`) | `small` |
| `--overwrite` | Ignore existing transcript files | off |

## Output layout

```
transcripts/
├── 001_<title>.txt     # one transcript per video (title + URL header + text)
├── 002_<title>.txt
├── ...
├── context.md          # all transcripts concatenated, with per-video headers
└── index.json          # manifest: id, title, url, source (captions/whisper), file
```

`index.json`'s `source` field tells you how each transcript was obtained
(`captions`, `whisper`, `cached`) or `null` when nothing was available — useful
for spotting videos that need the `--whisper` pass.

## Notes & tips

- **No captions and no `--whisper`** → that video is skipped and recorded as
  missing in `index.json`. Re-run with `--whisper` to fill the gaps.
- **Large channels**: start with `--limit` to sanity-check output, then run the
  full pass. Existing files are skipped by default, so a re-run resumes where it
  stopped.
- **Rights & usage**: transcripts are derived from third-party videos. Use them
  for personal study/analysis and respect the creator's rights and YouTube's
  Terms of Service.
