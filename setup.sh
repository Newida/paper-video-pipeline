#!/bin/sh
# One-time (idempotent) install of everything the pipeline needs, kept inside this folder in .tools/.
#   manim + ffmpeg (conda-forge, prebuilt — system python has no pip/venv and no cairo headers)
#   piper TTS + English voices (default cori-high) + a Mandarin fallback voice
#   ./setup.sh --kokoro   also installs Kokoro-82M (CPU torch, ~1 GB): much more natural voices
# Safe to re-run: skips whatever is already present.
set -e
P="$(cd "$(dirname "$0")" && pwd)"
T="$P/.tools"
mkdir -p "$T/bin" "$T/voices"
export MAMBA_ROOT_PREFIX="$T/mamba"
if [ ! -x "$T/bin/micromamba" ]; then
  curl -sL https://micro.mamba.pm/api/micromamba/linux-64/latest | tar xj -C "$T" bin/micromamba
fi
if [ ! -x "$T/env/bin/python" ]; then
  "$T/bin/micromamba" create -q -y -p "$T/env" -c conda-forge python=3.12 manim ffmpeg scipy
fi
"$T/env/bin/python" -c "import piper" 2>/dev/null || "$T/env/bin/python" -m pip install -q piper-tts
# default voice: cori; ryan was used for the first videos
for v in en/en_GB/cori/high/en_GB-cori-high en/en_US/ryan/high/en_US-ryan-high zh/zh_CN/huayan/medium/zh_CN-huayan-medium; do
  for e in .onnx .onnx.json; do
    f="$(basename $v)$e"
    [ -s "$T/voices/$f" ] || curl -sL -o "$T/voices/$f" "https://huggingface.co/rhasspy/piper-voices/resolve/main/$v$e"
  done
done
if [ "$1" = "--kokoro" ]; then
  "$T/env/bin/python" -c "import kokoro" 2>/dev/null || {
    "$T/env/bin/python" -m pip install -q torch --index-url https://download.pytorch.org/whl/cpu
    "$T/env/bin/python" -m pip install -q kokoro "misaki[zh]" soundfile; }
  "$T/env/bin/python" -c "import kokoro; print('kokoro OK')"
fi
"$T/env/bin/python" -c "import manim, piper, scipy; print('manim', manim.__version__)"
/usr/bin/latex --version | head -1 || echo "WARNING: needs system TeX Live with standalone.cls (apt install texlive-latex-extra)"
fc-list | grep -q "Noto Sans CJK SC" || echo "note: Mandarin versions need the Noto Sans CJK SC font (apt install fonts-noto-cjk)"
echo "setup OK"
