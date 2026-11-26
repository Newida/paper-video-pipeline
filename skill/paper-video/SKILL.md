---
name: paper-video
description: Make a narrated, animated (3Blue1Brown-style) explainer video of a research paper (e.g. "make a video explaining <arXiv link>"), optionally as a vertical Short, in English and Mandarin, or an audio-only podcast version. Uses the paper-video-pipeline checkout.
---

Use the pipeline checkout at `PIPELINE_DIR` (replace with where you cloned paper-video-pipeline).

1. Read `PIPELINE_DIR/CLAUDE.md` in full first: house style, workflow, scene API, known pitfalls.
2. Run `./setup.sh` there (no-op if installed; `./setup.sh --kokoro` for the better voices), then follow
   the workflow with `./pvp`. Work inside `projects/<slug>/` (start by copying `examples/minimal/`).
3. Discuss the storyline with the user before writing narration; render low-res and look at every
   contact sheet before the high-res render.
4. Vertical Short: `touch projects/<slug>/VERTICAL`. Mandarin version: `narration_zh.py` + `zh.py`, then
   prefix commands with `PVP_LANG=zh` (see CLAUDE.md).
5. Audio-only ("podcast"): follow "Audio-only mode" in CLAUDE.md (`listen.py`, `./pvp listen-tts`, `./pvp listen`).
