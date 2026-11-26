"""Synthesize narration: python engine/tts.py <project_dir> [Scene ...]

Reads <project>/narration.py (dict N: scene name -> list of segment strings), writes
<project>/audio/<Scene>_<i>.wav and <project>/durations.json (seconds per segment).
With scene names given, only those scenes are regenerated.
PVP_NARRATION=listen.py switches to the audio-only script -> audio_listen/, durations_listen.json.
Voice: PVP_VOICE env, else VOICE in the narration file, else en_GB-cori-high (.tools/voices/<name>.onnx).
"kokoro:<voice>" (e.g. kokoro:af_heart, kokoro:zf_xiaoxiao) uses Kokoro-82M instead of piper;
optional SPEED (default 1.0) and PAUSE (s after each sentence, default 0.35) in the narration file.
"""
import importlib.util, json, os, sys, wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
proj = Path(sys.argv[1]).resolve()
only = set(sys.argv[2:])

nfile = os.environ.get("PVP_NARRATION", "narration.py")
suffix = "" if nfile == "narration.py" else "_" + Path(nfile).stem
spec = importlib.util.spec_from_file_location("narration", proj / nfile)
mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
N = mod.N

OUT = proj / ("audio" + suffix)
OUT.mkdir(exist_ok=True)
vname = os.environ.get("PVP_VOICE") or getattr(mod, "VOICE", "en_GB-cori-high")
print("voice", vname, flush=True)
PAUSE = getattr(mod, "PAUSE", 0.35)
if vname.startswith("kokoro:"):
    import numpy as np
    from kokoro import KPipeline
    kvoice = vname.split(":", 1)[1]
    kpipe = KPipeline(lang_code=kvoice[0], repo_id="hexgrad/Kokoro-82M")   # a/b = English, z = Mandarin
    SPEED = getattr(mod, "SPEED", 1.0)
    SPLIT = r"(?<=[.!?。！？…])\s*"

    def synth(text, path):
        pcm = []
        for _, _, audio in kpipe(text, voice=kvoice, speed=SPEED, split_pattern=SPLIT):
            if audio is None:
                continue
            pcm.append(np.asarray(audio, dtype=np.float32))
            pcm.append(np.zeros(int(24000 * PAUSE), dtype=np.float32))
        x = np.clip(np.concatenate(pcm), -1, 1)
        with wave.open(str(path), "wb") as w:
            w.setframerate(24000); w.setsampwidth(2); w.setnchannels(1)
            w.writeframes((x * 32767).astype("<i2").tobytes())
else:
    from piper import PiperVoice, SynthesisConfig
    voice = PiperVoice.load(str(ROOT / ".tools" / "voices" / f"{vname}.onnx"))
    cfg = SynthesisConfig(length_scale=1.06)

    def synth(text, path):
        with wave.open(str(path), "wb") as w:
            first = True
            # one chunk per sentence; add a natural pause after each
            for chunk in voice.synthesize(text, syn_config=cfg):
                if first:
                    w.setframerate(chunk.sample_rate); w.setsampwidth(chunk.sample_width); w.setnchannels(chunk.sample_channels)
                    first = False
                w.writeframes(chunk.audio_int16_bytes)
                w.writeframes(b"\x00\x00" * int(chunk.sample_rate * PAUSE))

durs_path = proj / f"durations{suffix}.json"
durs = json.loads(durs_path.read_text()) if durs_path.exists() else {}
for scene, segs in N.items():
    if only and scene not in only:
        continue
    durs[scene] = []
    for i, text in enumerate(segs):
        p = OUT / f"{scene}_{i}.wav"
        synth(text, p)
        with wave.open(str(p)) as w:
            durs[scene].append(round(w.getnframes() / w.getframerate(), 3))
    print(scene, round(sum(durs[scene]), 1), "s", flush=True)
    durs_path.write_text(json.dumps(durs, indent=1))
# drop scenes that no longer exist in the narration
durs = {k: v for k, v in durs.items() if k in N}
durs_path.write_text(json.dumps(durs, indent=1))
print("total min", round(sum(sum(v) for v in durs.values()) / 60, 2))
