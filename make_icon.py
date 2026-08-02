"""Generate the app icon: a slime holding a photo.

    python3 make_icon.py

Writes icon.png (1024) and icon.icns. Everything is drawn at 4x and
downsampled, so the curves come out clean without antialiasing tricks.
All colours and the layout constants live near the top -- change them
and re-run.
"""

import math
import shutil
import subprocess
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

S = 4096
K = S // 1024

# --- palette -------------------------------------------------------------
# Swap PALETTE to change the whole icon. Backgrounds are a soft vertical
# gradient; the slime keeps a darker rim so it stays legible at 32px.
PALETTES = {
    "mist": {          # pale periwinkle behind a cyan slime
        "bg_top": (232, 240, 249), "bg_bottom": (203, 223, 238),
        "body": (77, 197, 222), "deep": (26, 129, 158), "light": (152, 231, 243),
    },
    "mint": {          # soft green-grey, cooler
        "bg_top": (229, 243, 238), "bg_bottom": (200, 226, 222),
        "body": (82, 200, 216), "deep": (28, 130, 152), "light": (156, 233, 242),
    },
    "sand": {          # warm cream, strongest contrast against cyan
        "bg_top": (247, 240, 229), "bg_bottom": (232, 219, 202),
        "body": (72, 194, 222), "deep": (24, 124, 156), "light": (148, 229, 243),
    },
    "lilac": {         # muted lavender, softest overall
        "bg_top": (238, 234, 248), "bg_bottom": (214, 208, 236),
        "body": (86, 196, 226), "deep": (30, 126, 162), "light": (158, 230, 245),
    },
}
PALETTE = PALETTES["lilac"]

BG_TOP = PALETTE["bg_top"] + (255,)
BG_BOTTOM = PALETTE["bg_bottom"] + (255,)
SLIME_BODY = PALETTE["body"] + (255,)
SLIME_DEEP = PALETTE["deep"] + (255,)
SLIME_LIGHT = PALETTE["light"] + (255,)
SHINE = (255, 255, 255, 215)

CARD = (255, 255, 255, 255)
CARD_EDGE = (186, 198, 214, 255)
SKY = (154, 200, 236, 255)
SUN = (255, 202, 106, 255)
HILL = (52, 74, 102, 255)
HILL_BACK = (96, 124, 156, 255)

FACE = (22, 38, 50, 255)
BLUSH = (255, 138, 150, 125)
DROP_SHADOW = (58, 96, 126, 105)

# macOS 26 masks app icons into the squircle itself, so the artwork is
# full-bleed and draws no corners of its own. Flip DRAW_OWN_CORNERS on if
# you need this to look right on macOS 15 or earlier, which does not mask.
# Apple's macOS app icon grid: a 1024x1024 document with the icon body
# occupying 824x824 (a 100px margin all round) and a corner radius of 185.4.
# Every app in the Dock is built to this, which is what makes icons line up at
# the same visual size. macOS does not apply the mask for you on macOS, so the
# artwork supplies its own corners.
#
# The scene below is drawn across the whole canvas and scaled down onto the
# 824 body at the end -- so CORNER_RADIUS is expressed pre-scale and works out
# to 185.4 once it lands on the grid.
DRAW_OWN_CORNERS = True
ICON_BODY = 824
CORNER_RADIUS = round(185.4 * 1024 / ICON_BODY) * K

# The Dock renders Finder-stamped custom icons by cropping the image to its
# visible content and scaling THAT to the tile slot -- fully transparent
# margins are discarded, which is why changing ICON_BODY never changed the
# rendered size. An almost-invisible veil (alpha 2/255) across the whole
# canvas pins the content bounds to the full 1024 square, so the 824 body
# lands at 824/1024 of the slot like every native Tahoe icon. If the Dock
# ever ignores the veil, raise this a little; it stays imperceptible below
# ~8.
BOUNDS_PIN_ALPHA = 2

CX = 512 * K
BASE_Y = 738 * K
HALF_W = 412 * K
BODY_H = 486 * K
EYE_Y = 396 * K
CARD_W, CARD_H = 396 * K, 270 * K
CARD_TOP = 520 * K


