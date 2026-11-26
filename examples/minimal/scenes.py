import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from common import *


class S01_Intro(NScene):
    def construct(self):
        self.header("1", "Hello, pipeline")
        # beat 0
        self.say()
        c = card("one narration beat", C_X, 5.0, 1.0, 30)
        self.play(FadeIn(c, shift=UP * 0.2))
        self.at(0.6)
        eq = M(r"E = mc^2", size=56, color=C_F).next_to(c, DOWN, buff=0.6)
        self.play(Write(eq))
        # beat 1
        self.say()
        self.clear_body()
        d = Dot(LEFT * 4, color=C_Y, radius=0.15)
        lab = T("animations follow the voice", 30, color=C_Y).to_edge(DOWN, buff=1.0)
        self.play(FadeIn(d), FadeIn(lab))
        self.at(0.5)
        self.play(d.animate.move_to(RIGHT * 4), run_time=self._d * 0.4)
        self.end()
