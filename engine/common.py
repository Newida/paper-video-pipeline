import json
from pathlib import Path
from manim import *
from PIL import Image as _PILImage

# manim 0.22 + Pillow 13: camera.display_image_mobject calls fromarray(2-D float zeros, mode="RGBA"),
# which Pillow now rejects (ImageMobject crashes). Return the blank transparent canvas it meant to build.
_fromarray = _PILImage.fromarray


def _fromarray_compat(obj, mode=None):
    if mode == "RGBA" and getattr(obj, "ndim", 0) == 2:
        return _PILImage.new("RGBA", (obj.shape[1], obj.shape[0]), (0, 0, 0, 0))
    return _fromarray(obj) if mode is None else _fromarray(obj, mode)


_PILImage.fromarray = _fromarray_compat

import os

# The project folder (narration, audio, durations) is passed in by render.sh.
PROJ = Path(os.environ["PVP_PROJECT"])
# Portrait output (VERTICAL projects): manim keeps frame_width=14.2 and stretches the height, so pin
# the frame to 8 tall and derive the width (4.5 for 9:16) instead.
if config.pixel_height > config.pixel_width:
    config.frame_height = 8.0
    config.frame_width = 8.0 * config.pixel_width / config.pixel_height
LANG = os.environ.get("PVP_LANG", "")          # "" = English, "zh" = Mandarin
_SFX = f"_narration_{LANG}" if LANG else ""   # matches tts.py: narration_zh.py -> audio_narration_zh/
AUDIO = PROJ / ("audio" + _SFX)

# Mandarin: on-screen strings are translated through the project's zh.py (dict ZH: English -> Chinese).
ZH = {}
if LANG == "zh" and (PROJ / "zh.py").exists():
    import importlib.util as _ilu
    _s = _ilu.spec_from_file_location("zh", PROJ / "zh.py"); _m = _ilu.module_from_spec(_s); _s.loader.exec_module(_m)
    ZH = _m.ZH


def tr(s):
    """Translate an on-screen string for the current language; log misses so none slip through."""
    if LANG != "zh":
        return s
    if s in ZH:
        return ZH[s]
    import re
    if re.search(r"[A-Za-z]{2,}", s) and not re.fullmatch(r"[A-Z ]{1,3}|[0-9 .,%/:x×+\-]*", s):
        (PROJ / "logs").mkdir(exist_ok=True)
        with open(PROJ / "logs" / "zh_missing.txt", "a") as f:
            f.write(repr(s) + "\n")
    return s

BG = "#0f1117"
INK = "#e8e8ea"
DIM = "#8a8f98"
C_X = "#58C4DD"      # data / inputs
C_Y = "#83C167"      # truth / good
C_F = "#FFD166"      # highlights
C_BAD = "#FC6255"    # surprise / bad
C_P = "#FF9F43"      # true distribution p
C_Q = "#4ECDC4"      # network prediction q
C_ANC = "#B39DDB"    # prior / rules
SANS = "Noto Sans CJK SC" if os.environ.get("PVP_LANG") == "zh" else "DejaVu Sans"
MONO = "DejaVu Sans Mono"

MathTex.set_default(color=INK)
Tex.set_default(color=INK)
Text.set_default(font=SANS, color=INK)


def T(s, size=30, **kw):
    t = Text(tr(s), font_size=size, **kw)
    wmax = config.frame_width * 0.92
    if t.width > wmax:
        t.scale_to_fit_width(wmax)
    return t


def M(*parts, size=48, **kw):
    if LANG and any(p in ZH for p in parts):
        # Chinese can't go through LaTeX here: translated parts become Text, the rest stays MathTex.
        col = kw.get("color", INK)
        m = VGroup(*[Text(ZH[p], font_size=size * 0.62, color=col) if p in ZH else MathTex(p, font_size=size, color=col)
                     for p in parts]).arrange(RIGHT, buff=0.12)
        if m.width > config.frame_width * 0.9:
            m.scale_to_fit_width(config.frame_width * 0.9)
        return m
    if LANG == "zh":
        for p in parts:
            if "\\text" in p:
                (PROJ / "logs").mkdir(exist_ok=True)
                with open(PROJ / "logs" / "zh_missing.txt", "a") as f:
                    f.write("M " + repr(p) + "\n")
    m = MathTex(*parts, font_size=size, **kw)
    if m.width > config.frame_width * 0.9:
        m.scale_to_fit_width(config.frame_width * 0.9)
    return m


