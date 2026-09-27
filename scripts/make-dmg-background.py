#!/usr/bin/env python3
"""The DMG window background (the install window: drag Jotva to Applications).

  python3 scripts/make-dmg-background.py   → build/background.tiff (+ the 1x/2x PNGs)

Dark like the website, with the glass notepad and "Jotva" at the top and soft light
pools under the two icons, and Wisely between them pointing the way. Icon positions must match
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
    glow(img, W / 2 * s, 64 * s, 170 * s, (78, 144, 248), 40)

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
    y_mid = 62 * s
    if mark_w:
        img.alpha_composite(m, (x0, int(y_mid - mark_h / 2)))
    d.text((x0 + mark_w + gap, y_mid), "Jotva", font=title_font, fill=(244, 245, 255), anchor="lm")

    # Wisely between the icons, his nib pointing the way to Applications
    if os.path.exists(WISELY):
        wz = Image.open(WISELY).convert("RGBA")
        wh = 126 * s
        wz = wz.resize((int(wz.width * wh / wz.height), wh), Image.LANCZOS)
        glow(img, W / 2 * s, (ICON_Y - 2) * s, 70 * s, (150, 110, 255), 70)
        img.alpha_composite(wz, (int(W / 2 * s - wz.width / 2), int((ICON_Y - 6) * s - wh / 2)))

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
