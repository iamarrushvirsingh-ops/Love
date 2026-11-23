"""
bloom.py  -  a glowing particle flower
======================================
A wilted grey flower lifts itself up, turns glowing blue and blooms into a
lotus inside a sphere of light circles... then closes, shrinks back into a
bud and sinks into the soil. Loops forever.

Everything is drawn from ~20,000 particles with an additive glow.

Controls:  SPACE / R = replay    ESC / Q = quit
Requires:  pip install pygame numpy
"""

import argparse
import math
import os

import numpy as np
import pygame

# ============== customize me ==============
WINDOW_TITLE = "bloom"
SIZE = 900                      # window is SIZE x SIZE (multiple of 4)
PETAL_OUTER = (40, 70, 255)     # bloom colours
PETAL_INNER = (175, 120, 255)
PETAL_HEART = (255, 200, 225)
STEM_COLOR = (70, 150, 255)
LEAF_COLOR = (40, 140, 255)
WILT_HEAD = (150, 140, 205)     # wilted colours
WILT_BODY = (190, 180, 160)
CYCLE = 11.5                    # seconds per loop
# ==========================================

W = H = SIZE
GROUND = int(H * 0.80)
BASE_X = W // 2 - 10


def sstep(x):
    x = min(max(x, 0.0), 1.0)
    return x * x * (3 - 2 * x)


def lerp(a, b, t):
    return a + (b - a) * t


def rot(x, y, th):
    """rotate vectors; th measured clockwise from 'up' on screen."""
    c, s = np.cos(th), np.sin(th)
    return x * c - y * s, x * s + y * c


