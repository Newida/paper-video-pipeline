"""Synthesize narration: python engine/tts.py <project_dir> [Scene ...]

Reads <project>/narration.py (dict N: scene name -> list of segment strings), writes
<project>/audio/<Scene>_<i>.wav and <project>/durations.json (seconds per segment).
With scene names given, only those scenes are regenerated.
PVP_NARRATION=listen.py switches to the audio-only script -> audio_listen/, durations_listen.json.
Voice: PVP_VOICE env, else VOICE in the narration file, else en_GB-cori-high (.tools/voices/<name>.onnx).
"kokoro:<voice>" (e.g. kokoro:af_heart, kokoro:zf_xiaoxiao) uses Kokoro-82M instead of piper;
optional SPEED (default 1.0) and PAUSE (s after each sentence, default 0.35) in the narration file.
"chatterbox:<file.wav>" clones the voice in <project>/<file.wav> (10-20 s clean recording) with Chatterbox
(needs ./setup.sh --chatterbox; ./pvp picks its Python automatically). Each sentence is spoken up to TAKES
times (default 3) and faster-whisper keeps the take closest to the script; takes are cached in
<project>/.tts_cache/. Optional EXAGGERATION (0.4), CFG (0.5, lower = slower/calmer), TEMPERATURE (0.7).
Pronunciations: optional <project>/pronunciations.txt ("written = spoken" per line; pronunciations_zh.txt
for the Mandarin script) is applied to the narration before synthesis, for every voice.
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
LANG = "zh" if suffix.endswith("_zh") else "en"

# ---------------------------------------------------------------- pronunciations (all voices)
PRON = []
pfile = proj / ("pronunciations_zh.txt" if LANG == "zh" else "pronunciations.txt")
if pfile.exists():
    for line in pfile.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if "=" in line:
            w, sp = (x.strip() for x in line.split("=", 1))
            if w:
                PRON.append((w, sp))
    PRON.sort(key=lambda p: -len(p[0]))       # longest first: "GPT-4o mini" before "GPT"
    print("pronunciations:", pfile.name, len(PRON), flush=True)


def say_as(text):
    import re
    for w, sp in PRON:
        text = re.sub(r"(?<![\w-])" + re.escape(w) + r"(?![\w-])", sp, text)
    return text


if vname.startswith("chatterbox:"):
    import difflib, gc, hashlib, re
    import numpy as np
    import soundfile as sf
    import torch

    ref = Path(vname.split(":", 1)[1])
    ref = ref if ref.is_absolute() else proj / ref
    if not ref.exists():
        sys.exit(f"voice reference {ref} not found (record 10-20 s of clean speech, WAV mono >= 24 kHz)")
    TAKES = getattr(mod, "TAKES", 3)
    GEN = dict(exaggeration=getattr(mod, "EXAGGERATION", 0.4), cfg_weight=getattr(mod, "CFG", 0.5),
               temperature=getattr(mod, "TEMPERATURE", 0.7))
    dev = "cuda" if torch.cuda.is_available() else "mps" if torch.backends.mps.is_available() else "cpu"
    _load = torch.load
    torch.load = lambda *a, **k: _load(*a, **{"map_location": torch.device(dev), **k})  # CUDA-saved weights
    import perth
    if perth.PerthImplicitWatermarker is None:      # watermark package failed to load: run without it
        print("WARNING: Chatterbox audio watermark unavailable (resemble-perth failed to import; try "
              "pip install 'setuptools<81' in .tools/chatterbox); continuing without it", flush=True)
        perth.PerthImplicitWatermarker = perth.DummyWatermarker
    if LANG == "en":
        from chatterbox.tts import ChatterboxTTS
        model = ChatterboxTTS.from_pretrained(device=dev)
        gen = lambda t: model.generate(t, audio_prompt_path=str(ref), **GEN)
    else:
        from chatterbox.mtl_tts import ChatterboxMultilingualTTS
        model = ChatterboxMultilingualTTS.from_pretrained(device=dev)
        gen = lambda t: model.generate(t, language_id=LANG, audio_prompt_path=str(ref), **GEN)
    SR = model.sr
    from faster_whisper import WhisperModel
    whisper = WhisperModel("small.en" if LANG == "en" else "small", device="cpu", compute_type="int8")
    print(f"chatterbox on {dev}, reference {ref.name}", flush=True)
    vhash = hashlib.sha1(ref.read_bytes()).hexdigest()[:10]
    CACHE = proj / ".tts_cache"

    ONES = ("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen "
            "fifteen sixteen seventeen eighteen nineteen").split()
    TENS = "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()

    def int_words(n):
        if n < 20: return ONES[n]
        if n < 100: return TENS[n // 10] + ("" if n % 10 == 0 else "-" + ONES[n % 10])
        if n < 1000: return ONES[n // 100] + " hundred" + ("" if n % 100 == 0 else " " + int_words(n % 100))
        if n < 10**6: return int_words(n // 1000) + " thousand" + ("" if n % 1000 == 0 else " " + int_words(n % 1000))
        return str(n)

    def num_words(tok):
        tok = tok.replace(",", "")
        if "." in tok:
            a, b = tok.split(".", 1)
            return int_words(int(a or 0)) + " point " + " ".join(ONES[int(d)] for d in b)
        return int_words(int(tok))

    def english_numbers(t):      # 93.5 -> ninety-three point five, 81 % -> eighty-one percent, 61.5k
        t = re.sub(r"(\d[\d,]*(?:\.\d+)?)\s?k\b", r"\1 thousand", t)
        t = re.sub(r"(\d)\s?%", r"\1 percent", t)
        t = re.sub(r"(\d)\s?[–-]\s?(\d)", r"\1 to \2", t)
        return re.sub(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?", lambda m: num_words(m.group(0)), t)

    def units(t):                # what the take check compares: letters/digits (en) or characters (zh),
        t = t.lower()            # ignoring spaces, so "pipe line" (a pronunciation) still matches "pipeline"
        return re.findall(r"[a-z0-9]", t) if LANG == "en" else re.findall(r"[\u4e00-\u9fff0-9a-z]", t)

    def trim(x, thresh=0.01, pad=0.05):
        idx = np.where(np.abs(x) > thresh * max(np.abs(x).max(), 1e-9))[0]
        return x if len(idx) == 0 else x[max(idx[0] - int(pad * SR), 0):min(idx[-1] + int(pad * SR), len(x))]

    def sentence(text):
        key = hashlib.sha1(f"{text}|{vhash}|{GEN}|{LANG}".encode()).hexdigest()[:16]
        d = CACHE / key
        if (d / "best.wav").exists():
            return sf.read(d / "best.wav", dtype="float32")[0]
        d.mkdir(parents=True, exist_ok=True)
        ref_u, best = units(text), None
        for t in range(TAKES):
            torch.manual_seed(int(key[:6], 16) + t)
            x = trim(gen(text).squeeze(0).detach().cpu().numpy().astype(np.float32))
            sf.write(d / f"take{t + 1}.wav", x, SR)
            segs, _ = whisper.transcribe(str(d / f"take{t + 1}.wav"), language=LANG, beam_size=5)
            heard = " ".join(s.text for s in segs)
            hyp = units(english_numbers(heard) if LANG == "en" else heard)
            score = difflib.SequenceMatcher(None, ref_u, hyp).ratio()
            if len(x) / SR > 1.7 * (len(ref_u) / (13.0 if LANG == "en" else 4.0)) + 1.0:   # ~13 letters/s
                score -= 0.15        # trailing babble or long gaps
            print(f"    take {t + 1}: {score:.2f}  {text[:60]}", flush=True)
            if best is None or score > best[0]:
                best = (score, x, heard)
            gc.collect()
            if best[0] >= 0.98:
                break
        sf.write(d / "best.wav", best[1], SR)
        (d / "best.json").write_text(json.dumps({"score": round(best[0], 3), "text": text, "heard": best[2]},
                                                ensure_ascii=False, indent=1))
        if best[0] < 0.9:
            print(f"  CHECK (score {best[0]:.2f}): {text}\n    heard: {best[2]}", flush=True)
        return best[1]

    def synth(text, path):
        text = english_numbers(text) if LANG == "en" else text
        parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+|(?<=[。！？…])", text) if p.strip()]
        # Chatterbox garbles very short sentences ("Why?" came out as "What? I can't hear you."):
        # speak them together with a neighbour instead.
        short = lambda t: len(t.split()) < 4 if LANG == "en" else len(t) < 6
        units_ = []
        for snt in parts:
            if units_ and short(snt):
                units_[-1] += " " + snt if LANG == "en" else snt
            else:
                units_.append(snt)
        if len(units_) > 1 and short(units_[0]):
            units_[1] = units_[0] + (" " if LANG == "en" else "") + units_[1]
            units_.pop(0)
        pcm = []
        for snt in units_:
            pcm += [sentence(snt), np.zeros(int(SR * PAUSE), np.float32)]
        x = np.clip(np.concatenate(pcm), -1, 1)
        with wave.open(str(path), "wb") as w:
            w.setframerate(SR); w.setsampwidth(2); w.setnchannels(1)
            w.writeframes((x * 32767).astype("<i2").tobytes())
elif vname.startswith("kokoro:"):
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
        synth(say_as(text), p)
        with wave.open(str(p)) as w:
            durs[scene].append(round(w.getnframes() / w.getframerate(), 3))
    print(scene, round(sum(durs[scene]), 1), "s", flush=True)
    durs_path.write_text(json.dumps(durs, indent=1))
# drop scenes that no longer exist in the narration
durs = {k: v for k, v in durs.items() if k in N}
durs_path.write_text(json.dumps(durs, indent=1))
print("total min", round(sum(sum(v) for v in durs.values()) / 60, 2))
