"""Render the Jotva app + tray icons.

App icon: the vector mark (src/logoGeometry.js) on a light macOS-grid squircle -> icon-1024.png,
icon.png (512), icon.ico, icon.icns. Tray: a monochrome template silhouette of the three
sheets (with gaps so they read at 16px) -> tray-icon.png (16px) + tray-icon@2x.png (32px).

Run from the repo root: python3 scripts/render_icon.py  (needs Pillow)
"""
import json
import re
import subprocess
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "electron" / "assets"
GRADS = {  # mirrors COLORS in src/logoGeometry.js (top-right -> bottom-left)
    "front": [(0, "#d8fcff"), (.42, "#4e90f8"), (.78, "#a98cf6"), (1, "#ffc2f1")],
    "mid": [(0, "#6f88ff"), (.35, "#3452f6"), (1, "#110d55")],
    "back": [(0, "#b27dff"), (.35, "#7a3df6"), (1, "#1b0b52")],
}


def rounded_mask(size, box, radius):
    m = Image.new("L", size, 0)
    ImageDraw.Draw(m).rounded_rectangle(box, radius=radius, fill=255)
    return m


def app_icon():
    S = 2048  # supersampled 1024
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    inset, body = 200, 1648  # Apple grid: 824/1024 body with 100px margin
    box = (inset, inset, inset + body, inset + body)
    radius = 370

    shadow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    shadow.putalpha(rounded_mask((S, S), (inset, inset + 24, inset + body, inset + body + 24), radius)
                    .point(lambda v: int(v * 0.45)).filter(ImageFilter.GaussianBlur(40)))
    img.alpha_composite(shadow)

    # Light white -> lavender body with a soft periwinkle glow behind the mark, so the
    # tile reads at full size on both light and dark Docks.
    t = np.linspace(0, 1, S)[:, None, None]
    body_rgb = (np.array([255, 255, 255]) * (1 - t) + np.array([232, 230, 250]) * t) * np.ones((1, S, 1))
    yy, xx = np.mgrid[0:S, 0:S]
    glow = np.clip(1 - np.hypot(xx - S / 2, yy - S * .47) / (body * .55), 0, 1) ** 1.6 * .6
    body_rgb = body_rgb * (1 - glow[..., None]) + np.array([200, 210, 255]) * glow[..., None]
    fill = Image.fromarray(np.dstack([body_rgb, np.full((S, S), 255)]).astype(np.uint8))
    img.paste(fill, (0, 0), rounded_mask((S, S), box, radius))

    img.alpha_composite(render_mark(S, target_w=int(body * 0.80), center=(S // 2, S // 2 + 10),
                                 shadow=0.32, shadow_rgb=(40, 30, 120)))

    return img.resize((1024, 1024), Image.LANCZOS)


def _hex(c):
    return np.array([int(c[i:i + 2], 16) for i in (1, 3, 5)], float)


def _ramp(t, stops):
    out = np.zeros(t.shape + (3,))
    for (o0, c0), (o1, c1) in zip(stops, stops[1:]):
        k = np.clip((t - o0) / (o1 - o0), 0, 1)[..., None]
        seg = (t >= o0) & (t <= o1)
        out[seg] = ((1 - k) * _hex(c0) + k * _hex(c1))[seg]
    return out


def render_mark(S, target_w, center, shadow=0.75, shadow_rgb=(3, 2, 26)):
    """Rasterise the three sheets like the SVG: gradient fill, rim light, drop shadow, bloom."""
    polys = dict(zip(("front", "mid", "back"), (sample(d, 48) for d in sheet_paths())))
    allp = [p for v in polys.values() for p in v]
    x0, x1 = min(p[0] for p in allp), max(p[0] for p in allp)
    y0, y1 = min(p[1] for p in allp), max(p[1] for p in allp)
    k = target_w / (x1 - x0)
    ox, oy = center[0] - (x0 + x1) / 2 * k, center[1] - (y0 + y1) / 2 * k
    out = Image.new("RGBA", (S, S), (0, 0, 0, 0))

    masks = {}
    for name, poly in polys.items():
        m = Image.new("L", (S, S), 0)
        ImageDraw.Draw(m).polygon([(x * k + ox, y * k + oy) for x, y in poly], fill=255)
        masks[name] = m

    bloom = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    for name, col in (("back", "#7a3df6"), ("mid", "#3452f6"), ("front", "#4e90f8")):
        layer = Image.new("RGBA", (S, S), tuple(int(v) for v in _hex(col)) + (0,))
        layer.putalpha(masks[name])
        bloom.alpha_composite(layer)
    bloom = bloom.filter(ImageFilter.GaussianBlur(22 * k))
    bloom.putalpha(bloom.getchannel("A").point(lambda v: int(v * 0.45)))
    out.alpha_composite(bloom)

    for name in ("back", "mid", "front"):
        m = masks[name]
        sh = Image.new("RGBA", (S, S), shadow_rgb + (0,))
        sh.putalpha(ImageChops.offset(m, int(-8 * k), int(10 * k)).filter(ImageFilter.GaussianBlur(16 * k))
                    .point(lambda v: int(v * shadow)))
        out.alpha_composite(sh)

        bx0, by0, bx1, by1 = m.getbbox()
        yy, xx = np.mgrid[0:S, 0:S].astype(float)
        u = (xx - bx0) / (bx1 - bx0); v = (yy - by0) / (by1 - by0)
        t = np.clip(((1 - u) + v) / 2, 0, 1)
        rgb = _ramp(t, GRADS[name])
        rim_w = max(1, int(3 * k))
        rim = (np.array(m, float) - np.array(m.filter(ImageFilter.MinFilter(2 * rim_w + 1)), float)) / 255
        rim_a = np.interp(t, [0, .5, 1], [.85, .18, 0]) * rim
        rgb = rgb * (1 - rim_a[..., None]) + 255 * rim_a[..., None]
        fill = Image.fromarray(np.dstack([np.clip(rgb, 0, 255), np.array(m)]).astype(np.uint8))
        out.alpha_composite(fill)
    return out


def sheet_paths():
    js = ("import('./src/logoGeometry.js').then(g => console.log(JSON.stringify("
          "[g.sheetPath(undefined, 0), ...g.BACK.map(m => g.sheetPath(m, 1))])))")
    out = subprocess.run(["node", "--input-type=module", "-e", js],
                         cwd=ROOT, capture_output=True, text=True, check=True).stdout
    return json.loads(out.strip().splitlines()[-1])  # [front, mid, back]


def sample(d, steps=24):
    toks = re.findall(r"[MCLZ]|-?\d+\.?\d*,-?\d+\.?\d*", d)
    pts, cur, i = [], None, 0
    while i < len(toks):
        t = toks[i]
        if t in "ML":
            cur = tuple(map(float, toks[i + 1].split(","))); pts.append(cur); i += 2
        elif t == "C":
            p1, p2, p3 = (tuple(map(float, toks[i + k].split(","))) for k in (1, 2, 3))
            for s in range(1, steps + 1):
                u = s / steps; v = 1 - u
                pts.append(tuple(v**3 * a + 3 * v * v * u * b + 3 * v * u * u * c + u**3 * e
                                 for a, b, c, e in zip(cur, p1, p2, p3)))
            cur = p3; i += 4
        else:
            i += 1
    return pts


def tray_icon():
    S = 512
    front, mid, back = (sample(d) for d in sheet_paths())
    xs = [p[0] for p in front + mid + back]; ys = [p[1] for p in front + mid + back]
    scale = (S * 0.92) / max(max(xs) - min(xs), max(ys) - min(ys))
    ox = (S - (max(xs) - min(xs)) * scale) / 2 - min(xs) * scale
    oy = (S - (max(ys) - min(ys)) * scale) / 2 - min(ys) * scale
    alpha = Image.new("L", (S, S), 0)
    for poly in (back, mid, front):  # back to front: cut a gap, then fill
        shape = Image.new("L", (S, S), 0)
        ImageDraw.Draw(shape).polygon([(x * scale + ox, y * scale + oy) for x, y in poly], fill=255)
        gap = shape.filter(ImageFilter.MaxFilter(29))
        alpha = ImageChops.subtract(alpha, gap)
        alpha = ImageChops.lighter(alpha, shape)
    icon = Image.new("RGBA", (S, S), (0, 0, 0, 255))
    icon.putalpha(alpha)
    return icon


if __name__ == "__main__":
    icon = app_icon()
    icon.save(OUT / "icon-1024.png")
    icon.resize((512, 512), Image.LANCZOS).save(OUT / "icon.png")
    icon.save(OUT / "icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])

    with tempfile.TemporaryDirectory() as tmp:
        iconset = Path(tmp) / "icon.iconset"
        iconset.mkdir()
        for sz in (16, 32, 128, 256, 512):
            icon.resize((sz, sz), Image.LANCZOS).save(iconset / f"icon_{sz}x{sz}.png")
            icon.resize((sz * 2, sz * 2), Image.LANCZOS).save(iconset / f"icon_{sz}x{sz}@2x.png")
        subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(OUT / "icon.icns")], check=True)

    tray = tray_icon()
    tray.resize((16, 16), Image.LANCZOS).save(OUT / "tray-icon.png")
    tray.resize((32, 32), Image.LANCZOS).save(OUT / "tray-icon@2x.png")
    print("wrote icon-1024.png, icon.png, icon.ico, icon.icns, tray-icon.png, tray-icon@2x.png")