class Flower:
    def __init__(self, seed=7):
        rng = np.random.default_rng(seed)
        self.rng = rng

        # ---- stem: param s along stem, w across ----
        n = 1600
        self.stem_s = rng.random(n)
        self.stem_w = rng.uniform(-1, 1, n) * 3.2

        # ---- leaves: two pairs ----
        leaves = []
        for k, (s_at, side) in enumerate(((0.08, -1), (0.10, 1), (0.36, -1), (0.38, 1))):
            m = 3200
            u = rng.random(m)
            v = rng.uniform(-1, 1, m)
            side_vein = np.abs(np.mod(u * 7 - np.abs(v) * 1.6, 1.0) - 0.5) > 0.44
            keep = (np.abs(v) > 0.82) | (np.abs(v) < 0.07) | side_vein | (rng.random(m) < 0.28)
            u, v = u[keep][:1100], v[keep][:1100]
            vein = (np.abs(v) < 0.07)
            leaves.append((s_at, side, u, v, vein, 0.9 + 0.2 * (k >= 2)))
        self.leaves = leaves

        # ---- petals: three layers fanning out (front view lotus) ----
        petals = []
        for layer, (count, length, width, fan, pts) in enumerate((
                (7, 1.00, 0.42, 84, 560),
                (6, 0.80, 0.40, 55, 480),
                (5, 0.58, 0.36, 26, 360))):
            for j in range(count):
                phi0 = math.radians(lerp(-fan, fan, j / (count - 1)))
                m = pts * 3
                u = rng.random(m) ** 0.6
                v = rng.uniform(-1, 1, m)
                keep = (np.abs(v) > 0.86) | (np.abs(v) < 0.06) | (rng.random(m) < 0.42)
                u, v = u[keep][:pts], v[keep][:pts]
                petals.append((layer, phi0, length, width, u, v))
        self.petals = petals
        # heart of the flower
        m = 250
        a = rng.random(m) * 6.283
        r = np.sqrt(rng.random(m))
        self.heart = (r * np.cos(a), r * np.sin(a))

        # ---- sphere (flower-of-life circles) ----
        circ = []
        for i in range(900):                       # outer ring
            a = rng.random() * 6.283
            circ.append((math.cos(a), math.sin(a)))
        centers = [(0, 0)] + [(0.5 * math.cos(k * math.pi / 3), 0.5 * math.sin(k * math.pi / 3))
                              for k in range(6)]
        for cx, cy in centers:
            for i in range(260):
                a = rng.random() * 6.283
                circ.append((cx + 0.5 * math.cos(a), cy + 0.5 * math.sin(a)))
        for i in range(500):                       # dust inside
            a = rng.random() * 6.283
            r = math.sqrt(rng.random())
            circ.append((r * math.cos(a), r * math.sin(a)))
        self.sphere = np.array(circ)
        self.sphere_b = np.concatenate([np.full(900, 1.0), np.full(260 * 7, 0.7), np.full(500, 0.35)])
        self.sphere_tw = rng.random(len(circ)) * 6.283

        # ---- soil ----
        m = 11000
        sx = rng.uniform(-W * 0.42, W * 0.42, m)
        top = -20 * np.exp(-(sx / 220) ** 2) + rng.normal(0, 3, m)
        depth = rng.random(m) ** 1.8 * 80
        self.soil_x = BASE_X + sx
        self.soil_y = GROUND + top + depth
        shade = rng.uniform(0.25, 1.0, m) * (1 - depth / 110)
        col = np.stack([shade * 140, shade * 128, shade * 120], 1)
        specks = rng.random(m) < 0.05
        col[specks] = 230
        self.soil_c = col
        self.soil_tw = rng.random(m) * 6.283

        self.spark = np.zeros((0, 6))   # x, y, vx, vy, age, life

    # ------------------------------------------------------------------
    def state(self, t):
        fade = sstep(t / 0.8)
        revive = sstep((t - 1.3) / 2.0)
        o = lerp(0.38, 1.0, sstep((t - 2.0) / 1.6))
        o = lerp(o, 0.03, sstep((t - 6.0) / 1.5))
        g = 1 - sstep((t - 7.0) / 2.7)
        sphere = sstep((t - 2.3) / 1.2) * (1 - sstep((t - 6.4) / 3.0))
        return dict(fade=fade, b=1 - revive, h=revive, o=o, g=g, sphere=sphere)

    def points(self, t, st):
        """returns xs, ys, colours(N,3), and glow centre"""
        b, h, o, g = st["b"], st["h"], st["o"], st["g"]
        if g < 0.015:
            return None
        xs, ys, cs = [], [], []
        sway = 0.035 * math.sin(t * 1.3) * h

        # stem centre line
        K = 160
        ss = np.linspace(0, 1, K)
        theta = b * 2.55 * ss ** 1.6 + sway * ss
        Hs = 300 * g
        dx = np.sin(theta) * Hs / (K - 1)
        dy = -np.cos(theta) * Hs / (K - 1)
        cx = BASE_X + np.concatenate([[0], np.cumsum(dx[:-1])])
        cy = GROUND + np.concatenate([[0], np.cumsum(dy[:-1])])

        def stem_at(s):
            i = s * (K - 1)
            return np.interp(i, np.arange(K), cx), np.interp(i, np.arange(K), cy), \
                np.interp(i, np.arange(K), theta)

        body = np.array(WILT_BODY) * (1 - h)
        # stem
        sx_, sy_, sth = stem_at(self.stem_s)
        ox, oy = rot(self.stem_w, 0 * self.stem_w, sth)
        xs.append(sx_ + ox)
        ys.append(sy_ + oy)
        cs.append(np.tile(body + np.array(STEM_COLOR) * h, (len(sx_), 1)) * 1.1)

        # leaves
        for s_at, side, u, v, vein, big in self.leaves:
            px, py, pth = stem_at(np.array([s_at]))
            ang = side * lerp(math.radians(62), math.radians(118), b) + pth[0] * 0.5
            L = 92 * g * big
            Wl = 36 * g * big
            w_u = np.sin(np.pi * u) ** 0.9
            lx = v * w_u * Wl
            ly = -u * L
            # slight curl
            lx = lx + side * 0.18 * L * u * u * (1 - b) - side * 0.25 * L * u * u * b
            rx, ry = rot(lx, ly, ang)
            xs.append(px[0] + rx)
            ys.append(py[0] + ry)
            base = body + np.array(LEAF_COLOR) * h
            col = np.tile(base, (len(u), 1))
            col[vein] = body * 1.2 + np.array((150, 220, 255)) * h
            cs.append(col)

        # head
        hx, hy, hth = stem_at(np.array([1.0]))
        hx, hy, hth = hx[0], hy[0], hth[0]
        Lh = 150 * (0.35 + 0.65 * g) * (0.75 + 0.25 * o)
        for layer, phi0, length, width, u, v in self.petals:
            phi = phi0 * (0.1 + 0.9 * o)
            L = Lh * length
            Wd = Lh * width * (0.7 + 0.3 * o)
            w_u = np.sin(np.pi * np.clip(u, 0, 1) ** 0.75) ** 0.9
            # local petal frame (up = along petal)
            plx = v * w_u * Wd
            ply = -u * L
            px_, py_ = rot(plx, ply, phi)
            py_ = py_ * (0.78 + 0.1 * layer) + layer * 6      # front-view squash
            px_, py_ = rot(px_, py_, hth)
            xs.append(hx + px_)
            ys.append(hy + py_)
            if layer == 0:
                bloom = np.array(PETAL_OUTER)
            elif layer == 1:
                bloom = (np.array(PETAL_OUTER) + np.array(PETAL_INNER)) / 2
            else:
                bloom = np.array(PETAL_INNER)
            uu = u[:, None]
            bloom_c = bloom * (0.75 + 0.5 * uu) + np.array(PETAL_HEART) * (1 - uu) ** 3 * 0.8
            edge = (np.abs(v) > 0.86)[:, None]
            col = np.array(WILT_HEAD) * (1 - h) + bloom_c * h
            col = col * np.where(edge, 1.25, 1.0)
            cs.append(col)
        # heart
        hrx, hry = self.heart
        r = Lh * 0.22 * (0.4 + 0.6 * o)
        px_, py_ = rot(hrx * r, hry * r * 0.6 - Lh * 0.18 * o, hth)
        xs.append(hx + px_)
        ys.append(hy + py_)
        cs.append(np.tile(np.array(WILT_HEAD) * (1 - h) + np.array((255, 220, 190)) * h * 0.6, (len(hrx), 1)))

        # glow centre = middle of the open flower
        gx, gy = rot(np.array([0.0]), np.array([-Lh * 0.45]), hth)
        centre = (hx + gx[0], hy + gy[0])
        return np.concatenate(xs), np.concatenate(ys), np.concatenate(cs), centre, Lh


