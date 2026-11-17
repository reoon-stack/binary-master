"""レシピ(Dish)から 30 秒のドット絵料理動画を作るエンジン。

時間割(全料理共通):
   0- 3s  スポットライトで材料の一部だけ見せる
   3- 9s  2 種類の食材を刻み、まな板の端から鍋へ落とす(カメラがコンロへパン)
  10-19s  レシピの steps を順番に実行
  19-24s  鍋ごと器へ運んで盛り付け(湯気で全体はまだ見せない)
  24-30s  湯気が晴れ、仕上げ → 「何の料理か わかった？」
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageDraw

from . import gfx
from .gfx import (CROP_X, CROP_Y, LH, LW, VH, VW, add_outline, clamp, draw_hand, draw_text, ease,
                  lerp, lerp2, lerpc, paste, paste_shadow, prog, shadow_of, smooth, wood)
from .ingredients import EXTRAS, GRAIN_KINDS, INGS, egg_sprite

DURATION = 30.0

# ワールド座標の配置
ING1_0, ING1_C = (95, 215), (128, 232)
ING2_0, ING2_C = (80, 335), (126, 256)
EXTRA_POS = (214, 138)
PILE1, PILE2 = (200, 168), (192, 246)
GATHER = (135, 386)
PLATE_C = (135, 1215)
CUT1 = (3.5, 5.6, 11)
CUT2 = (6.45, 7.7, 7)
COOK_START = 10.4
STIR_SPEED = math.tau / 0.75


@dataclass
class Theme:
    board: tuple = (226, 184, 128)
    counter: tuple = (166, 112, 70)
    mat: tuple = ((238, 232, 220), (206, 92, 80), (226, 160, 148))
    sleeve: tuple = ((205, 150, 72), (170, 116, 52), (96, 60, 30))
    accent: tuple = (84, 118, 186)


THEMES = [
    Theme(),
    Theme((214, 170, 112), (140, 96, 64), ((236, 236, 226), (80, 120, 180), (164, 186, 214)),
          ((96, 130, 170), (70, 100, 140), (40, 56, 80)), (180, 70, 60)),
    Theme((232, 196, 146), (176, 128, 84), ((240, 236, 224), (96, 150, 96), (176, 204, 160)),
          ((210, 110, 110), (176, 84, 84), (100, 44, 44)), (60, 130, 90)),
    Theme((220, 178, 120), (120, 84, 60), ((244, 230, 200), (220, 160, 60), (234, 200, 140)),
          ((110, 150, 110), (84, 120, 84), (44, 70, 44)), (200, 120, 40)),
]


class Step:
    def __init__(self, raw, a):
        self.kind = raw[0]
        self.raw = raw
        dur = {"add": 2, "liquid": 3, "sauce": 4}.get(self.kind, 1)
        self.a, self.b = a, a + raw[dur]


class Scene:
    def __init__(self, dish, theme: Theme, seed: int = 0):
        self.d = dish
        self.th = theme
        self.rng = np.random.default_rng(seed + 11)
        gfx.STYLE["sleeve"] = theme.sleeve
        self.ing1, self.ing2 = INGS[dish.chop[0]](), INGS[dish.chop[1]]()
        kind, name = dish.extra
        self.extra_sprite = EXTRAS[name]() if kind == "extra" else INGS[name]().sprite
        self.egg = egg_sprite()
        self.knife = gfx.knife_sprite()
        self.spatula = gfx.spatula_sprite()
        self.ladle = gfx.ladle_sprite()
        self.chop_sticks = gfx.chopsticks_sprite()

        self.pot = dish.vessel == "pot"
        self.has_egg_pan = any(s[0] == "egg_sheet" for s in dish.steps)
        self.V0 = (135, 640) if self.has_egg_pan else (135, 690)
        self.E0 = (150, 800)
        self.vr = 72 if self.pot else 78
        self.vessel, self.vpts = gfx.vessel_sprite(dish.vessel, self.vr, (-0.5, 0.866), 52)
        self.inner = self.vr - 12
        self.egg_pan, self.epts = gfx.vessel_sprite("pan", 52, (0.5, 0.866), 44)

        cont, self.transfer, self.rice_base = dish.serve
        self.container, self.cr = gfx.container_sprite(cont, theme.accent)

        # 工程の時刻を決める
        self.steps, t = [], COOK_START
        for raw in dish.steps:
            st = Step(raw, t)
            self.steps.append(st)
            t = st.b + 0.1
        self.stirs = [(s.a, s.b) for s in self.steps if s.kind in ("stir",)]
        self.shape = next((s for s in self.steps if s.kind == "shape"), None)
        self.egg_sheet = next((s for s in self.steps if s.kind == "egg_sheet"), None)
        self.egg_pour = next((s for s in self.steps if s.kind == "egg_pour"), None)
        self.cook_end = max(s.b for s in self.steps)
        self.noodles = any(s.kind == "add" and GRAIN_KINDS[s.raw[1]].style == "strand" for s in self.steps)

        self._make_tints()
        self._make_liquid()
        self._make_pieces()
        self._make_grains()
        self._make_egg_patches()
        self._make_steam()
        self.world = self._make_world()

    # ------------------------------------------------------------ 準備

    def _make_tints(self):
        """ソースやルウが入った時刻と、混ざり終わる時刻。"""
        self.tints = []
        for i, s in enumerate(self.steps):
            grain_c = liquid_c = None
            if s.kind == "sauce":
                grain_c, liquid_c = s.raw[2], s.raw[3]
            elif s.kind == "add" and len(s.raw) > 3:
                liquid_c = s.raw[3]
            else:
                continue
            nxt = self.steps[i + 1] if i + 1 < len(self.steps) else None
            end = nxt.b if nxt else s.b + 1.0
            self.tints.append((s.b - 0.1, end, grain_c, liquid_c))

    def tint(self, t, which):
        """(色, 割合) 最新のものを返す。"""
        col, p = None, 0.0
        for a, b, gc, lc in self.tints:
            c = gc if which == "grain" else lc
            if c is not None and t >= a:
                col, p = c, ease(t, a, b)
        return col, p

    def _make_liquid(self):
        self.liquid_steps = [s for s in self.steps if s.kind == "liquid"]
        self.boil_from = None
        if self.liquid_steps:
            self.boil_from = self.liquid_steps[0].b + 0.3

    def liquid_level(self, t):
        if not self.liquid_steps:
            return 0.0
        lv = 0.0
        for s in self.liquid_steps:
            lv = max(lv, s.raw[2] * ease(t, s.a + 0.2, s.b))
        return lv

    def liquid_color(self, t):
        if not self.liquid_steps:
            return None
        base = self.liquid_steps[0].raw[1]
        col, p = self.tint(t, "liquid")
        return lerpc(base, col, p) if col else base

    def _make_pieces(self):
        rng = self.rng
        self.pieces = []
        for idx, (ing, c, pile) in enumerate(((self.ing1, ING1_C, PILE1), (self.ing2, ING2_C, PILE2))):
            w, h = ing.sprite.size
            for _ in range(ing.count):
                a, rr = rng.uniform(0, math.tau), math.sqrt(rng.random())
                mr = rng.uniform(0, math.tau), math.sqrt(rng.random())
                self.pieces.append(dict(
                    ing=ing, which=idx,
                    spawn=(c[0] + 0.4 * w * rr * math.cos(a), c[1] + 0.4 * h * rr * math.sin(a)),
                    pile=(pile[0] + rng.normal(0, 7), pile[1] + rng.normal(0, 5)),
                    gather=(GATHER[0] + rng.normal(0, 12), GATHER[1] + rng.normal(0, 4)),
                    r=rng.uniform(4, 0.72 * self.inner), a=rng.uniform(0, math.tau),
                    k=rng.uniform(0.18, 0.4), wob=rng.uniform(0, math.tau),
                    rel=(mr[1] * math.cos(mr[0]), mr[1] * math.sin(mr[0])),
                    delay=rng.uniform(0, 0.45), brown=rng.random() < 0.4,
                    vert=rng.random() < 0.5))

    def _make_grains(self):
        rng = self.rng
        self.grains = []
        for s in self.steps:
            if s.kind != "add":
                continue
            gk = GRAIN_KINDS[s.raw[1]]
            for _ in range(gk.count):
                mr = rng.uniform(0, math.tau), math.sqrt(rng.random())
                self.grains.append(dict(
                    gk=gk, step=s, t0=rng.uniform(s.a + 0.3, s.b - 0.05),
                    r=rng.uniform(2, 0.8 * self.inner), a=rng.uniform(0, math.tau),
                    k=rng.uniform(0.15, 0.4), wob=rng.uniform(0, math.tau),
                    mix=rng.uniform(0, 0.8), ang=rng.uniform(0, math.pi),
                    rel=(mr[1] * math.cos(mr[0]), mr[1] * math.sin(mr[0])),
                    vert=rng.random() < 0.4))

    def _make_egg_patches(self):
        self.patches = []
        if not self.egg_pour:
            return
        rng = self.rng
        for _ in range(30):
            a, rr = rng.uniform(0, math.tau), rng.uniform(0, 0.68 * self.inner)
            self.patches.append(dict(dx=rr * math.cos(a), dy=rr * math.sin(a),
                                     t0=rng.uniform(self.egg_pour.a + 0.2, self.egg_pour.b),
                                     rx=rng.uniform(3, 7), ry=rng.uniform(2, 5),
                                     yolk=rng.random() < 0.45))

    def _make_steam(self):
        rng = self.rng
        self.steam = []
        egg_a = self.egg_sheet.a + 0.6 if self.egg_sheet else None
        spans = [(10.2, 20.4, 26, "v", 46), (20.4, 25.6, 70, "plate", 70), (25.6, 30, 10, "plate", 40)]
        if egg_a:
            spans.append((egg_a, 21.9, 18, "e", 34))
        for (a, b, rate, src, spread) in spans:
            for _ in range(int((b - a) * rate)):
                self.steam.append(dict(t0=rng.uniform(a, b), src=src, dx=rng.normal(0, spread / 2.2),
                                       dy=rng.normal(0, spread / 4), life=rng.uniform(1.4, 2.4),
                                       size=int(rng.integers(2, 6)), ph=rng.uniform(0, math.tau),
                                       big=src == "plate" and a < 25))

    # ------------------------------------------------------------ 背景

    def _make_world(self):
        th = self.th
        world = Image.new("RGBA", (LW, gfx.WORLD_H))
        world.alpha_composite(wood(LW, gfx.WORLD_H, th.counter, plank=24, seed=3).convert("RGBA"))
        d = ImageDraw.Draw(world)
        board = Image.new("RGBA", (210, 310))
        bw = wood(210, 310, th.board, plank=310, seed=5, vertical=True).convert("RGBA")
        mask = Image.new("L", (210, 310))
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, 209, 309), 12, fill=255)
        board.paste(bw, (0, 0), mask)
        bd = ImageDraw.Draw(board)
        bd.rounded_rectangle((7, 7, 202, 302), 9, outline=tuple(int(c * 0.88) for c in th.board))
        bd.rounded_rectangle((8, 8, 201, 301), 8, outline=tuple(min(255, int(c * 1.06)) for c in th.board))
        board = add_outline(board, (104, 66, 36))
        paste_shadow(world, board, 30, 102, 3, 5, 90)
        paste(world, board, 30, 102)

        # コンロ
        d.rounded_rectangle((8, 500, 262, 952), 10, fill=(58, 56, 62), outline=(24, 22, 26))
        d.rounded_rectangle((12, 504, 258, 948), 8, outline=(88, 86, 94))
        burners = [(self.V0[0], self.V0[1], 62)]
        if self.has_egg_pan:
            burners.append((self.E0[0], self.E0[1], 40))
        for (cx, cy, r) in burners:
            d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=(30, 30, 34), width=3)
            for a in range(0, 360, 60):
                ca, sa = math.cos(math.radians(a)), math.sin(math.radians(a))
                d.line((cx + (r - 28) * ca, cy + (r - 28) * sa, cx + (r + 10) * ca, cy + (r + 10) * sa),
                       fill=(30, 30, 34), width=3)
            d.ellipse((cx - 10, cy - 10, cx + 10, cy + 10), fill=(40, 40, 46), outline=(20, 20, 24))
        for kx in (60, 110, 160, 210):
            d.ellipse((kx - 8, 924, kx + 8, 940), fill=(196, 196, 204), outline=(30, 30, 34))
            d.line((kx, 926, kx, 932), fill=(60, 60, 66), width=2)

        # ランチョンマット・器・スプーン
        mat = Image.new("RGBA", (240, 240))
        md = ImageDraw.Draw(mat)
        c0, c1, c2 = th.mat
        for gy in range(0, 240, 12):
            for gx in range(0, 240, 12):
                a, b = (gx // 12) % 2, (gy // 12) % 2
                md.rectangle((gx, gy, gx + 11, gy + 11), fill=c0 if a == b == 0 else c1 if a == b == 1 else c2)
        md.rectangle((0, 0, 239, 239), outline=tuple(int(c * 0.7) for c in c1))
        paste_shadow(world, mat, 15, PLATE_C[1] - 120, 2, 3, 60)
        paste(world, mat, 15, PLATE_C[1] - 120)
        cw = self.container.width
        paste_shadow(world, self.container, PLATE_C[0] - cw // 2, PLATE_C[1] - cw // 2, 4, 6, 90)
        paste(world, self.container, PLATE_C[0] - cw // 2, PLATE_C[1] - cw // 2)
        sp = Image.new("RGBA", (16, 90))
        sd = ImageDraw.Draw(sp)
        sd.ellipse((2, 0, 13, 20), fill=(214, 216, 224))
        sd.ellipse((4, 3, 9, 12), fill=(244, 246, 250))
        sd.rounded_rectangle((6, 18, 9, 88), 2, fill=(196, 198, 208))
        sp = add_outline(sp, (70, 70, 84))
        paste_shadow(world, sp, 226, PLATE_C[1] - 40, 2, 3, 70)
        paste(world, sp, 226, PLATE_C[1] - 40)
        # 先に盛っておくご飯
        if self.rice_base:
            self._draw_rice_base(ImageDraw.Draw(world), PLATE_C[0], PLATE_C[1], 0)
        return world

    def _draw_rice_base(self, d, x, y, cam):
        rng = np.random.default_rng(9)
        if self.rice_base == "left":
            cx, cy, rx, ry = x - 26, y, 30, 44
        else:
            cx, cy, rx, ry = x, y, self.cr, self.cr
        d.ellipse((cx - rx, cy - ry - cam, cx + rx, cy + ry - cam), fill=(236, 234, 226))
        d.ellipse((cx - rx + 1, cy - ry - cam, cx + rx - 2, cy + ry - 3 - cam), fill=(248, 247, 240))
        for _ in range(int(rx * ry / 6)):
            a, rr = rng.uniform(0, math.tau), math.sqrt(rng.random())
            px, py = cx + rx * rr * math.cos(a), cy + ry * rr * math.sin(a) - cam
            d.line((px, py, px + 1, py), fill=(226, 224, 214))

    # ------------------------------------------------------------ 位置

    def stir_amount(self, t):
        return sum(clamp(t - a, 0, b - a) for a, b in self.stirs) * STIR_SPEED

    def stirring(self, t):
        for a, b in self.stirs:
            if a <= t <= b:
                return (t - a) * STIR_SPEED
        return None

    def cam_y(self, t):
        top = 480 if self.has_egg_pan else 530
        y = top * ease(t, 8.9, 10.1)
        y += (900 - top) * ease(t, 19.0, 20.2)
        y += 60 * ease(t, 24.0, 25.0)
        return int(round(y))

    def serve_target(self):
        """器の中で中身を置く中心と大きさ。"""
        if self.rice_base == "left":
            return (PLATE_C[0] + 18, PLATE_C[1] + 2), (40, 50)
        if self.transfer == "mound":
            return (PLATE_C[0], PLATE_C[1] + 5), (48, 27)
        r = self.cr * (0.75 if self.transfer == "top_rice" else 0.95)
        return PLATE_C, (r, r * 0.92)

    def vessel_c(self, t):
        above = (PLATE_C[0] - (0 if self.transfer == "mound" else 30), PLATE_C[1] - 65)
        c = lerp2(self.V0, above, ease(t, 19.0, 20.2))
        if self.transfer == "mound":
            c = (c[0], c[1] - 12 * ease(t, 20.25, 20.55) + 12 * ease(t, 20.6, 20.9))
            q = ease(t, 20.8, 21.6)
        else:
            q = ease(t, 21.7, 22.4)
        return (c[0] - 300 * q, c[1])

    def egg_pan_c(self, t):
        if t < 20.2:
            return self.E0
        if t < 21.0:
            c = lerp2(self.E0, (340, self.E0[1]), prog(t, 20.2, 20.5))
            return lerp2(c, (340, 1160), prog(t, 20.5, 20.9))
        c = lerp2((340, 1160), (148, 1160), ease(t, 21.0, 21.85))
        return (c[0] + 300 * ease(t, 22.6, 23.4), c[1])

    def transfer_p(self, t, delay=0.0):
        if self.transfer == "mound":
            return ease(t, 20.25 + delay * 0.3, 20.85 + delay * 0.3)
        if self.transfer == "top_rice":
            return ease(t, 20.3, 21.0)
        return ease(t, 20.35 + delay, 21.0 + delay)

    def in_vessel_pos(self, t, r, a, k, wob, rel):
        vc = self.vessel_c(t)
        s = self.stir_amount(t)
        ang = a + s * k
        rr = r * (1 + 0.08 * math.sin(s * 0.7 + wob))
        p = (vc[0] + rr * math.cos(ang), vc[1] + rr * math.sin(ang) * 0.92)
        if self.liquid_level(t) > 0.3:
            p = (p[0] + 0.8 * math.sin(t * 3 + wob), p[1] + 0.8 * math.cos(t * 2.5 + wob))
        if self.shape:
            sp = ease(t, self.shape.a, self.shape.b)
            if sp > 0:
                p = lerp2(p, (vc[0] + rel[0] * 40, vc[1] + rel[1] * 23), sp)
        return p

    def served_pos(self, t, rel, item_p):
        c, (rx, ry) = self.serve_target()
        return (c[0] + rel[0] * rx * 0.85, c[1] + rel[1] * ry * 0.85)

    def piece_pos(self, pc, t):
        push = (5.6, 6.05) if pc["which"] == 0 else (7.7, 8.1)
        if t < push[0]:
            return None
        if t < 8.15:
            return lerp2(pc["spawn"], pc["pile"], ease(t, *push))
        if t < 8.8 + pc["delay"]:
            return lerp2(pc["pile"], pc["gather"], ease(t, 8.15, 8.75))
        target = self.in_vessel_pos(t, pc["r"], pc["a"], pc["k"], pc["wob"], pc["rel"])
        tp = self.transfer_p(t, pc["delay"])
        if tp > 0:
            target = lerp2(self.in_vessel_pos(min(t, 20.25), pc["r"], pc["a"], pc["k"], pc["wob"], pc["rel"])
                           if self.transfer != "top_rice" else target,
                           self.served_pos(t, pc["rel"], tp), tp)
        fp = prog(t, 8.8 + pc["delay"], 9.75 + pc["delay"])
        if fp < 1:
            return (lerp(pc["gather"][0], target[0], smooth(fp)), lerp(pc["gather"][1], target[1], fp * fp))
        return target

    # ------------------------------------------------------------ 描画(中身)

    def piece_color(self, pc, t):
        ing = pc["ing"]
        col = lerpc(ing.raw, ing.cooked, ease(t, 10.4, 13.0))
        if ing.browned and pc["brown"]:
            col = lerpc(col, ing.browned, ease(t, 11.5, 13.0))
        tc, tp = self.tint(t, "liquid")
        if tc:
            col = lerpc(col, tc, tp * 0.35)
        gc, gp = self.tint(t, "grain")
        if gc:
            col = lerpc(col, gc, gp * 0.3)
        return col

    def draw_piece(self, d, pc, x, y, col):
        x, y = int(round(x)), int(round(y))
        ing = pc["ing"]
        sz = ing.size
        dark = tuple(int(c * 0.78) for c in col)
        if ing.shape == "strip":
            w, h = (sz + 1, 2) if not pc["vert"] else (2, sz + 1)
            d.rectangle((x, y, x + w - 1, y + h - 1), fill=col)
            d.line((x, y + h - 1, x + w - 1, y + h - 1), fill=dark)
        elif ing.shape == "leaf":
            d.rectangle((x, y, x + sz - 1, y + sz - 2), fill=col)
            d.rectangle((x + 1, y + 1, x + sz, y + sz - 1), fill=col)
            d.point((x + sz, y + sz - 1), fill=dark)
        elif ing.shape == "ring":
            d.ellipse((x, y, x + sz, y + sz), fill=col, outline=dark)
            d.point((x + sz // 2, y + sz // 2), fill=tuple(min(255, c + 40) for c in col))
        else:
            d.rectangle((x, y, x + sz - 1, y + sz - 1), fill=col)
            d.line((x, y + sz - 1, x + sz - 1, y + sz - 1), fill=dark)
            d.line((x + sz - 1, y, x + sz - 1, y + sz - 1), fill=dark)

    def grain_color(self, g, t):
        base = g["gk"].color
        gc, gp = self.tint(t, "grain")
        if gc and g["gk"].style in ("dot", "strand"):
            m = clamp((gp - g["mix"] * 0.4) / 0.6)
            return lerpc(base, gc, m)
        if g["gk"].style in ("cube", "dot2"):
            lc, lp = self.tint(t, "liquid")
            if lc:
                return lerpc(base, lc, lp * 0.3)
        return base

    def grain_pos(self, g, t):
        tgt = self.in_vessel_pos(t, g["r"], g["a"], g["k"], g["wob"], g["rel"])
        tp = self.transfer_p(t, g["mix"] * 0.5)
        if tp > 0:
            src = (self.in_vessel_pos(min(t, 20.25), g["r"], g["a"], g["k"], g["wob"], g["rel"])
                   if self.transfer != "top_rice" else tgt)
            tgt = lerp2(src, self.served_pos(t, g["rel"], tp), tp)
        vc = self.vessel_c(t)
        tip = (vc[0] + 34, vc[1] - 36)
        fp = prog(t, g["t0"], g["t0"] + 0.35)
        return lerp2(tip, tgt, fp) if fp < 1 else tgt

    def draw_grain(self, d, g, x, y, col, t):
        x, y = int(round(x)), int(round(y))
        st = g["gk"].style
        if st == "dot":
            d.line((x, y, x, y + 1) if g["vert"] else (x, y, x + 1, y), fill=col)
        elif st == "dot2":
            d.rectangle((x, y, x + 1, y + 1), fill=col)
            d.point((x + 1, y + 1), fill=tuple(int(c * 0.8) for c in col))
        elif st == "strand":
            ang = g["ang"] + self.stir_amount(t) * g["k"] * 0.6
            ca, sa = math.cos(ang), math.sin(ang)
            pts = [(x + k * 2.4 * ca - sa * 1.6 * math.sin(k * 1.4 + g["wob"]),
                    y + k * 2.4 * sa + ca * 1.6 * math.sin(k * 1.4 + g["wob"])) for k in range(6)]
            d.line(pts, fill=tuple(int(c * 0.62) for c in col), width=3)
            d.line(pts, fill=col, width=1)
            d.point(pts[2], fill=tuple(min(255, c + 30) for c in col))
        elif st == "cube":
            d.rectangle((x, y, x + 3, y + 3), fill=col)
            d.line((x, y + 3, x + 3, y + 3), fill=tuple(int(c * 0.82) for c in col))
            d.line((x + 3, y, x + 3, y + 3), fill=tuple(int(c * 0.82) for c in col))
        elif st == "block":
            # ルウや味噌は、入れたあと混ぜると溶けて小さくなる
            _, lp = self.tint(t, "liquid")
            s = 5 * (1 - lp) if t > g["step"].b else 5
            if s >= 1:
                d.rectangle((x, y, x + s, y + s * 0.8), fill=col, outline=tuple(int(c * 0.7) for c in col))

    def draw_liquid(self, img, t, center, cam, r_full, level, color, boiling):
        if level <= 0.01 or color is None:
            return
        d = ImageDraw.Draw(img)
        r = r_full * math.sqrt(level)
        if r < 3:
            return
        x, y = center[0], center[1] - cam
        dark = tuple(int(c * 0.8) for c in color)
        d.ellipse((x - r, y - r * 0.94, x + r, y + r * 0.94), fill=dark)
        d.ellipse((x - r + 2, y - r * 0.94 + 2, x + r - 2, y + r * 0.94 - 2), fill=color)
        if r > 8:
            d.arc((x - r + 6, y - r * 0.8, x + r - 6, y + r * 0.8), 200, 240,
                  fill=tuple(min(255, c + 40) for c in color), width=1)
        if boiling:
            rng = np.random.default_rng(int(t * 12) + int(center[1]))
            for _ in range(7 if r > 6 else 0):
                a, rr = rng.uniform(0, math.tau), rng.uniform(0, r - 4)
                bx, by = x + rr * math.cos(a), y + rr * math.sin(a) * 0.9
                br = rng.integers(1, 3)
                d.ellipse((bx - br, by - br, bx + br, by + br), outline=tuple(min(255, c + 50) for c in color))

    def draw_sizzle(self, d, t, center, cam, radius, active, flame=True):
        if not active:
            return
        rng = np.random.default_rng(int(t * gfx.FPS) * 7 + int(center[1]))
        if not self.pot:
            for _ in range(5):
                a, rr = rng.uniform(0, math.tau), rng.uniform(0.3, 1.0) * radius
                d.point((center[0] + rr * math.cos(a), center[1] + rr * math.sin(a) - cam), fill=(255, 250, 210))
        if flame:
            for i in range(18):
                a = i / 18 * math.tau + t * 0.6
                if rng.random() < 0.6:
                    r2 = radius + 18 + rng.integers(0, 3)
                    d.point((center[0] + r2 * math.cos(a), center[1] + r2 * math.sin(a) - cam),
                            fill=(90, 150, 255) if rng.random() < 0.7 else (255, 200, 90))

    # ------------------------------------------------------------ 卵

    def draw_egg_sheet(self, img, t, cam):
        es = self.egg_sheet
        if not es or t < es.a + 0.6:
            return
        morph = ease(t, 21.95, 22.6)
        c = self.egg_pan_c(t) if t < 21.95 else lerp2(self.egg_pan_c(21.95), self.serve_target()[0], morph)
        d = ImageDraw.Draw(img)
        x, y = c[0], c[1] - cam
        a0 = es.a + 0.6
        if t < a0 + 0.35:
            r = lerp(8, 30, ease(t, a0, a0 + 0.35))
            d.ellipse((x - r, y - r, x + r, y + r), fill=(246, 244, 236), outline=(220, 214, 200))
            d.ellipse((x - 7, y - 7, x + 7, y + 7), fill=(252, 184, 40), outline=(220, 140, 30))
            return
        w = ease(t, a0 + 0.35, a0 + 1.4)
        r = lerp(30, 47, ease(t, a0 + 0.35, a0 + 1.2))
        if t < 21.95:
            base = lerpc((246, 236, 200), (250, 206, 76), w)
            edge = lerpc((220, 210, 180), (232, 172, 60), w)
            d.ellipse((x - r, y - r, x + r, y + r), fill=base, outline=edge)
            if w < 1:
                for i in range(5):
                    a = i * 1.3 + t * 5
                    d.arc((x - r * 0.6, y - r * 0.6, x + r * 0.6, y + r * 0.6),
                          math.degrees(a), math.degrees(a) + 40, fill=(252, 184, 40), width=2)
            return
        self.draw_omelet(d, x, y, morph)

    @staticmethod
    def draw_omelet(d, x, y, morph):
        rx, ry = lerp(47, 52, morph), lerp(47, 30, morph)
        d.ellipse((x - rx - 1, y - ry - 1 + 3 * morph, x + rx + 1, y + ry + 1 + 3 * morph), fill=(196, 128, 36))
        d.ellipse((x - rx, y - ry, x + rx, y + ry), fill=(232, 164, 44))
        d.ellipse((x - rx + 2, y - ry + 1, x + rx - 4, y + ry - 4), fill=(248, 198, 64))
        d.ellipse((x - rx * 0.7 - 4, y - ry * 0.7 - 4, x + rx * 0.55, y + ry * 0.4), fill=(252, 216, 104))
        d.ellipse((x - rx * 0.55, y - ry * 0.65, x - rx * 0.15, y - ry * 0.4), fill=(255, 238, 170))

    def draw_egg_patches(self, img, d, t, cam):
        if not self.egg_pour:
            return
        vc = self.vessel_c(t)
        setp = ease(t, self.egg_pour.b, self.egg_pour.b + 1.4)
        # 卵の膜(全体をうっすら覆う)
        lp = ease(t, self.egg_pour.a + 0.2, self.egg_pour.b)
        if lp > 0.05:
            if self.transfer == "top_rice" and t >= 20.3:
                c, (rx, _) = self.serve_target()
                cx, cy = lerp2(vc, c, self.transfer_p(t))
                r = lerp(0.7 * self.inner, rx * 0.95, self.transfer_p(t))
            else:
                cx, cy, r = vc[0], vc[1], 0.7 * self.inner
            r *= lp
            base = lerpc((252, 240, 200), (246, 222, 140), setp)
            ov = Image.new("RGBA", (int(2 * r) + 4, int(2 * r) + 4))
            ImageDraw.Draw(ov).ellipse((2, 2, 2 * r + 1, 2 * r * 0.92 + 1), fill=base + (170,))
            paste(img, ov, cx - r - 2, cy - r - 2 - cam)
        for p in self.patches:
            if t < p["t0"]:
                continue
            g = ease(t, p["t0"], p["t0"] + 0.4)
            if self.transfer == "top_rice" and t >= 20.3:
                c, (rx, ry) = self.serve_target()
                tp = self.transfer_p(t)
                src = (vc[0] + p["dx"], vc[1] + p["dy"])
                dst = (c[0] + p["dx"] * 0.75, c[1] + p["dy"] * 0.75)
                x, y = lerp2(src, dst, tp)
            else:
                x, y = vc[0] + p["dx"], vc[1] + p["dy"]
            y -= cam
            col = lerpc((250, 230, 170) if not p["yolk"] else (250, 196, 60), (248, 216, 110), setp)
            d.ellipse((x - p["rx"] * g, y - p["ry"] * g, x + p["rx"] * g, y + p["ry"] * g), fill=col)
            if not p["yolk"]:
                d.point((x - 2, y - 1), fill=(255, 250, 230))

    # ------------------------------------------------------------ 仕上げ

    def garnish_schedule(self):
        n = len(self.d.garnish)
        a, b = 25.1, 27.0
        span = (b - a) / max(1, n)
        return [(g, a + i * span, a + (i + 1) * span) for i, g in enumerate(self.d.garnish)]

    KETCHUP_PATH = [(-36, -4), (-24, 8), (-12, -9), (0, 7), (12, -9), (24, 8), (36, -4)]

    def ketchup_points(self, p):
        pts = self.KETCHUP_PATH
        total = len(pts) - 1
        seg = p * total
        out = [pts[0]]
        for i in range(1, len(pts)):
            if i <= seg:
                out.append(pts[i])
            else:
                f = seg - (i - 1)
                if f > 0:
                    out.append(lerp2(pts[i - 1], pts[i], f))
                break
        return out

    def draw_garnish(self, img, t, cam):
        d = ImageDraw.Draw(img)
        c, (rx, ry) = self.serve_target()
        for g, a, b in self.garnish_schedule():
            p = ease(t, a + 0.25, b - 0.2)
            if p <= 0:
                continue
            if g[0] == "line":
                pts = [(c[0] + x, c[1] + y - cam) for x, y in self.ketchup_points(p)]
                if len(pts) >= 2:
                    d.line(pts, fill=tuple(int(v * 0.6) for v in g[2]), width=5, joint="curve")
                    d.line(pts, fill=g[2], width=3, joint="curve")
                    d.line([(x - 1, y - 1) for x, y in pts], fill=tuple(min(255, v + 60) for v in g[2]))
            elif g[0] == "sprinkle":
                rng = np.random.default_rng(len(g[1]) * 7 + g[3])
                for i in range(g[3]):
                    if i / g[3] > p:
                        break
                    a2, rr = rng.uniform(0, math.tau), g[2] * math.sqrt(rng.random())
                    x, y = int(c[0] + rr * math.cos(a2)), int(c[1] + rr * math.sin(a2) * 0.8 - cam)
                    d.rectangle((x, y, x + 1, y + 1), fill=g[1][i % len(g[1])])
            elif g[0] == "place":
                self.draw_topping(d, g[1], c[0] + g[2][0], c[1] + g[2][1] - cam, p)

    @staticmethod
    def draw_topping(d, kind, x, y, p):
        if p < 0.5:
            y -= (0.5 - p) * 30
        if kind == "parsley":
            for (ox, oy) in ((0, 0), (3, -2), (-2, 2), (2, 3), (5, 1), (-1, -3)):
                d.rectangle((x + ox - 1, y + oy - 1, x + ox + 1, y + oy + 1), fill=(64, 140, 56))
                d.point((x + ox, y + oy - 1), fill=(130, 200, 96))
        elif kind == "mitsuba":
            d.line((x, y + 2, x + 8, y + 10), fill=(120, 170, 90), width=1)
            for (ox, oy) in ((-3, -2), (3, -3), (0, 3)):
                d.ellipse((x + ox - 3, y + oy - 2, x + ox + 3, y + oy + 2), fill=(70, 150, 60),
                          outline=(40, 100, 40))
        elif kind == "beni":
            for k in range(6):
                d.line((x + k - 3, y - 2 + (k % 2), x + k, y + 3), fill=(220, 50, 70))
        elif kind == "snowpea":
            d.ellipse((x - 6, y - 2, x + 6, y + 2), fill=(80, 170, 70), outline=(40, 110, 40))
            d.line((x - 4, y - 1, x + 4, y - 1), fill=(150, 220, 120))
        elif kind == "fukujin":
            for k in range(9):
                ox, oy = (k * 3) % 8 - 4, (k * 5) % 6 - 3
                d.rectangle((x + ox, y + oy, x + ox + 1, y + oy + 1), fill=(190, 50, 50))

    # ------------------------------------------------------------ 湯気

    def draw_steam(self, dst, t, cam):
        ov = Image.new("RGBA", dst.size)
        d = ImageDraw.Draw(ov)
        fade_plate = 1 - ease(t, 24.2, 25.6) * 0.85
        for p in self.steam:
            age = t - p["t0"]
            if age < 0 or age > p["life"]:
                continue
            if p["src"] == "v":
                sx, sy = self.vessel_c(p["t0"])
            elif p["src"] == "e":
                sx, sy = self.egg_pan_c(p["t0"])
            else:
                sx, sy = PLATE_C
            u = age / p["life"]
            x = sx + p["dx"] + 6 * math.sin(age * 2.2 + p["ph"])
            y = sy + p["dy"] - age * 22 - cam
            a = 95 * math.sin(math.pi * u) * (1.3 if self.pot and p["src"] == "v" else 1)
            if p["src"] == "plate":
                a *= fade_plate * (1.5 if p["big"] else 1)
            a = int(min(150, a) // 30 * 30)
            if a <= 0:
                continue
            n = 4 + p["size"]
            w = 2 if p["big"] else 1
            for k in range(n):
                fk = k / n
                px = x + 2.2 * math.sin(fk * 4 + age * 3 + p["ph"])
                ak = int(a * (1 - abs(fk - 0.4)) // 30 * 30)
                if ak > 0:
                    ix, iy = int(round(px)), int(round(y - k * 2))
                    d.rectangle((ix, iy, ix + w - 1, iy + 1), fill=(255, 255, 255, ak))
        v = ease(t, 22.2, 22.9) * (1 - ease(t, 24.1, 25.3))
        if v > 0:
            for i in range(8):
                ph = i * 1.7
                bx = PLATE_C[0] + 26 * math.sin(t * 0.7 + ph) + (i - 3.5) * 7
                by = PLATE_C[1] - cam + 2 + 12 * math.sin(t * 0.5 + ph * 1.3) - (t * 6 + i * 7) % 26
                rx, ry = 46 + 8 * math.sin(ph), 20 + 4 * math.cos(ph)
                a = int(v * 120 // 20 * 20)
                if a > 0:
                    d.ellipse((bx - rx, by - ry, bx + rx, by + ry), fill=(255, 252, 246, a))
        dst.alpha_composite(ov)

    # ------------------------------------------------------------ 刻む

    @staticmethod
    def chop_state(t, cut):
        a, b, n = cut
        if t < a:
            return 0.0, 1.0, 0
        p = prog(t, a, b)
        k = min(n, int(p * n))
        phase = (p * n) % 1
        lift = abs(math.cos(phase * math.pi)) if p < 1 else 1.0
        return k / n + (1 / n) * smooth(clamp(phase * 2 - 0.2)) * (p < 1), lift, k

    @staticmethod
    def draw_sliced(dst, spr, cx, cy, frac, ndone, ntotal, cam):
        w = spr.width
        x0, y0 = cx - w / 2, cy - spr.height / 2 - cam
        cut_x = int(w * (1 - frac))
        if cut_x > 0:
            paste(dst, spr.crop((0, 0, cut_x, spr.height)), x0, y0)
        edges = [int(w * (1 - j / ntotal)) for j in range(ndone + 1)]
        d = ImageDraw.Draw(dst)
        for j in range(ndone):
            xr, xl = edges[j], max(cut_x, edges[j + 1])
            if xr - xl <= 0:
                continue
            off = 1 + (ndone - j) * 0.55
            paste(dst, spr.crop((xl, 0, xr, spr.height)), x0 + xl + off, y0)
            d.line((x0 + xl + off, y0 + 3, x0 + xl + off, y0 + spr.height - 4), fill=(255, 255, 248))
        return x0 + cut_x

    # ------------------------------------------------------------ 1 フレーム

    def render(self, t: float) -> Image.Image:
        cam = self.cam_y(t)
        img = self.world.crop((0, cam, LW, cam + LH))
        d = ImageDraw.Draw(img)

        # まな板
        ex = self.extra_sprite
        if cam < 300:
            paste_shadow(img, ex, EXTRA_POS[0] - ex.width / 2, EXTRA_POS[1] - ex.height / 2 - cam, 2, 2, 60)
            paste(img, ex, EXTRA_POS[0] - ex.width / 2, EXTRA_POS[1] - ex.height / 2 - cam)
        f1, l1, k1 = self.chop_state(t, CUT1)
        c1 = lerp2(ING1_0, ING1_C, ease(t, 3.15, 3.5))
        knife = None
        s1, s2 = self.ing1.sprite, self.ing2.sprite
        if t < 5.65:
            paste_shadow(img, s1, c1[0] - s1.width / 2, c1[1] - s1.height / 2 - cam, 2, 2, 60)
            cx = self.draw_sliced(img, s1, c1[0], c1[1], f1, k1, CUT1[2], cam)
            if t >= 3.0:
                knife = (cx + 1, c1[1] - 12, l1 if t >= CUT1[0] else 1.0)
        f2, l2, k2 = self.chop_state(t, CUT2)
        c2 = lerp2(ING2_0, ING2_C, ease(t, 6.1, 6.45))
        if t < 7.75:
            paste_shadow(img, s2, c2[0] - s2.width / 2, c2[1] - s2.height / 2 - cam, 2, 2, 60)
            cx = self.draw_sliced(img, s2, c2[0], c2[1], f2, k2, CUT2[2], cam)
            if t >= 6.05:
                knife = (cx + 1, c2[1] - 14, l2 if t >= CUT2[0] else 1.0)

        vc = self.vessel_c(t)
        ep = self.egg_pan_c(t)

        def draw_vessel():
            x0, y0 = vc[0] - self.vpts[0], vc[1] - self.vpts[1] - cam
            if t < 22.5 and -300 < y0 < LH + 50:
                paste_shadow(img, self.vessel, x0, y0, 3, 4, 80)
                paste(img, self.vessel, x0, y0)
            self.draw_sizzle(d, t, vc, cam, self.vr - 18, 9.8 < t < 19.0)

        def draw_contents():
            # 汁(鍋の中 → 器へ)
            lv = self.liquid_level(t)
            lc = self.liquid_color(t)
            tp = self.transfer_p(t) if self.transfer != "mound" else 0
            if lc is not None:
                boiling = self.boil_from is not None and self.boil_from < t < 19.2
                if self.transfer == "pour":
                    self.draw_liquid(img, t, vc, cam, self.inner, lv * (1 - tp), lc, boiling)
                    c, (rx, ry) = self.serve_target()
                    if tp > 0:
                        self.draw_liquid(img, t, c, cam, rx, tp * 0.95, lc, False)
                        if tp < 1:
                            # 鍋から器へ流れる汁
                            sx, sy = vc[0] + 30, vc[1] + 40 - cam
                            d.line((sx, sy, c[0], c[1] - cam), fill=lc, width=4)
                            d.line((sx - 1, sy, c[0] - 1, c[1] - cam), fill=tuple(min(255, v + 40) for v in lc))
                elif self.transfer == "top_rice":
                    if t < 20.3:
                        self.draw_liquid(img, t, vc, cam, self.inner, lv, lc, boiling)
                    else:
                        c, (rx, ry) = self.serve_target()
                        pos = lerp2(vc, c, tp)
                        self.draw_liquid(img, t, pos, cam, lerp(self.inner, rx, tp), lv * 0.8, lc, False)
            # 形を整えたご飯・麺の土台
            if self.shape:
                sp = ease(t, self.shape.a, self.shape.b)
                if sp > 0:
                    gcol = self.mound_color(t)
                    if t < 20.25:
                        mx, my = vc
                    else:
                        mx, my = lerp2(self.vessel_c(20.25), self.serve_target()[0], self.transfer_p(t))
                    rx, ry = 44 * sp, 26 * sp
                    k = 0.7 if self.noodles else 1.0
                    d.ellipse((mx - rx - 1, my - ry - cam, mx + rx + 1, my + ry + 2 - cam),
                              fill=tuple(int(c * 0.8 * k) for c in gcol))
                    d.ellipse((mx - rx, my - ry - cam, mx + rx, my + ry - cam),
                              fill=tuple(int(c * k) for c in gcol))
            for pc in self.pieces:
                pos = self.piece_pos(pc, t)
                if pos is not None:
                    self.draw_piece(d, pc, pos[0], pos[1] - cam, self.piece_color(pc, t))
            for g in self.grains:
                if t >= g["t0"]:
                    pos = self.grain_pos(g, t)
                    self.draw_grain(d, g, pos[0], pos[1] - cam, self.grain_color(g, t), t)
            self.draw_egg_patches(img, d, t, cam)
            # ソースのかたまり(混ぜる前)
            for s in self.steps:
                if s.kind == "sauce":
                    kp = ease(t, s.a + 0.25, s.b - 0.1)
                    fade = 1 - ease(t, s.b + 0.1, s.b + 0.9)
                    r = 10 * kp * fade
                    if r > 0.5:
                        bc = s.raw[1]
                        kx, ky = vc[0] - 6, vc[1] - 4 - cam
                        d.ellipse((kx - r, ky - r * 0.8, kx + r, ky + r * 0.8), fill=bc,
                                  outline=tuple(int(v * 0.6) for v in bc))
                        d.point((kx - r * 0.4, ky - r * 0.4), fill=tuple(min(255, v + 70) for v in bc))

        def draw_egg_pan_group():
            if self.has_egg_pan:
                x0, y0 = ep[0] - self.epts[0], ep[1] - self.epts[1] - cam
                if -300 < y0 < LH + 50 and t < 23.5:
                    paste_shadow(img, self.egg_pan, x0, y0, 3, 4, 80)
                    paste(img, self.egg_pan, x0, y0)
                es = self.egg_sheet
                self.draw_sizzle(d, t, ep, cam, 40, es.a + 0.6 < t < 19.0)
                self.draw_egg_sheet(img, t, cam)

        if t < 20.9:
            draw_egg_pan_group()
            draw_vessel()
            draw_contents()
        else:
            draw_vessel()
            draw_contents()
            draw_egg_pan_group()

        self.draw_garnish(img, t, cam)
        self.draw_hands(img, t, cam, knife, f1, f2, c1, c2, vc, ep)
        self.draw_steam(img, t, cam)
        return self.post(img, t, cam)

    def mound_color(self, t):
        g = next((g for g in self.grains if g["gk"].style in ("dot", "strand")), None)
        if not g:
            return (200, 160, 110)
        base = g["gk"].color
        gc, gp = self.tint(t, "grain")
        return lerpc(base, gc, gp) if gc else base

    # ------------------------------------------------------------ 手と道具

    def _tool(self, img, spr, x, y, cam, sh=True):
        if sh:
            paste(img, shadow_of(spr), x + 3, y - cam + 4)
        paste(img, spr, x, y - cam)

    def draw_hands(self, img, t, cam, knife, f1, f2, c1, c2, vc, ep):
        w1, w2 = self.ing1.sprite.width, self.ing2.sprite.width
        # 左手: 食材を押さえる
        if 3.0 <= t < 6.0:
            tx = c1[0] - 14 - w1 * f1 * 0.8
            g = lerp2((20, cam + 520), (tx, c1[1] + 6), ease(t, 3.0, 3.25))
            g = lerp2(g, (-10, cam + 540), ease(t, 5.55, 5.95))
            draw_hand(img, "L", "claw", g[0], g[1], cam)
        if 6.0 <= t < 8.1:
            tx = c2[0] - 16 - w2 * f2 * 0.8
            g = lerp2((20, cam + 520), (tx, c2[1] + 6), ease(t, 6.0, 6.2))
            g = lerp2(g, (-10, cam + 540), ease(t, 7.65, 8.05))
            draw_hand(img, "L", "claw", g[0], g[1], cam)
        # 左手: 鍋の取っ手
        end = 21.7 if self.transfer == "mound" else 22.5
        if 9.8 <= t < end:
            hx = vc[0] - self.vpts[0] + self.vpts[2]
            hy = vc[1] - self.vpts[1] + self.vpts[3]
            g = lerp2((10, cam + 560), (hx + 2, hy - 4), ease(t, 9.8, 10.3))
            draw_hand(img, "L", "grip", g[0], g[1], cam)

        # 右手: 包丁
        if 3.0 <= t < 9.4:
            if knife is not None and t < 7.7:
                kx, ky, lift = knife
            else:
                kx, ky, lift = PILE2[0] - 20, PILE2[1] - 30, 1.0
            if 5.6 <= t < 6.1:
                kx, ky = lerp2((kx, ky), (PILE1[0] - 22, PILE1[1] - 10), ease(t, 5.6, 6.0))
            if 7.7 <= t:
                kx, ky = lerp2((c2[0] - 10, c2[1] - 14), (PILE2[0] - 22, PILE2[1] - 12), ease(t, 7.7, 8.1))
                kx, ky = lerp2((kx, ky), (GATHER[0] + 24, GATHER[1] - 40), ease(t, 8.1, 8.75))
                kx, ky = lerp2((kx, ky), (300, cam + 560), ease(t, 8.8, 9.35))
            kx, ky = lerp2((240, cam + 540), (kx, ky), ease(t, 3.0, 3.4))
            up = 4 * lift
            paste(img, shadow_of(self.knife, 70), kx - 3 + up, ky - cam + 3 + up)
            paste(img, self.knife, kx - 5, ky - cam - up)
            draw_hand(img, "R", "grip", kx, ky + 56 - up, cam)

        def enter_exit(a, b, target, dur_in=0.25, dur_out=0.25):
            p = lerp2((260, cam + 520), target, ease(t, a, a + dur_in))
            return lerp2(p, (300, cam + 560), ease(t, b - dur_out, b))

        for s in self.steps:
            if not (s.a <= t < s.b + 0.05):
                continue
            if s.kind == "stir" or (s.kind == "shape"):
                tool = self.ladle if self.pot else self.spatula
                if s.kind == "stir":
                    a = (t - s.a) * STIR_SPEED
                    px, py = vc[0] + 26 * math.cos(a), vc[1] + 21 * math.sin(a)
                else:
                    px, py = vc[0] + 10 * math.cos(t * 9), vc[1] + 3 * math.sin(t * 22)
                b = enter_exit(s.a, s.b + 0.05, (px, py), 0.2, 0.15)
                self._tool(img, tool, b[0] - tool.width // 2, b[1] - 9, cam)
                draw_hand(img, "R", "grip", b[0], b[1] + 55, cam)
            elif s.kind == "add":
                gk = GRAIN_KINDS[s.raw[1]]
                b = enter_exit(s.a, s.b, (vc[0] + 34, vc[1] - 36), 0.3, 0.3)
                bowl = gfx.bowl_sprite(gk.bowl_color, 1 - ease(t, s.a + 0.3, s.b - 0.05))
                paste_shadow(img, bowl, b[0] - 23, b[1] - 23 - cam, 3, 4, 70)
                paste(img, bowl, b[0] - 23, b[1] - 23 - cam)
                draw_hand(img, "R", "grip", b[0] + 8, b[1] + 26, cam)
            elif s.kind == "liquid":
                b = enter_exit(s.a, s.b, (vc[0] + 30, vc[1] - 30), 0.25, 0.25)
                cup = gfx.cup_sprite(s.raw[1], 1 - ease(t, s.a + 0.2, s.b - 0.1))
                paste_shadow(img, cup, b[0] - 16, b[1] - 20 - cam, 3, 4, 70)
                paste(img, cup, b[0] - 16, b[1] - 20 - cam)
                if s.a + 0.2 < t < s.b - 0.1:
                    ImageDraw.Draw(img).line((b[0] - 10, b[1] - 6 - cam, vc[0] + 6, vc[1] - cam),
                                             fill=s.raw[1], width=2)
                draw_hand(img, "R", "grip", b[0] + 20, b[1] + 22, cam)
            elif s.kind == "sauce":
                b = enter_exit(s.a, s.b, (vc[0] - 6, vc[1] - 4), 0.22, 0.25)
                bottle = gfx.bottle_sprite(s.raw[1])
                sq = 1 if s.a + 0.25 <= t <= s.b - 0.1 else 0
                paste_shadow(img, bottle, b[0] - 11, b[1] + 4 - cam, 3, 4, 70)
                paste(img, bottle, b[0] - 11 + sq * (int(t * 30) % 2), b[1] + 4 - cam)
                draw_hand(img, "R", "grip", b[0], b[1] + 44, cam)
            elif s.kind == "egg_pour":
                b = enter_exit(s.a, s.b, (vc[0] + 20 * math.cos(t * 4), vc[1] - 20 + 14 * math.sin(t * 4)), 0.25, 0.25)
                bowl = gfx.bowl_sprite((250, 210, 100), 1 - ease(t, s.a + 0.2, s.b - 0.1))
                paste_shadow(img, bowl, b[0] - 23, b[1] - 23 - cam, 3, 4, 70)
                paste(img, bowl, b[0] - 23, b[1] - 23 - cam)
                draw_hand(img, "R", "grip", b[0] + 8, b[1] + 26, cam)
            elif s.kind == "egg_sheet":
                a0 = s.a
                if t < a0 + 0.95:
                    b = lerp2((260, cam + 520), (ep[0], ep[1] - 6), ease(t, a0, a0 + 0.4))
                    b = lerp2(b, (300, cam + 560), ease(t, a0 + 0.65, a0 + 0.95))
                    split = ease(t, a0 + 0.48, a0 + 0.62)
                    if split <= 0:
                        paste(img, self.egg, b[0] - 7, b[1] - 8 - cam)
                    else:
                        paste(img, self.egg.crop((0, 0, 7, 17)), b[0] - 7 - 5 * split, b[1] - 8 - cam)
                        paste(img, self.egg.crop((7, 0, 14, 17)), b[0] + 5 * split, b[1] - 8 - cam)
                    draw_hand(img, "R", "claw", b[0], b[1] + 12, cam)
                elif t < a0 + 2.5:
                    a = t * 13
                    cx, cy2 = ep[0] + 18 * math.cos(a), ep[1] + 14 * math.sin(a)
                    b = lerp2((260, cam + 520), (cx, cy2), ease(t, a0 + 0.9, a0 + 1.1))
                    b = lerp2(b, (300, cam + 560), ease(t, a0 + 2.15, a0 + 2.5))
                    self._tool(img, self.chop_sticks, b[0] - 6, b[1], cam)
                    draw_hand(img, "R", "grip", b[0], b[1] + 52, cam)
        # 右手: 卵のフライパンを運ぶ
        if self.has_egg_pan and 20.9 <= t < 23.5:
            hx = ep[0] - self.epts[0] + self.epts[2]
            hy = ep[1] - self.epts[1] + self.epts[3]
            draw_hand(img, "R", "grip", hx - 2, hy - 4, cam)
        # 右手: 仕上げ
        c, _ = self.serve_target()
        for g, a, b in self.garnish_schedule():
            if not (a <= t < b):
                continue
            p = ease(t, a + 0.25, b - 0.2)
            if g[0] == "line":
                tip = self.ketchup_points(max(p, 0.001))[-1]
                pos = enter_exit(a, b, (c[0] + tip[0], c[1] + tip[1]), 0.3, 0.3)
                bottle = gfx.bottle_sprite(g[1])
                paste_shadow(img, bottle, pos[0] - 11, pos[1] - cam + 2, 3, 4, 70)
                paste(img, bottle, pos[0] - 11, pos[1] - cam + 2)
                draw_hand(img, "R", "grip", pos[0], pos[1] + 40, cam)
            else:
                if g[0] == "place":
                    tgt = (c[0] + g[2][0], c[1] + g[2][1] - 4)
                else:
                    tgt = (c[0] + g[2] * 0.6 * math.cos(t * 7), c[1] - 6 + g[2] * 0.4 * math.sin(t * 7))
                pos = enter_exit(a, b, tgt, 0.3, 0.3)
                draw_hand(img, "R", "claw", pos[0], pos[1] + 14, cam)

    # ------------------------------------------------------------ 画面座標の後処理

    def post(self, img, t, cam):
        img = img.crop((CROP_X, CROP_Y, CROP_X + VW, CROP_Y + VH))
        arr = np.asarray(img.convert("RGB"), dtype=np.float32) * gfx.VIGNETTE
        if t < 3.0:
            dark = 1 - ease(t, 2.35, 3.0)
            e = (EXTRA_POS[0] - 4, EXTRA_POS[1] + 4)
            o = (ING1_0[0] + 8, ING1_0[1] + 6)
            c = (ING2_0[0] + 12, ING2_0[1] - 4)
            sx, sy = lerp2(e, o, ease(t, 0.9, 1.25))
            sx, sy = lerp2((sx, sy), c, ease(t, 1.7, 2.05))
            yy, xx = np.mgrid[0:VH, 0:VW]
            dist = np.hypot(xx - (sx - CROP_X), yy - (sy - cam - CROP_Y))
            r = 20 + 2 * math.sin(t * 6)
            light = np.where(dist < r, 1.0, np.where(dist < r + 5, 0.55, 0.1))
            arr *= (1 - dark * (1 - light))[:, :, None]
        img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).convert("RGBA")
        if 0.25 <= t < 2.7:
            draw_text(img, ["なにができるかな？"], 34, 0.25, t, color=(255, 246, 220), panel=False)
        draw_text(img, ["何の料理か", "わかった？"], 30, 27.3, t)
        if t >= 27.5:
            sd = ImageDraw.Draw(img)
            rng = np.random.default_rng(int(t * 4))
            pcx, pcy = PLATE_C[0] - CROP_X, PLATE_C[1] - cam - CROP_Y
            for i in range(6):
                a = rng.uniform(0, math.tau)
                r = rng.uniform(70, 92)
                x, y = pcx + r * math.cos(a), pcy + r * 0.8 * math.sin(a)
                sz = 2 if (int(t * 8) + i) % 2 else 1
                sd.line((x - sz - 1, y, x + sz + 1, y), fill=(255, 250, 210))
                sd.line((x, y - sz - 1, x, y + sz + 1), fill=(255, 250, 210))
        return img.convert("RGB")
