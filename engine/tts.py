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
Fix one sentence by ear (Chatterbox voices):
  --variants "<phrase>" [N] ["alternative wording" ...]   N takes (default 3) per wording, each with its own
      seed, for the sentence containing <phrase> -> <project>/variants/compare.wav (+ numbered wavs)
  --pick <n>   lock variant n into the cache (and switch the script to its wording); then run tts again
"""
import importlib.util, json, os, sys, wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
proj = Path(sys.argv[1]).resolve()
args = sys.argv[2:]
MODE = PHRASE = PICK = None
NVAR, ALTS = 3, []
if args[:1] == ["--variants"]:   # --variants "<phrase>" [N] ["alternative wording" ...]
    MODE, PHRASE, rest = "variants", args[1], args[2:]
    if rest and rest[0].isdigit():
        NVAR, rest = int(rest[0]), rest[1:]
    ALTS = rest
elif args[:1] == ["--pick"]:     # --pick <n>
    MODE, PICK = "pick", int(args[1])
only = set() if MODE else set(args)

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
    import difflib, gc, hashlib, re, shutil
    import numpy as np
    import soundfile as sf

    ref = Path(vname.split(":", 1)[1])
    ref = ref if ref.is_absolute() else proj / ref
    if not ref.exists():
        sys.exit(f"voice reference {ref} not found (record 10-20 s of clean speech, WAV mono >= 24 kHz)")
    TAKES = getattr(mod, "TAKES", 3)
    GEN = dict(exaggeration=getattr(mod, "EXAGGERATION", 0.4), cfg_weight=getattr(mod, "CFG", 0.5),
               temperature=getattr(mod, "TEMPERATURE", 0.7))
    vhash = hashlib.sha1(ref.read_bytes()).hexdigest()[:10]
    CACHE = proj / ".tts_cache"
    VDIR = proj / f"variants{suffix}"

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
        return re.findall(r"[a-z0-9]", t) if LANG == "en" else re.findall(r"[一-鿿0-9a-z]", t)

    def split_units(text):
        """Written text of one narration beat -> the units that are spoken one at a time."""
        text = english_numbers(text) if LANG == "en" else text
        parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+|(?<=[。！？…])", text) if p.strip()]
        # Chatterbox garbles very short sentences ("Why?" came out as "What? I can't hear you."):
        # speak them together with a neighbour instead.
        short = lambda t: len(t.split()) < 4 if LANG == "en" else len(t) < 6
        out = []
        for snt in parts:
            if out and short(snt):
                out[-1] += " " + snt if LANG == "en" else snt
            else:
                out.append(snt)
        if len(out) > 1 and short(out[0]):
            out[1] = out[0] + (" " if LANG == "en" else "") + out[1]
            out.pop(0)
        return out

    def cache_dir(spoken):
        return CACHE / hashlib.sha1(f"{spoken}|{vhash}|{GEN}|{LANG}".encode()).hexdigest()[:16]

    if MODE == "pick":           # lock a variant picked by ear; no model needed
        idx = {e["n"]: e for e in json.loads((VDIR / "index.json").read_text(encoding="utf-8"))}
        if PICK not in idx:
            sys.exit(f"no variant {PICK}; available: {sorted(idx)}")
        e = idx[PICK]
        d = cache_dir(say_as(e["written"]))
        d.mkdir(parents=True, exist_ok=True)
        shutil.copy(VDIR / f"{PICK:02d}.wav", d / "best.wav")
        (d / "best.json").write_text(json.dumps({"score": 1.0, "text": say_as(e["written"]),
                                                 "heard": f"picked by ear: variant {PICK}, seed {e['seed']}"},
                                                ensure_ascii=False, indent=1))
        print(f"locked variant {PICK} for {e['scene']} beat {e['segment']}: {e['written']}")
        if e["written"] != e["original"]:
            src = (proj / nfile).read_text(encoding="utf-8")
            if e["original"] in src:
                (proj / nfile).write_text(src.replace(e["original"], e["written"], 1), encoding="utf-8")
                print(f"{nfile}: changed the wording to the picked variant")
            else:
                print(f"NOTE: change this sentence in {nfile} by hand, to exactly:\n  {e['written']}")
        print("now run ./pvp tts again: it reuses the locked take")
        sys.exit(0)

    import torch
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
    print(f"chatterbox on {dev}, reference {ref.name}", flush=True)

    def trim(x, thresh=0.01, pad=0.05):
        idx = np.where(np.abs(x) > thresh * max(np.abs(x).max(), 1e-9))[0]
        return x if len(idx) == 0 else x[max(idx[0] - int(pad * SR), 0):min(idx[-1] + int(pad * SR), len(x))]

    if MODE == "variants":       # several seeds x wordings of one sentence, to pick by ear
        hits = [(sc, i, u) for sc, segs in N.items() for i, seg in enumerate(segs) for u in split_units(seg)
                if PHRASE.lower() in u.lower()]
        if not hits:
            sys.exit(f"{PHRASE!r} not found in {nfile}")
        for sc, i, u in hits[1:]:
            print(f"note: also in {sc} beat {i}: {u}  (only the first match is used)")
        scene, seg_i, original = hits[0]
        if VDIR.exists():
            shutil.rmtree(VDIR)
        VDIR.mkdir()
        index, pcm, t = [], [], 0.0
        beep = (0.3 * np.sin(2 * np.pi * 880 * np.arange(int(0.15 * SR)) / SR)).astype(np.float32)
        for wi, written in enumerate([original] + ALTS):
            written = english_numbers(written) if LANG == "en" else written
            for k in range(NVAR):
                seed = 1000 * (wi + 1) + 101 * (k + 1)
                torch.manual_seed(seed)
                x = trim(gen(say_as(written)).squeeze(0).detach().cpu().numpy().astype(np.float32))
                n = len(index) + 1
                sf.write(VDIR / f"{n:02d}.wav", x, SR)
                index.append({"n": n, "scene": scene, "segment": seg_i, "original": original,
                              "written": written, "seed": seed})
                pcm += [beep, np.zeros(int(0.35 * SR), np.float32)]
                t += 0.5
                print(f"  {n:2d}  at {int(t // 60)}:{t % 60:04.1f}  seed {seed}  {written}", flush=True)
                pcm += [x, np.zeros(int(1.0 * SR), np.float32)]
                t += len(x) / SR + 1.0
                gc.collect()
        sf.write(VDIR / "compare.wav", np.concatenate(pcm), SR)
        (VDIR / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"listen: {VDIR / 'compare.wav'} (a beep before each; numbers and times above)\n"
              f"then lock one:  ./pvp tts <slug> --pick <n>")
        sys.exit(0)

    from faster_whisper import WhisperModel
    whisper = WhisperModel("small.en" if LANG == "en" else "small", device="cpu", compute_type="int8")

    def sentence(text, written=None):
        d = cache_dir(text)
        if (d / "best.wav").exists():
            return sf.read(d / "best.wav", dtype="float32")[0]
        key = d.name
        d.mkdir(parents=True, exist_ok=True)
        ref_u, best = units(text), None
        ref_w = units(english_numbers(written) if LANG == "en" else written) if written and written != text else None
        for t in range(TAKES):
            torch.manual_seed(int(key[:6], 16) + t)
            x = trim(gen(text).squeeze(0).detach().cpu().numpy().astype(np.float32))
            sf.write(d / f"take{t + 1}.wav", x, SR)
            segs, _ = whisper.transcribe(str(d / f"take{t + 1}.wav"), language=LANG, beam_size=5)
            heard = " ".join(s.text for s in segs)
            hyp = units(english_numbers(heard) if LANG == "en" else heard)
            score = difflib.SequenceMatcher(None, ref_u, hyp).ratio()
            if ref_w:                # Whisper writes real words: a respelling like "Kwen" is heard as "Qwen"
                score = max(score, difflib.SequenceMatcher(None, ref_w, hyp).ratio())
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
            print(f"  CHECK (score {best[0]:.2f}): {text}\n    heard: {best[2]}\n"
                  f"    fix by ear: ./pvp tts <slug> --variants \"<a few words of it>\"", flush=True)
        return best[1]

    def synth(text, path):
        pcm = []
        for snt in split_units(text):
            pcm += [sentence(say_as(snt), written=snt), np.zeros(int(SR * PAUSE), np.float32)]
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
        text = say_as(text)
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
        text = say_as(text)
        with wave.open(str(path), "wb") as w:
            first = True
            # one chunk per sentence; add a natural pause after each
            for chunk in voice.synthesize(text, syn_config=cfg):
                if first:
                    w.setframerate(chunk.sample_rate); w.setsampwidth(chunk.sample_width); w.setnchannels(chunk.sample_channels)
                    first = False
                w.writeframes(chunk.audio_int16_bytes)
                w.writeframes(b"\x00\x00" * int(chunk.sample_rate * PAUSE))

if MODE:
    sys.exit("--variants / --pick work with chatterbox voices only")

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
