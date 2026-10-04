"""Generate PWA / touch icons from the LifeFlow logo geometry (run once; PNGs are committed).

    python frontend/make_icons.py
"""
from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent.parent / "static" / "img" / "icons"
BRAND = (79, 70, 229)
ACCENT = (165, 180, 252)
SCALE = 4  # supersampling for smooth curves


def wave_points(size, inset):
    """Approximate the logo's path (M9 21.5 c ... in a 32x32 viewBox) with a polyline."""
    def cubic(p0, p1, p2, p3, n=24):
        pts = []
        for i in range(n + 1):
            t = i / n
            x = (1 - t) ** 3 * p0[0] + 3 * (1 - t) ** 2 * t * p1[0] + 3 * (1 - t) * t ** 2 * p2[0] + t ** 3 * p3[0]
            y = (1 - t) ** 3 * p0[1] + 3 * (1 - t) ** 2 * t * p1[1] + 3 * (1 - t) * t ** 2 * p2[1] + t ** 3 * p3[1]
            pts.append((x, y))
        return pts

    segs = [((9, 21.5), (11.2, 15.9), (13.4, 13.1), (15.6, 13.1)),
            ((15.6, 13.1), (18.6, 13.1), (18, 18.9), (21, 18.9)),
            ((21, 18.9), (22.2, 18.9), (23.2, 18), (24, 16.3))]
    pts = []
    for s in segs:
        pts += cubic(*s)
    span = size - 2 * inset
    return [(inset + x / 32 * span, inset + y / 32 * span) for x, y in pts]


def draw(size, maskable=False):
    big = size * SCALE
    img = Image.new("RGBA", (big, big), BRAND + (255,) if maskable else (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    inset = big * 0.18 if maskable else 0
    if not maskable:
        d.rounded_rectangle([0, 0, big - 1, big - 1], radius=big * 9 / 32, fill=BRAND)
    span = big - 2 * inset
    pts = wave_points(big, inset)
    r = span * 1.3 / 32  # stroke-width 2.6 in the 32-unit viewBox
    # Round stroke drawn as overlapping discs along a densely resampled path (no joint artefacts).
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        steps = max(int(((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5 / (r / 4)), 1)
        for i in range(steps + 1):
            x, y = x0 + (x1 - x0) * i / steps, y0 + (y1 - y0) * i / steps
            d.ellipse([x - r, y - r, x + r, y + r], fill="white")
    cx, cy, r = inset + 23.6 / 32 * span, inset + 11.4 / 32 * span, 2 / 32 * span
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=ACCENT)
    return img.resize((size, size), Image.LANCZOS)


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for size in (192, 512):
        draw(size).save(OUT / f"icon-{size}.png")
        draw(size, maskable=True).save(OUT / f"maskable-{size}.png")
    draw(180, maskable=True).convert("RGB").save(OUT / "apple-touch-icon.png")
    print("icons written to", OUT)
