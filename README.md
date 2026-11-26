# paper-video-pipeline

Turn a research paper into a narrated, animated explainer video in the style of 3Blue1Brown:
[manim](https://www.manim.community/) for the animation, a local text-to-speech voice for narration,
ffmpeg to assemble. Everything runs offline on a normal laptop (no GPU needed).

- horizontal 16:9 videos or vertical 9:16 Shorts
- English and Mandarin versions from the same scenes
- an audio-only podcast mode
- built to be driven by [Claude Code](https://claude.com/claude-code) (see `CLAUDE.md` and `skill/`),
  but every step is a plain shell command

## Requirements

Linux, `curl`, a system TeX Live with `standalone.cls` (`apt install texlive-latex-extra`), and for
Mandarin the `Noto Sans CJK SC` font (`apt install fonts-noto-cjk`). About 4 GB of disk for the
toolchain, which `setup.sh` installs into `.tools/` inside this folder (nothing system-wide).

```sh
./setup.sh            # manim, ffmpeg, piper TTS + voices (idempotent)
./setup.sh --kokoro   # optional: Kokoro-82M voices, much more natural (CPU torch, ~1 GB)
./setup.sh --chatterbox  # optional: narrate with a clone of your own voice (Chatterbox, ~3.5 GB of models)
```

## Quick start

```sh
cp -r examples/minimal projects/demo
./pvp tts demo                     # narration.py -> audio + durations
./pvp render demo low              # 480p preview renders (re-runs only redo scenes that changed)
./pvp sheets demo                  # contact sheets in projects/demo/sheets/ to check layouts
./pvp render demo high             # 1080p
./pvp assemble demo demo           # -> videos/demo.mp4 (+ a small 720p copy)
```

Mandarin version of the same project (needs `narration_zh.py` and `zh.py`, see the example):

```sh
PVP_LANG=zh ./pvp tts demo && PVP_LANG=zh ./pvp render demo high && PVP_LANG=zh ./pvp assemble demo demo_zh
```

Vertical Short: `touch projects/<slug>/VERTICAL` before rendering.

**Your own voice:** record 10–20 s of clean speech (Chatterbox only uses the **first 10 s**, so make those your best) (WAV, mono, ≥ 24 kHz, quiet room, no "ehm"), save it as
`projects/<slug>/my_voice.wav` and set `VOICE = "chatterbox:my_voice.wav"` in `narration.py`. Each sentence
is spoken up to three times and a speech recogniser keeps the take that matches the script best; sentences
it is unsure about are printed as `CHECK` so you can listen to those first. Fast on a GPU, slow on CPU.
Consider telling viewers the narration is a voice clone.

**Pronunciations:** an optional `projects/<slug>/pronunciations.txt` fixes names and abbreviations for any voice
(`pronunciations_zh.txt` for the Mandarin script):

```
# written = spoken   (longest entries win; subtitles/on-screen text keep the written form)
IEEE = I triple E
Qwen = Kwen
arXiv = archive
```
A real paper: `./pvp new <slug> <arxiv-id>` downloads the PDF and text into `projects/<slug>/paper/`.

## How a project works

- `narration.py`: `N = {"S01_Intro": ["beat 1 text", "beat 2 text"], ...}`. One key per scene, one entry per
  narration beat. Optional `VOICE`, `SPEED`, `PAUSE`.
- `scenes*.py`: one `class S01_Intro(NScene)` per key. `self.say()` starts the next beat's audio,
  `self.at(0.6)` waits until 60% of it has been spoken, so animations land on the right words.
  Helpers (`T`, `M`, `card`, `bullets`, `label_brace`, ...) are in `engine/common.py`.
- Generated files (audio, renders, logs, sheets) stay inside the project folder and are git-ignored.

Full workflow, house style, voices and known pitfalls: [`CLAUDE.md`](CLAUDE.md).

## Use with Claude Code

Copy `skill/paper-video/` to `~/.claude/skills/`, replace `PIPELINE_DIR` in its `SKILL.md` with the path
of this checkout, then ask Claude Code e.g. "make a video explaining arXiv:XXXX.XXXXX".

## License

MIT, see [LICENSE](LICENSE). Generated videos are yours; voices and models keep their own licenses
(piper voices: see their model cards; Kokoro-82M: Apache 2.0).
