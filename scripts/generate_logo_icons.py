# -*- coding: utf-8 -*-
"""Регенерация PNG-иконок PWA и favicon.ico с новым логотипом «Трудник».

Эмблема: незамкнутый круг + ихтис (две пересекающиеся дуги).
Геометрия — в координатах фирменного знака (холст 600x600, y вниз):
  - круг: центр (300, 280), радиус 150, зазор ~50 сверху (244.95..295.05 градусов);
  - ихтис: хвост (215, 280), голова (420, 280), концы хвоста (178, 248) / (178, 312);
  - толщина линии 15.

Палитра приложения (tailwind primary): градиент #fbbf24 (primary-300, верх-лево)
-> #b45309 (primary-600, низ-право); монохром #d97706 (primary-500).

Зависимости: Pillow (pip install Pillow). Запуск из корня репозитория:
    .venv/Scripts/python.exe scripts/generate_logo_icons.py
"""
from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
ICONS_DIR = ROOT / "static" / "icons"

# Палитра приложения (tailwind primary/amber)
GRAD_LIGHT = (0xFB, 0xBF, 0x24)  # primary-300
GRAD_DARK = (0xB4, 0x53, 0x09)   # primary-600

# Геометрия эмблемы (координаты знака 600x600, y вниз)
CIRCLE_C = (300.0, 280.0)
CIRCLE_R = 150.0
STROKE = 15.0
EMBLEM_DIAMETER = 2 * CIRCLE_R + STROKE  # 315 — диаметр знака с учётом strokes

# Зазор круга сверху: конечные точки дуги (236.6, 144.1) и (363.4, 144.1)
def _angle(px: float, py: float) -> float:
    return math.degrees(math.atan2(py - CIRCLE_C[1], px - CIRCLE_C[0])) % 360.0

GAP_START = _angle(363.4, 144.1)  # ~295.05 (правый конец зазора)
GAP_END = _angle(236.6, 144.1)    # ~244.95 (левый конец зазора)

# Ихтис: квадратичные Безье (P0, Q, P1)
FISH_BOTTOM = [
    ((178, 248), (197, 265), (215, 280)),
    ((215, 280), (317, 366), (420, 280)),
]
FISH_TOP = [
    ((178, 312), (197, 295), (215, 280)),
    ((215, 280), (317, 194), (420, 280)),
]

PWA_SIZES = [48, 72, 96, 144, 168, 192, 512]
SUPERSCALE = 4
EMBLEM_FILL = 0.76  # доля стороны иконки (безопасная зона maskable — круг 80%)


def _quad(p0, q, p1, n=120):
    """Точки квадратичной Безье."""
    out = []
    for i in range(n + 1):
        t = i / n
        mt = 1.0 - t
        x = mt * mt * p0[0] + 2 * mt * t * q[0] + t * t * p1[0]
        y = mt * mt * p0[1] + 2 * mt * t * q[1] + t * t * p1[1]
        out.append((x, y))
    return out


def _emblem_mask(size: int) -> Image.Image:
    """Маска эмблемы (белые линии на чёрном), size x size, со сглаживанием."""
    ss = size * SUPERSCALE
    scale = size * EMBLEM_FILL / EMBLEM_DIAMETER
    cx = cy = size / 2.0

    def tx(lx, ly):
        return ((lx - CIRCLE_C[0]) * scale + cx) * SUPERSCALE

    def ty(ly):
        return ((ly - CIRCLE_C[1]) * scale + cy) * SUPERSCALE

    mask = Image.new("L", (ss, ss), 0)
    d = ImageDraw.Draw(mask)
    w = max(1, round(STROKE * scale * SUPERSCALE))

    # Круг: большая дуга от правого конца зазора по часовой до левого (через низ).
    r = CIRCLE_R * scale * SUPERSCALE
    ccx, ccy = tx(*CIRCLE_C), ty(CIRCLE_C[1])
    bbox = [ccx - r, ccy - r, ccx + r, ccy + r]
    d.arc(bbox, GAP_START, 360, fill=255, width=w)
    d.arc(bbox, 0, GAP_END, fill=255, width=w)
    # Скруглённые концы дуги
    for gx, gy in ((236.6, 144.1), (363.4, 144.1)):
        ex, ey = tx(gx, gy), ty(gy)
        d.ellipse([ex - w / 2, ey - w / 2, ex + w / 2, ey + w / 2], fill=255)

    # Ихтис: полилинии из Безье + скруглённые концы
    for curve in (FISH_BOTTOM, FISH_TOP):
        pts = []
        for p0, q, p1 in curve:
            seg = _quad(p0, q, p1)
            if pts and abs(pts[-1][0] - seg[0][0]) < 1e-6 and abs(pts[-1][1] - seg[0][1]) < 1e-6:
                pts.extend(seg[1:])
            else:
                pts.extend(seg)
        d.line([(tx(x, y), ty(y)) for x, y in pts], fill=255, width=w, joint="curve")
        for px, py in (pts[0], pts[-1]):
            ex, ey = tx(px, py), ty(py)
            d.ellipse([ex - w / 2, ey - w / 2, ex + w / 2, ey + w / 2], fill=255)

    return mask.resize((size, size), Image.LANCZOS)


def _gradient(size: int) -> Image.Image:
    """Диагональный градиент primary-300 -> primary-600 вдоль оси знака
    (150,120) -> (460,520), отображённой на иконку."""
    x1, y1 = 150.0, 120.0
    x2, y2 = 460.0, 520.0
    dx, dy = x2 - x1, y2 - y1
    denom = dx * dx + dy * dy

    # Градиент знака покрывает только эмблему; за пределами — клэмпим края.
    scale = size * EMBLEM_FILL / EMBLEM_DIAMETER
    cx = cy = size / 2.0

    def to_local(px, py):
        return ((px - cx) / scale + CIRCLE_C[0], (py - cy) / scale + CIRCLE_C[1])

    res = 256
    img = Image.new("RGB", (res, res))
    px = img.load()
    for j in range(res):
        ly = to_local(0, (j + 0.5) * size / res)[1]
        for i in range(res):
            lx = to_local((i + 0.5) * size / res, 0)[0]
            t = max(0.0, min(1.0, ((lx - x1) * dx + (ly - y1) * dy) / denom))
            px[i, j] = tuple(round(a + (b - a) * t) for a, b in zip(GRAD_LIGHT, GRAD_DARK))
    return img.resize((size, size), Image.BILINEAR)


def render_icon(size: int) -> Image.Image:
    base = Image.new("RGB", (size, size), (0xFF, 0xFF, 0xFF))
    base.paste(_gradient(size), (0, 0), _emblem_mask(size))
    return base


def main() -> None:
    ICONS_DIR.mkdir(parents=True, exist_ok=True)
    for s in PWA_SIZES:
        render_icon(s).save(ICONS_DIR / f"icon-{s}x{s}.png", optimize=True)
        print(f"icon-{s}x{s}.png: OK")
    ico_master = render_icon(48)
    ico_master.save(
        ROOT / "static" / "favicon.ico",
        format="ICO",
        sizes=[(16, 16), (32, 32), (48, 48)],
    )
    print("favicon.ico: OK")


if __name__ == "__main__":
    main()