def eqno(mob, n):
    lab = T(f"({n})", 24, color=DIM)
    lab.next_to(mob, RIGHT, buff=0.5)
    return lab


def card(text, color=C_X, w=3.2, h=1.0, size=26):
    box = RoundedRectangle(corner_radius=0.15, width=w, height=h, stroke_color=color,
                           fill_color=color, fill_opacity=0.12, stroke_width=2.5)
    t = T(text, size)
    if t.width > w - 0.3:
        t.scale_to_fit_width(w - 0.3)
    return VGroup(box, t.move_to(box))


def bullets(lines, size=28, buff=0.32, color=INK):
    g = VGroup(*[T(l, size, color=color) for l in lines])
    g.arrange(DOWN, aligned_edge=LEFT, buff=buff)
    return g


def label_brace(mob, text, direction=DOWN, color=C_F, size=22):
    b = Brace(mob, direction, color=color, buff=0.1)
    lab = T(text, size, color=color)
    lab.next_to(b, direction, buff=0.12)
    return VGroup(b, lab)


def bars(ax, xs, hs, width, color, opacity=0.6):
    """Histogram bars on axes: xs = centers, hs = heights (axis units)."""
    return VGroup(*[Rectangle(width=ax.x_length / (ax.x_range[1] - ax.x_range[0]) * width * 0.94,
                              height=max(ax.y_length * h / (ax.y_range[1] - ax.y_range[0]), 0.001),
                              stroke_width=0, fill_color=color, fill_opacity=opacity)
                    .move_to(ax.c2p(x, 0), aligned_edge=DOWN) for x, h in zip(xs, hs)])


DUR = json.loads((PROJ / f"durations{_SFX}.json").read_text())


class NScene(Scene):
    def setup(self):
        self.camera.background_color = BG
        self.key = type(self).__name__
        self._i = -1
        self._t0 = None
        self._d = 0
        self.hdr = None

    def say(self, i=None):
        """Start narration segment i (default: next), first padding out the previous one."""
        self.finish()
        self._i = self._i + 1 if i is None else i
        self._d = DUR[self.key][self._i]
        self.add_sound(str(AUDIO / f"{self.key}_{self._i}.wav"))
        self._t0 = self.renderer.time

    def at(self, frac):
        """Wait until `frac` of the current segment's audio has elapsed."""
        if self._t0 is None:
            return
        rem = self._t0 + frac * self._d - self.renderer.time
        if rem > 0.03:
            self.wait(rem)

    def finish(self, pad=0.3):
        if self._t0 is not None:
            self.at(1.0)
            self.wait(pad)
            self._t0 = None

    def header(self, num, title):
        n = T(num, 22, color=C_F, weight=BOLD)
        t = T(title, 30, weight=BOLD)
        g = VGroup(n, t).arrange(RIGHT, buff=0.25).to_corner(UL, buff=0.45)
        line = Line(g.get_corner(DL) + DOWN * 0.12, g.get_corner(DR) + DOWN * 0.12, color=C_F, stroke_width=2)
        self.play(FadeIn(g, shift=RIGHT * 0.2), Create(line), run_time=0.8)
        self.remove(g, line)
        self.hdr = VGroup(g, line)
        self.add(self.hdr)
        return self.hdr

    def clear_body(self, run_time=0.6):
        mobs = [m for m in self.mobjects if m is not self.hdr]
        if mobs:
            self.play(*[FadeOut(m) for m in mobs], run_time=run_time)

    def end(self):
        self.finish(pad=0.4)
        self.play(*[FadeOut(m) for m in self.mobjects], run_time=0.7)


def code_box(lines, w=5.6, color=C_ANC, size=20, hl=None):
    """Monospace code panel; `hl` = indices of lines to highlight. Keeps indentation."""
    indents = [len(l) - len(l.lstrip(" ")) for l in lines]
    txt = VGroup(*[Text(l.strip(" "), font=MONO, font_size=size, color=INK) for l in lines]).arrange(DOWN, aligned_edge=LEFT, buff=0.12)
    cw = Text("M" * 10, font=MONO, font_size=size).width / 10
    for t, n in zip(txt, indents):
        t.shift(RIGHT * n * cw)
    for i in (hl or []):
        txt[i].set_color(C_F)
    box = RoundedRectangle(corner_radius=0.12, width=max(w, txt.width + 0.5), height=txt.height + 0.5,
                           stroke_color=color, fill_color="#1a1d26", fill_opacity=1, stroke_width=2)
    txt.move_to(box)
    return VGroup(box, txt)
