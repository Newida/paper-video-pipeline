"""Build an audio-only episode: python engine/audiobook.py <project_dir> <out.mp3> [narration file]

Joins the segment wavs from tts.py (audio/ for narration.py, audio_listen/ for listen.py) in narration order, with short pauses between
segments and longer ones between scenes, and writes one mono MP3 with a chapter per scene.
Chapter titles come from an optional dict TITLES in the narration file, else from the scene name.
"""
import importlib.util, subprocess, sys, wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FF = str(ROOT / ".tools" / "env" / "bin" / "ffmpeg")
proj = Path(sys.argv[1]).resolve()
out = Path(sys.argv[2]).resolve()
nfile = proj / (sys.argv[3] if len(sys.argv) > 3 else "narration.py")
adir = proj / ("audio" if nfile.name == "narration.py" else "audio_" + nfile.stem)

spec = importlib.util.spec_from_file_location("narration", nfile)
mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
N, TITLES = mod.N, getattr(mod, "TITLES", {})
meta = dict(l.split(": ", 1) for l in (proj / "paper" / "meta.txt").read_text().splitlines()
            if ": " in l) if (proj / "paper" / "meta.txt").exists() else {}

SEG_PAUSE, SCENE_PAUSE = 0.6, 2.0
pcm, chapters, rate, t = bytearray(), [], None, 0.0
for scene, segs in N.items():
    start = t
    for i in range(len(segs)):
        with wave.open(str(adir / f"{scene}_{i}.wav")) as w:
            rate = rate or w.getframerate()
            assert w.getframerate() == rate and w.getnchannels() == 1 and w.getsampwidth() == 2
            pcm += w.readframes(w.getnframes())
        pause = SCENE_PAUSE if i == len(segs) - 1 else SEG_PAUSE
        pcm += b"\x00\x00" * int(rate * pause)
        t = len(pcm) / 2 / rate
    title = TITLES.get(scene) or scene.split("_", 1)[-1].replace("_", " ")
    chapters.append((start, t, f"{len(chapters) + 1}. {title}"))

esc = lambda s: "".join("\\" + c if c in "=;#\\\n" else c for c in s)
md = [";FFMETADATA1", f"title={esc(meta.get('citation_title', out.stem))} (audio explainer)",
      "artist=paper-video-pipeline", "genre=Podcast"]
for a, b, title in chapters:
    md += ["[CHAPTER]", "TIMEBASE=1/1000", f"START={int(a * 1000)}", f"END={int(b * 1000)}", f"title={esc(title)}"]
mdfile = proj / "audiobook_meta.txt"
mdfile.write_text("\n".join(md) + "\n")

out.parent.mkdir(parents=True, exist_ok=True)
subprocess.run([FF, "-v", "error", "-y", "-f", "s16le", "-ar", str(rate), "-ac", "1", "-i", "-",
                "-i", str(mdfile), "-map_metadata", "1", "-map_chapters", "1",
                "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",  # podcast loudness: audible over car noise
                "-c:a", "libmp3lame", "-b:a", "64k", "-ar", "44100", "-id3v2_version", "3", str(out)],
               input=bytes(pcm), check=True)
for a, _, title in chapters:
    print(f"{int(a // 60):3d}:{int(a % 60):02d}  {title}")
print(f"total {t / 60:.1f} min -> {out} ({out.stat().st_size / 1e6:.1f} MB)")