def slime_outline(cx, base_y, half_w, height, bumps=4, amp=None):
    """Dome across the top, wavy skirt along the bottom."""
    amp = amp if amp is not None else 24 * K
    points = []
    steps = 200
    for i in range(steps + 1):
        angle = math.pi * (1 - i / steps)
        points.append((cx + half_w * math.cos(angle), base_y - height * math.sin(angle)))
    base_steps = 160
    for i in range(base_steps + 1):
        t = i / base_steps
        x = cx + half_w - 2 * half_w * t
        y = base_y + amp * math.sin(bumps * math.pi * t) * (1 - abs(0.5 - t) * 0.5)
        points.append((x, y))
    return points


def build_card():
    pad = 18 * K
    canvas = Image.new("RGBA", (CARD_W + 40 * K, CARD_H + 40 * K), (0, 0, 0, 0))
    ox, oy = 20 * K, 20 * K

    scene = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    sd = ImageDraw.Draw(scene)
    inner = (ox + pad, oy + pad, ox + CARD_W - pad, oy + CARD_H - pad)
    sd.rectangle(inner, fill=SKY)
    sun_r = 26 * K
    sx, sy = ox + CARD_W - 74 * K, oy + 68 * K
    sd.ellipse((sx - sun_r, sy - sun_r, sx + sun_r, sy + sun_r), fill=SUN)
    sd.polygon(
        [(ox + pad, oy + CARD_H - pad), (ox + 122 * K, oy + 92 * K), (ox + 208 * K, oy + CARD_H - pad)],
        fill=HILL_BACK,
    )
    sd.polygon(
        [(ox + 108 * K, oy + CARD_H - pad), (ox + 198 * K, oy + 118 * K), (ox + CARD_W - pad, oy + CARD_H - pad)],
        fill=HILL,
    )

    mask = Image.new("L", canvas.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle(inner, radius=10 * K, fill=255)

    cd = ImageDraw.Draw(canvas)
    cd.rounded_rectangle(
        (ox, oy, ox + CARD_W, oy + CARD_H),
        radius=22 * K, fill=CARD, outline=CARD_EDGE, width=4 * K,
    )
    canvas.paste(scene, (0, 0), mask)
    return canvas.rotate(7, resample=Image.BICUBIC, expand=True)


ICONSET_SIZES = [
    ("icon_16x16.png", 16), ("icon_16x16@2x.png", 32),
    ("icon_32x32.png", 32), ("icon_32x32@2x.png", 64),
    ("icon_128x128.png", 128), ("icon_128x128@2x.png", 256),
    ("icon_256x256.png", 256), ("icon_256x256@2x.png", 512),
    ("icon_512x512.png", 512), ("icon_512x512@2x.png", 1024),
]


def write_icns(master: Image.Image) -> None:
    """Build icon.icns with every size macOS expects.

    Pillow's own .icns writer skips the 16 and 32 point @1x variants, so
    Finder list view and the menu bar end up scaling down from 128. iconutil
    is Apple's own tool and gets the set right; Pillow is the fallback for
    building on anything that isn't a Mac.
    """
    iconutil = shutil.which("iconutil")
    if not iconutil:
        master.save("icon.icns")
        print("  (iconutil not found -- used Pillow, small sizes will be scaled)")
        return

    iconset = Path("icon.iconset")
    if iconset.exists():
        shutil.rmtree(iconset)
    iconset.mkdir()

    for name, size in ICONSET_SIZES:
        master.resize((size, size), Image.LANCZOS).save(iconset / name)

    subprocess.run(
        [iconutil, "-c", "icns", str(iconset), "-o", "icon.icns"],
        check=True,
    )
    shutil.rmtree(iconset)


def main():
    image = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    gradient = Image.new("RGBA", (1, S))
    gd = ImageDraw.Draw(gradient)
    for y in range(S):
        t = y / (S - 1)
        gd.point((0, y), fill=tuple(
            round(a + (b - a) * t) for a, b in zip(BG_TOP, BG_BOTTOM)
        ))
    gradient = gradient.resize((S, S))

    image.paste(gradient, (0, 0))

    shadow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).ellipse(
        (CX - 340 * K, BASE_Y + 4 * K, CX + 340 * K, BASE_Y + 76 * K), fill=DROP_SHADOW
    )
    image.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(18 * K)))

    body = slime_outline(CX, BASE_Y, HALF_W, BODY_H)
    draw.polygon(body, fill=SLIME_BODY)
    draw.polygon(
        slime_outline(CX, BASE_Y - 16 * K, HALF_W - 58 * K, BODY_H - 68 * K, amp=18 * K),
        fill=SLIME_LIGHT,
    )
    rim = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(rim).polygon(body, outline=SLIME_DEEP, width=9 * K)
    image.alpha_composite(rim)

    draw.ellipse((CX - 262 * K, 324 * K, CX - 140 * K, 396 * K), fill=SHINE)
    draw.ellipse((CX - 118 * K, 298 * K, CX - 70 * K, 338 * K), fill=SHINE)

    for side in (-1, 1):
        ex = CX + side * 118 * K
        draw.ellipse((ex - 32 * K, EYE_Y - 42 * K, ex + 32 * K, EYE_Y + 42 * K), fill=FACE)
        draw.ellipse((ex - 22 * K, EYE_Y - 33 * K, ex - 3 * K, EYE_Y - 11 * K), fill=(255, 255, 255, 240))

    draw.arc(
        (CX - 38 * K, EYE_Y + 30 * K, CX + 38 * K, EYE_Y + 94 * K),
        start=15, end=165, fill=FACE, width=13 * K,
    )
    for side in (-1, 1):
        bx = CX + side * 222 * K
        draw.ellipse((bx - 41 * K, EYE_Y + 8 * K, bx + 41 * K, EYE_Y + 52 * K), fill=BLUSH)

    card = build_card()
    image.alpha_composite(card, (CX - card.width // 2, CARD_TOP))

    arm_r = 69 * K
    arm_y = CARD_TOP + card.height // 2 + 8 * K
    for side in (-1, 1):
        ax = CX + side * 220 * K
        draw.ellipse((ax - arm_r, arm_y - arm_r, ax + arm_r, arm_y + arm_r), fill=SLIME_BODY)
        draw.ellipse(
            (ax - arm_r, arm_y - arm_r, ax + arm_r, arm_y + arm_r), outline=SLIME_DEEP, width=8 * K
        )
        draw.ellipse(
            (ax - arm_r + 15 * K, arm_y - arm_r + 13 * K, ax - 8 * K, arm_y - 18 * K),
            fill=SLIME_LIGHT,
        )

    if DRAW_OWN_CORNERS:
        body = image.resize((ICON_BODY, ICON_BODY), Image.LANCZOS)
        final = Image.new("RGBA", (1024, 1024), (0, 0, 0, BOUNDS_PIN_ALPHA))
        offset = (1024 - ICON_BODY) // 2
        final.paste(body, (offset, offset), body)
    else:
        final = image.resize((1024, 1024), Image.LANCZOS)

    # Full-bleed square for Icon Composer / the native macOS 26 pipeline.
    # No rounded corners, no margins: once compiled into an asset catalog,
    # the SYSTEM masks and sizes it, which is what makes native icons land
    # at the same size as every other app with no measuring on our side.
    image.resize((1024, 1024), Image.LANCZOS).save("icon-native.png")

    if DRAW_OWN_CORNERS:
        corner = Image.new("L", (S, S), 0)
        ImageDraw.Draw(corner).rounded_rectangle(
            (0, 0, S - 1, S - 1), radius=CORNER_RADIUS, fill=255
        )
        image.putalpha(ImageChops.multiply(image.split()[3], corner))

    final.save("icon.png")
    write_icns(final)

    # In-app copy: the 824 body with the grid margin cropped off, so dialogs
    # and the window icon show the artwork at full size instead of floating
    # small inside transparent padding.
    if DRAW_OWN_CORNERS:
        offset = (1024 - ICON_BODY) // 2
        body = final.crop((offset, offset, offset + ICON_BODY, offset + ICON_BODY))
    else:
        body = final
    body.resize((512, 512), Image.LANCZOS).save("icon-app.png")

    print("wrote icon.png, icon.icns and icon-app.png")


if __name__ == "__main__":
    main()
