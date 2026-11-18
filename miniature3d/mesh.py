"""ローポリの基本形状(箱・円柱・円すい・球)を作る。

頂点 1 つ = 位置(3) + 法線(3) + 色(4)。色の 4 つ目は「発光の強さ」(0=発光しない)。
法線は面ごとに持たせて、カクッとしたローポリらしい陰影にする。
"""

from __future__ import annotations

import math

import numpy as np


def _tri(out, a, b, c, col):
    n = np.cross(np.subtract(b, a), np.subtract(c, a))
    ln = np.linalg.norm(n) or 1.0
    n = n / ln
    for p in (a, b, c):
        out.extend([*p, *n, *col])


def box(w, h, d, col, x=0.0, y=0.0, z=0.0, glow=0.0):
    """底面の中心が (x, y, z) にある箱。"""
    c = (*col, glow)
    x0, x1 = x - w / 2, x + w / 2
    y0, y1 = y, y + h
    z0, z1 = z - d / 2, z + d / 2
    v = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
         (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
    faces = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (3, 7, 6, 2), (0, 4, 7, 3), (1, 2, 6, 5)]
    out = []
    for a, b, cc, d_ in faces:
        _tri(out, v[a], v[b], v[cc], c)
        _tri(out, v[a], v[cc], v[d_], c)
    return out


def cylinder(r, h, col, x=0.0, y=0.0, z=0.0, seg=8, r_top=None, glow=0.0):
    """底面の中心が (x, y, z) にある円柱(r_top を変えると円すい台)。"""
    c = (*col, glow)
    rt = r if r_top is None else r_top
    out = []
    for i in range(seg):
        a0, a1 = i / seg * math.tau, (i + 1) / seg * math.tau
        p0 = (x + r * math.cos(a0), y, z + r * math.sin(a0))
        p1 = (x + r * math.cos(a1), y, z + r * math.sin(a1))
        q0 = (x + rt * math.cos(a0), y + h, z + rt * math.sin(a0))
        q1 = (x + rt * math.cos(a1), y + h, z + rt * math.sin(a1))
        _tri(out, p0, q0, q1, c)
        _tri(out, p0, q1, p1, c)
        _tri(out, (x, y + h, z), q1, q0, c)
        _tri(out, (x, y, z), p0, p1, c)
    return out


def cone(r, h, col, x=0.0, y=0.0, z=0.0, seg=8, glow=0.0):
    return cylinder(r, h, col, x, y, z, seg, r_top=0.001, glow=glow)


def sphere(r, col, x=0.0, y=0.0, z=0.0, seg=8, rings=5, sy=1.0, glow=0.0):
    """中心が (x, y, z) の低ポリ球。sy で縦につぶす/伸ばす。"""
    c = (*col, glow)
    out = []

    def p(i, j):
        th = j / rings * math.pi
        ph = i / seg * math.tau
        return (x + r * math.sin(th) * math.cos(ph), y + r * sy * math.cos(th), z + r * math.sin(th) * math.sin(ph))

    for j in range(rings):
        for i in range(seg):
            a, b, cc, d = p(i, j), p(i + 1, j), p(i + 1, j + 1), p(i, j + 1)
            for tri in ((a, b, cc) if j > 0 else None, (a, cc, d) if j < rings - 1 else None):
                if tri is None:
                    continue
                t0, t1, t2 = tri
                n = np.cross(np.subtract(t1, t0), np.subtract(t2, t0))
                mid = np.add(np.add(t0, t1), t2) / 3 - np.array((x, y, z))
                if np.dot(n, mid) < 0:
                    t1, t2 = t2, t1
                _tri(out, t0, t1, t2, c)
    return out


def to_array(parts) -> np.ndarray:
    flat = []
    for p in parts:
        flat.extend(p)
    return np.array(flat, dtype="f4")


def transform(parts, m):
    """部品をまとめて 4x4 行列で動かす(回転した家や道路を作るとき)。"""
    m = np.asarray(m, dtype="f4")
    out = []
    for p in parts:
        arr = np.array(p, dtype="f4").reshape(-1, 10)
        pos = np.c_[arr[:, :3], np.ones(len(arr), "f4")] @ m.T
        nrm = arr[:, 3:6] @ m[:3, :3].T
        nrm /= np.linalg.norm(nrm, axis=1, keepdims=True) + 1e-9
        arr[:, :3], arr[:, 3:6] = pos[:, :3], nrm
        out.append(arr.ravel().tolist())
    return out
