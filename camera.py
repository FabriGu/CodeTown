"""Camera focus easing (v3 section 2)."""

import math

EASE = 6.5
EPS = 0.05


class Camera:
    def __init__(self, focus=(0.0, 0.0)):
        self.focus = [float(focus[0]), float(focus[1])]
        self.target = [float(focus[0]), float(focus[1])]

    def set_target(self, x, y):
        self.target[0], self.target[1] = float(x), float(y)

    def jump(self, x, y):
        self.focus[0] = self.target[0] = float(x)
        self.focus[1] = self.target[1] = float(y)

    def gliding(self):
        return (abs(self.focus[0] - self.target[0]) > EPS
                or abs(self.focus[1] - self.target[1]) > EPS)

    def step(self, dt):
        if dt <= 0:
            return self.gliding()
        t = 1 - math.exp(-EASE * dt)
        for i in range(2):
            self.focus[i] += (self.target[i] - self.focus[i]) * t
        return self.gliding()
