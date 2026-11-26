"""Per-scene render fingerprints, so ./pvp render only re-renders scenes whose inputs changed.

  python engine/fingerprint.py <project> <state> stale <Scene ...>   print the scenes that need a render
  python engine/fingerprint.py <project> <state> mark  <Scene ...>   record them as rendered

<state> names the render target, e.g. "low", "high", "high_zh"; fingerprints live in <project>/.render_state.json.
A scene's fingerprint covers: its own class code, the module-level code of its scenes file, the project's helper
modules (zh.py only for PVP_LANG=zh), engine/common.py, its narration audio + timings, VERTICAL, figures/.
Missing rendered output also counts as stale.
"""
import hashlib, json, os, re, sys
from pathlib import Path

ENGINE = Path(__file__).resolve().parent
proj = Path(sys.argv[1]).resolve()
state, cmd, scenes = sys.argv[2], sys.argv[3], sys.argv[4:]
lang = os.environ.get("PVP_LANG", "")
sfx = f"_narration_{lang}" if lang else ""
CLASS = re.compile(r"^class (\w+)\(", re.M)
SKIP = {"zh.py"} if not lang else set()


def h(*parts):
    m = hashlib.sha1()
    for p in parts:
        m.update(p if isinstance(p, bytes) else str(p).encode())
        m.update(b"\0")
    return m.hexdigest()


def blocks(text):
    pos = [(m.start(), m.group(1)) for m in CLASS.finditer(text)]
    module = text[:pos[0][0]] if pos else text
    return module, {name: text[st:(pos[i + 1][0] if i + 1 < len(pos) else len(text))] for i, (st, name) in enumerate(pos)}


scene_src = {}                       # scene -> (module code of its file, its class block)
for f in sorted(proj.glob("scenes*.py")):
    module, cls = blocks(f.read_text(encoding="utf-8"))
    for name, b in cls.items():
        scene_src[name] = (module, b)

helpers = [f for f in sorted(proj.glob("*.py")) if not f.name.startswith(("scenes", "narration", "listen"))
           and f.name not in SKIP]
figs = sorted(p for p in (proj / "figures").rglob("*") if p.is_file()) if (proj / "figures").is_dir() else []
shared = h((ENGINE / "common.py").read_bytes(), lang, (proj / "VERTICAL").exists(),
           *[f.name.encode() + f.read_bytes() for f in helpers],
           *[str(p.relative_to(proj)).encode() + p.read_bytes() for p in figs])
dpath = proj / f"durations{sfx}.json"
durs = json.loads(dpath.read_text()) if dpath.exists() else {}


def fp(scene):
    if scene not in scene_src:
        return None
    audio = sorted((proj / f"audio{sfx}").glob(f"{scene}_*.wav"))
    return h(shared, *scene_src[scene], json.dumps(durs.get(scene)), *[a.read_bytes() for a in audio])


def rendered(scene):
    return any((proj / f"media_{state}" / scene / "videos").glob(f"*/*/{scene}.mp4"))


spath = proj / ".render_state.json"
saved = json.loads(spath.read_text()) if spath.exists() else {}
if cmd == "stale":
    old = saved.get(state, {})
    print(" ".join(s for s in scenes if fp(s) is None or old.get(s) != fp(s) or not rendered(s)))
elif cmd == "mark":
    saved.setdefault(state, {}).update({s: fp(s) for s in scenes if fp(s)})
    spath.write_text(json.dumps(saved, indent=1))
else:
    sys.exit("usage: fingerprint.py <project> <state> stale|mark <Scene ...>")
