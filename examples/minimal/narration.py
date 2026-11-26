# Minimal example. Copy this folder to projects/<slug>/ and run:
#   ./pvp tts <slug> && ./pvp render <slug> low && ./pvp sheets <slug>
# One key per scene (insertion order = video order); one list entry per narration beat.
# VOICE = "kokoro:af_heart"   # nicer voice, after ./setup.sh --kokoro (default: piper en_GB-cori-high)

N = {}
N["S01_Intro"] = [
    "This is a minimal example of the paper video pipeline. Each list entry is one narration beat.",
    "Animations are timed to the audio: say starts a beat, and at waits for a fraction of it.",
]
