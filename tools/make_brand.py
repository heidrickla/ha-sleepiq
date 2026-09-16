"""Generate the in-repo brand images.

A custom integration carries its own brand images and no pull request against
home-assistant/brands is needed. HACS reads custom_components/<domain>/brand/,
and Home Assistant serves the files at
/api/brands/integration/<domain>/<file> - the middle `integration/` segment is
required.

Sizes are exact requirements, not suggestions:

    icon.png       256x256 exactly
    icon@2x.png    512x512 exactly
    logo.png       shortest side 128-256
    logo@2x.png    shortest side 256-512

The mark is what the integration does: a bed seen from the side, with the
motion arcs of a massage running out of both ends. Palette and geometry match
the sibling integrations - navy body, cyan panel, amber for the action.

Everything is drawn at SUPERSAMPLE times the output size and reduced with
LANCZOS, because PIL's arc and rounded_rectangle do not anti-alias.

    python tools/make_brand.py
"""

from __future__ import annotations

import os

from PIL import Image, ImageDraw

DOMAIN = "sleepiq_massage"
SUPERSAMPLE = 4
PAD_FRAC = 0.06
# The mark's own height as a fraction of the square box: headboard top to the
# bottom of the legs. Checked against the rendered alpha bounding box below.
MARK_H_FRAC = 0.78

CLEAR = (0, 0, 0, 0)
BODY = (34, 52, 86, 255)
MATTRESS = (72, 190, 232, 255)
PILLOW = (235, 245, 250, 255)
MOTION = (245, 176, 66, 255)


def draw(size: tuple[int, int], pad_frac: float) -> Image.Image:
    w, h = size
    img = Image.new("RGBA", size, CLEAR)
    d = ImageDraw.Draw(img)

    # Work in a square box centred on the canvas so the mark is the same on
    # the icon and the wide logo.
    side = min(w, h)
    pad = side * pad_frac
    box = side - 2 * pad
    x0 = (w - box) / 2
    y0 = (h - box) / 2

    def px(fx: float, fy: float) -> tuple[float, float]:
        return x0 + box * fx, y0 + box * fy

    def rect(
        fx0: float,
        fy0: float,
        fx1: float,
        fy1: float,
        fill: tuple[int, int, int, int],
        radius: float,
    ) -> None:
        a = px(fx0, fy0)
        b = px(fx1, fy1)
        d.rounded_rectangle([a, b], radius=box * radius, fill=fill)

    # Motion arcs first, so the bed sits over them. Two radii each side of a
    # common centre, opening outwards: the vibration glyph.
    cx, cy = px(0.52, 0.51)
    line = box * 0.045
    for radius in (0.34, 0.45):
        r = box * radius
        for start, end in ((150, 210), (-30, 30)):
            d.arc(
                [cx - r, cy - r, cx + r, cy + r],
                start=start,
                end=end,
                fill=MOTION,
                width=int(round(line)),
            )

    # Headboard, base rail and legs.
    rect(0.22, 0.12, 0.31, 0.70, BODY, 0.035)
    rect(0.22, 0.62, 0.82, 0.74, BODY, 0.030)
    rect(0.24, 0.72, 0.30, 0.90, BODY, 0.020)
    rect(0.74, 0.72, 0.80, 0.90, BODY, 0.020)

    # Mattress and pillow.
    rect(0.29, 0.42, 0.82, 0.63, MATTRESS, 0.035)
    rect(0.33, 0.30, 0.50, 0.45, PILLOW, 0.030)

    return img


def render(size: tuple[int, int]) -> Image.Image:
    big = (size[0] * SUPERSAMPLE, size[1] * SUPERSAMPLE)
    return draw(big, PAD_FRAC).resize(size, Image.LANCZOS)


SPECS = {
    "icon.png": (256, 256),
    "icon@2x.png": (512, 512),
    "logo.png": (512, 256),
    "logo@2x.png": (1024, 512),
}


def main() -> None:
    out = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "..",
        "custom_components",
        DOMAIN,
        "brand",
    )
    os.makedirs(out, exist_ok=True)
    for name, size in SPECS.items():
        render(size).save(os.path.join(out, name), "PNG", optimize=True)

    # Verify against the published rules rather than trusting the calls above:
    # the sizes, a transparent background, and a mark that fills the square
    # rather than floating in it.
    ok = True
    for name, (want_w, want_h) in SPECS.items():
        path = os.path.join(out, name)
        with Image.open(path) as im:
            w, h = im.size
            alpha = im.convert("RGBA").getchannel("A")
        if name.startswith("icon"):
            good = (w, h) == (want_w, want_h)
        else:
            short = min(w, h)
            good = (256 <= short <= 512) if "@2x" in name else (128 <= short <= 256)
        corners = [alpha.getpixel(p) for p in ((0, 0), (w - 1, 0), (0, h - 1))]
        transparent = all(a == 0 for a in corners)
        left, top, right, bottom = alpha.getbbox() or (0, 0, 0, 0)
        box = min(w, h) * (1 - 2 * PAD_FRAC)
        filled = (right - left) >= box * 0.88 and (bottom - top) >= box * MARK_H_FRAC - 2
        verdict = "OK" if good and transparent and filled else "FAILS THE RULE"
        print(
            f"  {name:14s} {w}x{h} {os.path.getsize(path)}B "
            f"transparent={transparent} filled={filled} {verdict}"
        )
        ok &= good and transparent and filled
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
