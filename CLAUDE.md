# Paper → explainer video pipeline

Turns an arXiv paper into a narrated, animated (3Blue1Brown-style) explainer video: manim for
visuals, piper for offline TTS narration, ffmpeg to assemble. Everything persistent lives here;
nothing depends on the session scratchpad.

## House style (applies to every video)
- **In depth, but from scratch / first principles.** Assume no background beyond basic math.
- **Assume no information-theoretic background** (entropy, cross-entropy, KL, mutual
  information…). Never just name it: build it from everyday ideas first ("surprise = −log q",
  "cross-entropy = average surprise if the world follows p but you predicted q", "KL = extra
  surprise beyond the unavoidable"), with a concrete toy example (e.g. a weather forecaster), and
  only then show the symbols.
- Typical length: ~18–25 min, 10–13 scenes.
- **Always also make a Mandarin (Chinese) version** of every video (larger audience). See "Mandarin version" below.

## Layout
```
setup.sh            idempotent install into .tools/ (micromamba env w/ manim+ffmpeg+scipy, piper, voice)
pvp                 driver: new | tts | render | sheets | assemble | listen-tts | listen   (run with no args for usage)
engine/common.py    shared look + NScene base class (narration sync) + helpers
engine/tts.py       narration.py -> audio/*.wav + durations.json
engine/audiobook.py wavs -> one chaptered, loudness-normalised mono MP3 (audio-only mode)
projects/<slug>/    one folder per paper (see below)
videos/             finished videos: <name>.mp4 (1080p) + <name>_720p.mp4 (small copy)
podcasts/           finished audio-only episodes: <name>.mp3
.tools/             installed toolchain (do not edit)
```
Project folder: `paper/` (pdf, txt, meta), `narration.py`, `scenes_a.py`, `scenes_b.py`, optional
helper modules (e.g. `gp.py`), and generated `audio/ durations.json media_low/ media_high/ logs/ sheets/`.
Start from `examples/minimal/` (copy it to `projects/<slug>/`); your own past projects are good templates too.

## Workflow
0. `./setup.sh` (fast no-op if already installed).
1. `./pvp new <slug> <arxiv-id>` → read `projects/<slug>/paper/paper.txt` in full (methods
   and appendices too). If the paper doesn't match what was requested, ask.
2. Write `narration.py`: `N = {"S01_Intro": [seg, seg, ...], ...}` — insertion order = video
   order. One segment ≈ one visual beat (15–40 s). Write for the ear: spell symbols as spoken
   ("p of y given x and D", "P F N", "K L"), numbers in words where TTS might stumble. Check odd
   words with `piper` phonemize if unsure. Fact-check every number against the paper.
3. `./pvp tts <slug>` (runs ~1 s audio per 1 s wall; run in background for long scripts). Re-run
   with scene names to regenerate only those.
4. Write scenes (split across `scenes_a.py` / `scenes_b.py`; start each file with
   `from common import *`). Each scene is `class SNN_Name(NScene)` matching a narration key.
5. `./pvp render <slug> low` → `./pvp sheets <slug>` (and `./pvp sheets <slug> 115 5` for the
   later part of long scenes) → **look at every sheet** with Read, fix overlaps/clipping, repeat.
6. `./pvp render <slug> high` → spot-check → `./pvp assemble <slug> <name>`.
7. Deliver: the 1080p file is usually > 30 MB (SendUserFile limit) → send `videos/<name>_720p.mp4`
   and give the path of the full one.

## Mandarin version (always, alongside English)
Per project: `narration_zh.py` (same scene keys and segment counts as `narration.py`, `VOICE = "zh_CN-huayan-medium"`,
natural spoken Mandarin, numbers in Chinese characters, no Latin acronyms in speech) and `zh.py`
(`ZH = {english on-screen string: chinese}`). Then:
`PVP_LANG=zh ./pvp tts <slug>` → `PVP_LANG=zh ./pvp render <slug> low` → check `logs/zh_missing.txt` (every
untranslated `T()` string or `\text{}` formula part is logged there; add them to zh.py, delete the file, re-render)
→ `PVP_LANG=zh ./pvp sheets <slug>` (sheets/*_zh_*.png) → `PVP_LANG=zh ./pvp render <slug> high` →
`PVP_LANG=zh ./pvp assemble <slug> <name>_zh`.
How it works: `common.T()` runs every string through `tr()`; `M()` turns parts found in ZH into Text (CJK can't go
through LaTeX), so write maths in those translations with Unicode (2⁸, ½, →). Font: Noto Sans CJK SC.
Use `T()` (not raw `Text()`) for any word on screen, or it won't be translated.
Separate outputs: audio_narration_zh/, durations_narration_zh.json, media_low_zh/, media_high_zh/.
Voice: Kokoro `VOICE = "kokoro:zf_xiaoxiao"` (preferred); piper `zh_CN-huayan-medium`
is the flat fallback. Kokoro zh: keep Latin words out of the Mandarin script (G2P).

## Voices (Kokoro preferred since 2026-11-25)
piper sounds fast, monotone and has no breaks. Kokoro-82M (CPU torch in .tools/env, not in setup.sh) via
`VOICE = "kokoro:af_heart"` (English) / `"kokoro:zf_xiaoxiao"` (Mandarin); optional `SPEED`, `PAUSE` (s after each
sentence, default 0.35) in the narration file. Use "..." in the text for a dramatic pause.
Own voice (Chatterbox): `VOICE = "chatterbox:my_voice.wav"` (file in the project folder, 10-20 s, clean,
calm presentation pace). Needs `./setup.sh --chatterbox`; pvp switches to its Python 3.11 env by itself.
Best-of-TAKES per sentence with a faster-whisper check; low-scoring sentences are printed as CHECK: listen
to those, then fix wording/pronunciations, or delete their folder in .tts_cache/ for fresh takes.
Knobs: EXAGGERATION (0.4; 0.3 calmer, 0.5 livelier), CFG (0.5; 0.3 slower), TAKES (3). English numbers are
written out automatically. Mandarin uses Chatterbox's multilingual model with the same reference. Slow on CPU.

## Pronunciations (all voices)
`projects/<slug>/pronunciations.txt` (`written = spoken` per line, longest first; `pronunciations_zh.txt`
for narration_zh.py) is applied to the narration text before synthesis. Use it for names/acronyms
instead of misspelling them in narration.py.

## Vertical Shorts (9:16)
`touch projects/<slug>/VERTICAL` → renders 480x854 (low) / 1080x1920 (high), sheets 6x2, preview 720x1280.
common.py pins the frame to 8 tall x 4.5 wide for portrait output (manim's default would keep 14.2 wide and
make everything tiny). Use `config.frame_width` for layout; one centered column, big bold words.
Keep scripts short and punchy (~1–2 min); a single `scenes.py` is enough.

## Audio-only mode (for listening in the car / on walks)
Same standing requirements as the videos, but there is no screen, so it needs its own script:
`projects/<slug>/listen.py` (same `N` format, plus optional `TITLES = {"S01_Intro": "Why this paper"}`
for chapter names). Don't just reuse `narration.py`: it points at visuals.
Workflow: `./pvp new` → read paper → write `listen.py` → `./pvp listen-tts <slug>` (background) →
`./pvp listen <slug> <name>` → send `podcasts/<name>.mp3` (~0.5 MB/min, fits SendUserFile).
No manim, so an episode takes minutes instead of hours.

Writing for a listener who can't see, pause easily, or rewind (driving):
- **Zero visual references.** No "look at", "here", "on the left", "this table", "as shown".
- **Equations get spoken in full, then re-spoken in words.** Name each symbol once with a
  memorable role ("call the training data D, for Data"), keep the symbol count small, and say the
  equation slowly piece by piece: "the score is: minus the log of q. Minus. Log. Of q. In words:
  how surprised the model was." Never rely on equation numbers alone; restate the equation.
- **Signpost constantly:** at chapter start say where we are and what's coming; at chapter end a
  2–3 sentence recap. Recap the whole thing at the end.
- **Concrete toy examples carry the math** (weather forecaster, coin, dice), with small round
  numbers the listener can hold in their head. Avoid lists longer than three.
- Shorter sentences than the video script; one idea per sentence. Repetition is a feature.
- Segments can be longer (30–90 s) since nothing syncs to them; segment breaks become short
  pauses, scene breaks become chapters with a 2 s pause.
- Length: 20–35 min is fine; the listener isn't watching a screen.
- Can coexist with a video in the same project folder (separate `audio_listen/` wavs).

## NScene API (engine/common.py)
- `self.say()` starts the next narration segment's audio (first pads out the previous one).
- `self.at(frac)` waits until `frac` of the current segment has elapsed → place animations at
  the moment the narration mentions them.
- `self.header(num, title)`, `self.clear_body()` (keeps header), `self.end()` (finish + fade all).
- Helpers: `T(text,size)` / `M(*tex_parts,size)` (auto-shrink to frame width), `card`, `bullets`,
  `label_brace(mob, text, UP|DOWN, color)` — the workhorse for labelling equation parts,
  `eqno(mob, n)`, `bars(ax, centers, heights, width, color)`, `code_box(lines, hl=[...])`.
- Colors: INK, DIM, C_X, C_Y (good/truth), C_F (highlight), C_BAD, C_P, C_Q, C_ANC; BG dark.
- Build equations from separate `M(...)` parts so each part can be colored/braced by index;
  never brace by glyph slices like `eq[1][0:16]`.

## Non-arXiv sources (tutorials, blog posts, demos)
`pvp new` only handles arXiv. For a web page: `mkdir -p projects/<slug>/paper`, curl the HTML to
`paper/page.html`, strip tags with a small Python snippet into `paper/paper.txt`, and write
`paper/meta.txt` by hand. Tutorials can contain
wrong formulas: verify the math numerically before narrating it and note corrections in meta.txt.

## Pitfalls already hit (don't rediscover)
- `latex` on PATH is TinyTeX (no standalone.cls) → pvp puts /usr/bin first. Don't undo that.
- Parallel renders sharing a media dir race on Tex cache → pvp uses one media dir per scene.
- Text wider than the frame gets clipped → T/M auto-shrink, but still check sheets.
- `label_brace` under/over neighbouring parts collide: alternate UP/DOWN.
- Indented code in `Text` loses leading spaces → use `code_box` from common.py.
- Dynamic `always_redraw` braces with zero length can crash → FadeOut before collapsing.
- Don't fabricate results visuals (e.g. a fake "model output" curve); show the real reference
  and state the paper's finding in text.
- TTS warnings "Missing phoneme from id map" are harmless.
- Voice: default `en_GB-cori-high` (`en_US-ljspeech-high` is a good alternative). Override per
  project with `VOICE = "<name>"` in narration.py/listen.py; extra voices sit in `.tools/voices/`.
  Kept on purpose (alternatives): ryan, lessac, ljspeech, joe, norman, hfc_female
  (en_US), cori, alba, northern_english_male (en_GB). Not in setup.sh; re-download from
  huggingface.co/rhasspy/piper-voices if .tools is rebuilt. Sample reel: podcasts/voice_samples.mp3.