class Renderer:
    """Collects glowing points, then draws them with a soft bloom."""

    def __init__(self):
        self.items = []
        self.surf = pygame.Surface((W, H))
        self.tmp = pygame.Surface((W, H))

    def splat(self, xs, ys, cs, k):
        self.items.append((np.asarray(xs), np.asarray(ys), np.asarray(cs, np.float32) * k))

    def finish(self, screen, glow):
        xs = np.concatenate([i[0] for i in self.items])
        ys = np.concatenate([i[1] for i in self.items])
        cs = np.concatenate([i[2] for i in self.items])
        self.items = []
        xi = xs.astype(np.int32)
        yi = ys.astype(np.int32)
        m = (xi >= 0) & (xi < W) & (yi >= 0) & (yi < H)
        idx = xi[m] * H + yi[m]            # column-major to match surfarray (W, H)
        c = cs[m]
        img = np.empty((W * H, 3), np.float32)
        for ch in range(3):
            img[:, ch] = np.bincount(idx, weights=c[:, ch], minlength=W * H)
        np.minimum(img, 255, out=img)
        pygame.surfarray.blit_array(self.surf, img.reshape(W, H, 3).astype(np.uint8))
        screen.blit(self.surf, (0, 0))
        # bloom: blur by down/up-scaling, then add on top
        small = pygame.transform.smoothscale(self.surf, (W // 6, H // 6))
        small = pygame.transform.smoothscale(small, (W // 12, H // 12))
        small = pygame.transform.smoothscale(small, (W // 6, H // 6))
        g = pygame.transform.smoothscale(small, (W, H))
        k = int(min(255, 150 + 105 * glow))
        g.fill((k, k, k), special_flags=pygame.BLEND_RGB_MULT)
        for _ in range(1 + int(glow * 2)):
            screen.blit(g, (0, 0), special_flags=pygame.BLEND_RGB_ADD)


def frame(screen, flower, rend, t, dt, rng):
    st = flower.state(t)
    fade = st["fade"]

    # soil
    tw = 0.75 + 0.25 * np.sin(t * 2 + flower.soil_tw)
    rend.splat(flower.soil_x, flower.soil_y, flower.soil_c * tw[:, None] * fade, 0.7)

    res = flower.points(t, st)
    if res is not None:
        xs, ys, cs, (gx, gy), Lh = res
        k = (0.45 + 0.35 * st["h"]) * fade
        rend.splat(xs + rng.normal(0, 0.4, len(xs)), ys + rng.normal(0, 0.4, len(ys)), cs, k)

        # sphere
        sp = st["sphere"]
        if sp > 0.01:
            R = (1.55 * Lh + 40) * (0.6 + 0.4 * sp)
            a = t * 0.15
            c, s = math.cos(a), math.sin(a)
            p = flower.sphere
            px = p[:, 0] * c - p[:, 1] * s
            py = p[:, 0] * s + p[:, 1] * c
            tw = 0.55 + 0.45 * np.sin(t * 3 + flower.sphere_tw)
            col = np.array((150, 160, 255))[None, :] * (flower.sphere_b * tw)[:, None]
            rend.splat(gx + px * R, gy + py * R + 10, col, 0.9 * sp * fade)

        # sparkles
        if st["h"] > 0.5 and st["g"] > 0.3:
            n = rng.poisson(70 * dt)
            if n:
                a = rng.random(n) * 6.283
                r = np.sqrt(rng.random(n)) * Lh * 1.3
                new = np.stack([gx + r * np.cos(a), gy + r * np.sin(a),
                                rng.normal(0, 8, n), -rng.uniform(10, 40, n),
                                np.zeros(n), rng.uniform(0.8, 2.0, n)], 1)
                flower.spark = np.concatenate([flower.spark, new])
    sp_ = flower.spark
    if len(sp_):
        sp_[:, 0] += sp_[:, 2] * dt
        sp_[:, 1] += sp_[:, 3] * dt
        sp_[:, 4] += dt
        flower.spark = sp_ = sp_[sp_[:, 4] < sp_[:, 5]]
        k = (1 - sp_[:, 4] / sp_[:, 5])[:, None]
        rend.splat(sp_[:, 0], sp_[:, 1], np.array((200, 210, 255)) * k * 3, 1.0)

    rend.finish(screen, st["h"] * st["g"] * fade)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--record", help="save PNG frames to this folder (no window needed)")
    args = ap.parse_args()
    if args.record:
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    pygame.display.init()
    screen = pygame.display.set_mode((W, H))
    pygame.display.set_caption(WINDOW_TITLE)

    flower = Flower()
    rend = Renderer()
    rng = np.random.default_rng()
    clock = pygame.time.Clock()
    t = 0.0

    if args.record:
        os.makedirs(args.record, exist_ok=True)
        i = 0
        while t < CYCLE:
            t += 1 / 30
            frame(screen, flower, rend, t, 1 / 30, rng)
            if i % 15 == 0:
                pygame.image.save(screen, os.path.join(args.record, f"t{t:05.2f}.png"))
            i += 1
        return

    running = True
    while running:
        dt = min(clock.tick(60) / 1000.0, 1 / 20)
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                running = False
            elif ev.type == pygame.KEYDOWN:
                if ev.key in (pygame.K_ESCAPE, pygame.K_q):
                    running = False
                elif ev.key in (pygame.K_SPACE, pygame.K_r):
                    t = 0.0
        t += dt
        if t > CYCLE:
            t = 0.0
            flower.spark = flower.spark[:0]
        frame(screen, flower, rend, t, dt, rng)
        pygame.display.flip()
    pygame.quit()


if __name__ == "__main__":
    main()
