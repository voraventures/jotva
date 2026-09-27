#!/usr/bin/env python3
"""The DMG window background (the install window: drag Jotva to Applications).

  python3 scripts/make-dmg-background.py   → build/background.tiff (+ the 1x/2x PNGs)

Dark like the website, with the glass notepad and "Jotva" at the top and soft light
pools under the two icons, and Wisely drawing a dotted ink trail from Jotva to Applications. Icon positions must match
build.dmg.contents in package.json (app at x=160, Applications at x=440, y=205).
"""
import math
import os
import subprocess

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
W, H = 600, 400
APP, APPS, ICON_Y = (160, 205), (440, 205), 205
BG = (5, 5, 7)
BRAND = [(90, 130, 240), (107, 88, 230), (150, 96, 238)]
TRAIL = [(110, 160, 255), (123, 108, 246), (177, 125, 248), (255, 170, 230)]  # ink: blue → violet → pink
FONTS = ["/Applications/Blender.app/Contents/Resources/5.2/datafiles/fonts/Inter.woff2",
         os.path.join(ROOT, "design-reference/redesign/fonts/inter-0.woff2")]
MARK = os.path.join(ROOT, "electron/assets/logo-mark-render.png")  # the Blender-rendered notepad
WISELY = os.path.join(ROOT, "electron/assets/wisely-cutout.png")  # Wisely, nib pointing to Applications


def inter(size, weight):
    for p in FONTS:
        if os.path.exists(p):
            f = ImageFont.truetype(p, size)
            try:
                f.set_variation_by_axes([min(32, max(14, size)), weight])
            except Exception:
                pass
            return f
    return ImageFont.load_default()


def glow(img, cx, cy, r, color, strength):
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.ellipse((cx - r, cy - r * 0.8, cx + r, cy + r * 0.8), fill=(*color, strength))
    layer = layer.filter(ImageFilter.GaussianBlur(r * 0.45))
    img.alpha_composite(layer)


def draw(scale):
    s = scale
    img = Image.new("RGBA", (W * s, H * s), (*BG, 255))
    # soft light pools under the two icons, and a faint wash behind the title
    glow(img, APP[0] * s, (ICON_Y + 8) * s, 120 * s, (122, 61, 246), 120)
    glow(img, APPS[0] * s, (ICON_Y + 8) * s, 120 * s, (52, 82, 246), 110)
    glow(img, W / 2 * s, 50 * s, 170 * s, (78, 144, 248), 40)

    d = ImageDraw.Draw(img)
    # title: the rendered notepad mark + "Jotva"
    title_font = inter(34 * s, 650)
    tw = d.textlength("Jotva", font=title_font)
    mark_h = 46 * s
    mark_w = 0
    if os.path.exists(MARK):
        m = Image.open(MARK).convert("RGBA")
        m = m.crop(m.getbbox())
        mark_w = int(m.width * mark_h / m.height)
        m = m.resize((mark_w, mark_h), Image.LANCZOS)
    gap = 12 * s
    x0 = int((W * s - (mark_w + gap + tw)) / 2)
    y_mid = 46 * s
    if mark_w:
        img.alpha_composite(m, (x0, int(y_mid - mark_h / 2)))
    d.text((x0 + mark_w + gap, y_mid), "Jotva", font=title_font, fill=(244, 245, 255), anchor="lm")

    # Wisely draws the way: a dotted ink trail arcs from Jotva over to Applications and
    # ends at the tip of his nib, right at the folder's corner.
    if os.path.exists(WISELY):
        wz = Image.open(WISELY).convert("RGBA")
        wh = 86 * s
        wz = wz.resize((int(wz.width * wh / wz.height), wh), Image.LANCZOS)
        wx, wy = 370 * s - wz.width / 2, 116 * s - wh / 2              # top-left of Wisely
        nib = (wx + wz.width * 0.9, wy + wh * 0.985)                   # his nib (bottom-right after mirroring)
        start, ctrl = (APP[0] + 52) * s, ICON_Y - 48
        x0, y0, x2, y2 = start, ctrl * s, nib[0] - 4 * s, nib[1] - 4 * s
        cx, cy = (x0 + x2) / 2, min(y0, y2) - 62 * s
        trail = Image.new("RGBA", img.size, (0, 0, 0, 0))
        td = ImageDraw.Draw(trail)
        n = 24
        for i in range(n):
            t = i / (n - 1)
            x = (1 - t) ** 2 * x0 + 2 * (1 - t) * t * cx + t * t * x2
            y = (1 - t) ** 2 * y0 + 2 * (1 - t) * t * cy + t * t * y2
            k = min(len(TRAIL) - 2, int(t * (len(TRAIL) - 1)))
            u = t * (len(TRAIL) - 1) - k
            c = tuple(int(TRAIL[k][j] + (TRAIL[k + 1][j] - TRAIL[k][j]) * u) for j in range(3))
            r = (1.5 + 2.1 * t) * s
            td.ellipse((x - r, y - r, x + r, y + r), fill=(*c, 255))
        img.alpha_composite(trail.filter(ImageFilter.GaussianBlur(6 * s)))
        img.alpha_composite(trail)
        glow(img, 370 * s, 118 * s, 52 * s, (150, 110, 255), 60)
        img.alpha_composite(wz, (int(wx), int(wy)))

    # hint
    hint = inter(13 * s, 500)
    d.text((W / 2 * s, 352 * s), "Drag Jotva to Applications", font=hint, fill=(169, 169, 192), anchor="mm")
    return img.convert("RGB")


if __name__ == "__main__":
    out = os.path.join(ROOT, "build")
    os.makedirs(out, exist_ok=True)
    one, two = os.path.join(out, "background.png"), os.path.join(out, "background@2x.png")
    draw(1).save(one)
    draw(2).save(two)
    subprocess.run(["tiffutil", "-cathidpicheck", one, two, "-out", os.path.join(out, "background.tiff")], check=True)
    print("wrote build/background.tiff")
