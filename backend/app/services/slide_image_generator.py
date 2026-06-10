"""
Rich, visually engaging slide image generator.

Renders each narrated section as a 1920x1080 PNG using PIL with multiple layout
templates. No PPTX or LibreOffice dependency - direct image composition with
brand colors, gradients, decorative shapes, and visual hierarchy.

Layout templates (auto-detected from section content):
- HERO: Title slide with massive gradient text and decorative shapes
- ANALOGY: Big metaphor slide ("Imagine..." / "Think of it like...")
- COMPARISON: Old vs New side-by-side cards
- NUMBERED: 3-5 numbered points/rules/principles
- KEY_POINTS: Grid of takeaway cards
- ARCHITECTURE: Stacked layer diagram
- DEFAULT: Title + body excerpt + side visual
- OUTRO: Closing slide with call-to-action
"""
import os
import re
import math
import random
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from app.services.content_parser import ParsedContent, ContentSection
from app.services import icon_library
from app.services import bible_diagrams

OMIT_FOCAL_ICONS = False
"""When True, layout functions skip focal/decorative brand icons so the
animation engine can reveal them on top via icon_reveal cues. Discs and tags
are also suppressed since the animation engine emits its own. Title text,
chips, body copy, footers and dividers always render."""

OMIT_BODY_TEXT = False
"""When True, the standalone body *paragraph* on the generic layouts (default,
analogy) is skipped so the backdrop stays clean for the animation engine - the
narration-synced kinetic beat captions carry that text instead. Structured
layouts (numbered/comparison/key_points/architecture) keep their cards."""

CANVAS_W, CANVAS_H = 1920, 1080

BG_DEEP = (10, 10, 46)         # #0a0a2e (matches index.html)
BG_DARK = (19, 19, 19)
PURPLE_LIGHT = (120, 85, 250)  # #7855FA
PURPLE_DARK = (75, 0, 170)     # #4B00AA
PURPLE_DEEP = (57, 22, 153)    # #391699
TEAL = (31, 221, 233)          # #1FDDE9
GREEN = (146, 221, 35)         # #92DD23
CORAL = (255, 145, 120)        # #FF9178
YELLOW = (255, 215, 0)
PINK = (255, 107, 157)
BLUE = (0, 188, 212)
WHITE = (255, 255, 255)
TEXT_MUTED = (184, 197, 214)   # #b8c5d6
TEXT_DIM = (102, 102, 119)
PANEL_BG = (255, 255, 255, 12)
CARD_BG = (255, 255, 255, 18)
CARD_BORDER = (255, 255, 255, 38)

ACCENT_PALETTES = [
    (TEAL, PURPLE_LIGHT),
    (CORAL, YELLOW),
    (GREEN, TEAL),
    (PINK, PURPLE_LIGHT),
    (YELLOW, CORAL),
    (BLUE, GREEN),
    (PURPLE_LIGHT, TEAL),
    (TEAL, GREEN),
]

FONT_PATHS = {
    "regular": [
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/Library/Fonts/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ],
    "bold": [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/Library/Fonts/Arial Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ],
    "black": [
        "/System/Library/Fonts/Supplemental/Arial Black.ttf",
        "/Library/Fonts/Arial Black.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ],
}


def _font(weight: str, size: int) -> ImageFont.FreeTypeFont:
    for path in FONT_PATHS.get(weight, FONT_PATHS["regular"]):
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def _make_gradient(size, top_color, bottom_color, direction="vertical"):
    """Create a smooth gradient image."""
    w, h = size
    img = Image.new("RGB", size, top_color)
    draw = ImageDraw.Draw(img)
    if direction == "vertical":
        for y in range(h):
            t = y / max(h - 1, 1)
            r = int(top_color[0] * (1 - t) + bottom_color[0] * t)
            g = int(top_color[1] * (1 - t) + bottom_color[1] * t)
            b = int(top_color[2] * (1 - t) + bottom_color[2] * t)
            draw.line([(0, y), (w, y)], fill=(r, g, b))
    else:
        for x in range(w):
            t = x / max(w - 1, 1)
            r = int(top_color[0] * (1 - t) + bottom_color[0] * t)
            g = int(top_color[1] * (1 - t) + bottom_color[1] * t)
            b = int(top_color[2] * (1 - t) + bottom_color[2] * t)
            draw.line([(x, 0), (x, h)], fill=(r, g, b))
    return img


def _glow_circle(size, color, alpha=180):
    """Create a soft glowing circle for decorative use."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([0, 0, size, size], fill=(color[0], color[1], color[2], alpha))
    img = img.filter(ImageFilter.GaussianBlur(radius=size // 6))
    return img


def _base_canvas(seed: int = 0) -> Image.Image:
    """Create the base background with subtle decorative elements."""
    rng = random.Random(seed)
    bg = _make_gradient(
        (CANVAS_W, CANVAS_H),
        (8, 8, 35),
        (18, 12, 60),
        direction="vertical",
    )
    overlay = Image.new("RGBA", bg.size, (0, 0, 0, 0))

    for _ in range(6):
        size = rng.randint(220, 480)
        x = rng.randint(-100, CANVAS_W - 100)
        y = rng.randint(-100, CANVAS_H - 100)
        color = rng.choice([PURPLE_LIGHT, TEAL, PURPLE_DEEP, BLUE])
        glow = _glow_circle(size, color, alpha=rng.randint(35, 70))
        overlay.paste(glow, (x, y), glow)

    bg = Image.alpha_composite(bg.convert("RGBA"), overlay)
    return bg.convert("RGB")


def _rounded_rect(draw: ImageDraw.ImageDraw, xy, radius, fill=None, outline=None, width=1):
    """Draw a rounded rectangle (PIL has this built-in but with awkward signature)."""
    draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=width)


def _draw_card(img: Image.Image, xy, fill=(255, 255, 255, 18), border=(255, 255, 255, 50), border_w=2, radius=24):
    """Draw a translucent card panel onto an RGB image."""
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    _rounded_rect(d, xy, radius=radius, fill=fill, outline=border, width=border_w)
    return Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")


def _wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int, draw: ImageDraw.ImageDraw) -> list[str]:
    """Wrap text into lines that fit within max_width."""
    words = text.split()
    lines = []
    current = []
    for word in words:
        test = " ".join(current + [word])
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] - bbox[0] <= max_width or not current:
            current.append(word)
        else:
            lines.append(" ".join(current))
            current = [word]
    if current:
        lines.append(" ".join(current))
    return lines


def _draw_text(draw, xy, text, font, fill=WHITE, anchor="lt"):
    draw.text(xy, text, font=font, fill=fill, anchor=anchor)


def _draw_gradient_text(img: Image.Image, xy, text: str, font, color1, color2, anchor="lt"):
    """Draw text with a horizontal gradient fill via a glyph mask."""
    draw_temp = ImageDraw.Draw(img)
    lt_bbox = draw_temp.textbbox((0, 0), text, font=font, anchor="lt")
    text_w = max(lt_bbox[2] - lt_bbox[0], 1)
    text_h = max(lt_bbox[3] - lt_bbox[1], 1)

    pad_x = 8
    pad_y = 8
    canvas_w = text_w + pad_x * 2
    canvas_h = text_h + pad_y * 2

    grad = _make_gradient((canvas_w, canvas_h), color1, color2, direction="horizontal")
    mask = Image.new("L", (canvas_w, canvas_h), 0)
    mdraw = ImageDraw.Draw(mask)
    mdraw.text((pad_x - lt_bbox[0], pad_y - lt_bbox[1]), text, font=font, fill=255, anchor="lt")

    if anchor in ("mt", "mm", "ms", "mb"):
        paste_x = xy[0] - canvas_w // 2
    elif anchor in ("rt", "rm", "rs", "rb"):
        paste_x = xy[0] - canvas_w + pad_x
    else:
        paste_x = xy[0] - pad_x

    if anchor in ("mm", "rm", "lm"):
        paste_y = xy[1] - canvas_h // 2
    elif anchor in ("mb", "rb", "lb"):
        paste_y = xy[1] - canvas_h + pad_y
    else:
        paste_y = xy[1] - pad_y

    img.paste(grad, (paste_x, paste_y), mask)


def _draw_pill(img, xy, text, fg=WHITE, bg=PURPLE_LIGHT, font_size=24, padding=(20, 8), radius=20):
    """Draw a pill/badge with text inside."""
    font = _font("bold", font_size)
    draw_temp = ImageDraw.Draw(img)
    bbox = draw_temp.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    pill_w = tw + padding[0] * 2
    pill_h = th + padding[1] * 2

    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    pill_xy = (xy[0], xy[1], xy[0] + pill_w, xy[1] + pill_h)
    _rounded_rect(d, pill_xy, radius=radius, fill=bg + (220,))
    d.text((xy[0] + padding[0] - bbox[0], xy[1] + padding[1] - bbox[1]), text, font=font, fill=fg)
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    return img, pill_w, pill_h


def _logo_n(img: Image.Image, xy, size=64, color1=PURPLE_LIGHT, color2=TEAL):
    """Draw the Nutanix-style 'N' badge."""
    draw_temp = ImageDraw.Draw(img)
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    grad = _make_gradient((size, size), color1, color2, direction="vertical")
    mask = Image.new("L", (size, size), 0)
    md = ImageDraw.Draw(mask)
    md.rounded_rectangle([0, 0, size, size], radius=size // 5, fill=255)
    img_rgba = img.convert("RGBA")
    img_rgba.paste(grad.convert("RGBA"), xy, mask)
    img = img_rgba.convert("RGB")

    nfont = _font("black", int(size * 0.55))
    d2 = ImageDraw.Draw(img)
    d2.text((xy[0] + size // 2, xy[1] + size // 2), "N", font=nfont, fill=WHITE, anchor="mm")
    return img


def _footer(img: Image.Image, video_title: str, slide_num: int, total_slides: int):
    """Add a thin footer with brand + slide counter."""
    img = _logo_n(img, (60, CANVAS_H - 90), size=42)
    draw = ImageDraw.Draw(img)
    f = _font("regular", 20)
    draw.text((116, CANVAS_H - 79), "Video Nuggets OS", font=f, fill=TEXT_MUTED)
    draw.text((116, CANVAS_H - 55), video_title, font=_font("bold", 16), fill=TEXT_DIM)

    counter = f"{slide_num:02d} / {total_slides:02d}"
    cf = _font("bold", 22)
    bbox = draw.textbbox((0, 0), counter, font=cf)
    cw = bbox[2] - bbox[0]
    draw.rounded_rectangle(
        [CANVAS_W - 60 - cw - 24, CANVAS_H - 80, CANVAS_W - 60 + 12, CANVAS_H - 40],
        radius=20,
        outline=(255, 255, 255, 60),
        width=2,
    )
    draw.text((CANVAS_W - 60 - cw // 2 - 6, CANVAS_H - 60), counter, font=cf, fill=TEAL, anchor="mm")
    return img


# ---------------- Brand icon helpers ----------------

def _paste_icon(img: Image.Image, icon: Image.Image, center_xy: tuple[int, int],
                size: int, glow_color: tuple = None, glow_alpha: int = 140) -> Image.Image:
    """Paste a brand icon centered at center_xy at the requested size, optional glow halo."""
    if icon is None:
        return img
    cx, cy = center_xy
    icon_resized = icon.resize((size, size), Image.LANCZOS) if icon.size != (size, size) else icon

    img_rgba = img.convert("RGBA")
    if glow_color is not None:
        glow_size = size + size // 3
        glow = _glow_circle(glow_size, glow_color, alpha=glow_alpha)
        img_rgba.paste(glow, (cx - glow_size // 2, cy - glow_size // 2), glow)

    img_rgba.paste(icon_resized, (cx - size // 2, cy - size // 2), icon_resized)
    return img_rgba.convert("RGB")


def _draw_disc(img: Image.Image, center_xy: tuple[int, int], radius: int,
               fill: tuple, outline: tuple = None, outline_w: int = 0) -> Image.Image:
    """Draw a filled circle with optional outline as a separate composited layer."""
    cx, cy = center_xy
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    od.ellipse(
        [cx - radius, cy - radius, cx + radius, cy + radius],
        fill=fill,
        outline=outline,
        width=outline_w if outline else 0,
    )
    return Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")


def _icon_or_letter(
    title: str,
    body: str = "",
    fallback_letter: str = "N",
) -> tuple[Image.Image | None, str | None]:
    """Pick a brand icon based on section title + body. Title is weighted 3x.

    Returns (icon, concept_name) or (None, None).
    """
    text_for_match = f"{title} {body}" if body else title
    concept = icon_library.best_concept_for_text(text_for_match, title=title)
    if concept:
        icon = icon_library.get_icon(concept, size=512)
        if icon is not None:
            return icon, concept
    return None, None


# ---------------- Layout: HERO ----------------

def render_hero(title: str, subtitle: str = "Video Nuggets OS") -> Image.Image:
    img = _base_canvas(seed=hash(title) & 0xFFFF)

    hero_icon = icon_library.best_icon_for_text(title, fallback="cloud_node", title=title)
    if hero_icon is not None and not OMIT_FOCAL_ICONS:
        icon_cx = 280
        icon_cy = CANVAS_H // 2
        img = _draw_disc(img, (icon_cx, icon_cy), 220,
                         fill=PURPLE_LIGHT + (40,), outline=TEAL + (200,), outline_w=3)
        img = _paste_icon(img, hero_icon, (icon_cx, icon_cy), 320,
                          glow_color=PURPLE_LIGHT, glow_alpha=160)

    img = _logo_n(img, (560, 220), size=80)

    title_font = _font("black", 96)
    draw = ImageDraw.Draw(img)
    title_x = 660
    lines = _wrap_text(title, title_font, CANVAS_W - title_x - 80, draw)
    y = 340
    for line in lines[:3]:
        _draw_gradient_text(img, (title_x, y), line, title_font, TEAL, PURPLE_LIGHT)
        y += 110

    sf = _font("regular", 32)
    draw = ImageDraw.Draw(img)
    draw.text((title_x, y + 20), subtitle, font=sf, fill=TEXT_MUTED)

    img, _, _ = _draw_pill(img, (title_x, y + 80), "Learn it the fun way",
                           bg=PURPLE_LIGHT, font_size=26)
    return img


# ---------------- Layout: ANALOGY ----------------

def render_analogy(title: str, body: str, slide_num: int, total: int, video_title: str, accent=None) -> Image.Image:
    img = _base_canvas(seed=hash(title) & 0xFFFF)
    accent = accent or ACCENT_PALETTES[slide_num % len(ACCENT_PALETTES)]

    img, _, _ = _draw_pill(img, (80, 80), f"ANALOGY {slide_num:02d}", bg=accent[0], font_size=24)

    icon_size = 360
    icon_cx = 280
    icon_cy = 460

    if not OMIT_FOCAL_ICONS:
        img = _draw_disc(img, (icon_cx, icon_cy), icon_size // 2 + 30,
                         fill=accent[0] + (45,), outline=accent[1] + (180,), outline_w=3)

    brand_icon, matched_concept = _icon_or_letter(title, body)
    if brand_icon is not None and not OMIT_FOCAL_ICONS:
        img = _paste_icon(img, brand_icon, (icon_cx, icon_cy), icon_size,
                          glow_color=accent[0], glow_alpha=130)
    elif not OMIT_FOCAL_ICONS:
        draw = ImageDraw.Draw(img)
        symbol = _pick_analogy_symbol(title, body)
        icon_font = _font("black", 200)
        draw.text((icon_cx, icon_cy), symbol, font=icon_font, fill=WHITE, anchor="mm")

    title_font = _font("black", 76)
    text_x = 560
    draw = ImageDraw.Draw(img)
    title_lines = _wrap_text(title, title_font, CANVAS_W - text_x - 80, draw)
    y = 220
    for line in title_lines[:2]:
        _draw_gradient_text(img, (text_x, y), line, title_font, accent[0], accent[1])
        y += 92

    label_font = _font("bold", 28)
    draw = ImageDraw.Draw(img)
    draw.text((text_x, y + 20), "Imagine this...", font=label_font, fill=accent[0])

    if not OMIT_BODY_TEXT:
        body_excerpt = _first_sentences(body, 3)
        bf = _font("regular", 30)
        body_lines = _wrap_text(body_excerpt, bf, CANVAS_W - text_x - 80, ImageDraw.Draw(img))
        draw = ImageDraw.Draw(img)
        body_y = y + 80
        for line in body_lines[:8]:
            draw.text((text_x, body_y), line, font=bf, fill=WHITE)
            body_y += 46

    if matched_concept and not OMIT_FOCAL_ICONS:
        tag_font = _font("bold", 18)
        tag_text = matched_concept.replace("_", " ").upper()
        draw.text((icon_cx, icon_cy + icon_size // 2 + 60), tag_text,
                  font=tag_font, fill=accent[1], anchor="mm")

    return _footer(img, video_title, slide_num, total)


def _pick_analogy_symbol(title: str, body: str) -> str:
    """Pick a single thematic glyph based on title/body keywords."""
    combined = f"{title} {body}".lower()
    mapping = [
        (["lego", "brick", "block", "build"], "B"),
        (["castle", "tower", "house", "building"], "H"),
        (["library", "book", "book"], "L"),
        (["pizza", "slice", "food", "kitchen"], "P"),
        (["car", "engine", "drive"], "C"),
        (["water", "river", "stream", "flow"], "F"),
        (["map", "city", "street"], "M"),
        (["robot", "machine", "automation"], "R"),
        (["team", "people", "friends"], "T"),
        (["ship", "boat", "sail"], "S"),
        (["super", "hero", "amazing"], "X"),
        (["clock", "time", "fast"], "T"),
    ]
    for kws, sym in mapping:
        if any(kw in combined for kw in kws):
            return sym
    keyword = _extract_keyword(title)
    return keyword[0].upper() if keyword else "i"


# ---------------- Layout: COMPARISON ----------------

def render_comparison(title: str, body: str, slide_num: int, total: int, video_title: str) -> Image.Image:
    img = _base_canvas(seed=hash(title) & 0xFFFF)
    img, _, _ = _draw_pill(img, (80, 80), "COMPARE", bg=YELLOW, fg=BG_DEEP, font_size=24)

    title_font = _font("black", 64)
    draw = ImageDraw.Draw(img)
    title_lines = _wrap_text(title, title_font, CANVAS_W - 160, draw)
    y = 160
    for line in title_lines[:2]:
        _draw_gradient_text(img, (80, y), line, title_font, TEAL, PURPLE_LIGHT)
        y += 76

    card_w = 760
    card_h = 540
    card_y = 360
    left_x = 100
    right_x = CANVAS_W - card_w - 100

    img = _draw_card(img, (left_x, card_y, left_x + card_w, card_y + card_h), fill=CORAL + (40,), border=CORAL + (180,), radius=24, border_w=3)
    img = _draw_card(img, (right_x, card_y, right_x + card_w, card_y + card_h), fill=TEAL + (40,), border=TEAL + (180,), radius=24, border_w=3)

    label_font = _font("black", 40)
    draw = ImageDraw.Draw(img)
    draw.text((left_x + 40, card_y + 30), "TRADITIONAL", font=label_font, fill=CORAL)
    draw.text((right_x + 40, card_y + 30), "NUTANIX WAY", font=label_font, fill=TEAL)

    sub_font = _font("bold", 26)
    draw.text((left_x + 40, card_y + 90), "The old approach", font=sub_font, fill=TEXT_MUTED)
    draw.text((right_x + 40, card_y + 90), "The modern approach", font=sub_font, fill=TEXT_MUTED)

    if not OMIT_FOCAL_ICONS:
        left_icon = icon_library.get_icon("three_tier", size=256) or icon_library.get_icon("silos", size=256) or icon_library.get_icon("datacenter", size=256)
        right_icon = icon_library.get_icon("distributed_cloud", size=256) or icon_library.get_icon("cluster", size=256) or icon_library.get_icon("cloud_node", size=256)
        if left_icon is not None:
            img = _paste_icon(img, left_icon, (left_x + card_w - 100, card_y + 80), 110)
        if right_icon is not None:
            img = _paste_icon(img, right_icon, (right_x + card_w - 100, card_y + 80), 110)

    left_points, right_points = _split_comparison_points(body)
    bf = _font("regular", 26)
    bullet_y = card_y + 160
    for pt in left_points[:4]:
        draw.ellipse([left_x + 40, bullet_y + 10, left_x + 56, bullet_y + 26], fill=CORAL)
        wrapped = _wrap_text(pt, bf, card_w - 100, draw)
        for line in wrapped[:2]:
            draw.text((left_x + 70, bullet_y), line, font=bf, fill=WHITE)
            bullet_y += 36
        bullet_y += 16
    bullet_y = card_y + 160
    for pt in right_points[:4]:
        draw.ellipse([right_x + 40, bullet_y + 10, right_x + 56, bullet_y + 26], fill=TEAL)
        wrapped = _wrap_text(pt, bf, card_w - 100, draw)
        for line in wrapped[:2]:
            draw.text((right_x + 70, bullet_y), line, font=bf, fill=WHITE)
            bullet_y += 36
        bullet_y += 16

    vs_size = 96
    vs_x = (left_x + card_w + right_x) // 2 - vs_size // 2
    vs_y = card_y + card_h // 2 - vs_size // 2
    img = _draw_card(img, (vs_x, vs_y, vs_x + vs_size, vs_y + vs_size), fill=YELLOW + (220,), border=WHITE + (255,), radius=vs_size // 2, border_w=4)
    draw = ImageDraw.Draw(img)
    vsf = _font("black", 36)
    draw.text((vs_x + vs_size // 2, vs_y + vs_size // 2), "VS", font=vsf, fill=BG_DEEP, anchor="mm")

    return _footer(img, video_title, slide_num, total)


# ---------------- Layout: NUMBERED ----------------

def render_numbered(title: str, body: str, slide_num: int, total: int, video_title: str) -> Image.Image:
    img = _base_canvas(seed=hash(title) & 0xFFFF)
    img, _, _ = _draw_pill(img, (80, 80), f"STEP {slide_num:02d}", bg=GREEN, fg=BG_DEEP, font_size=24)

    title_font = _font("black", 64)
    draw = ImageDraw.Draw(img)
    title_lines = _wrap_text(title, title_font, CANVAS_W - 160, draw)
    y = 160
    for line in title_lines[:2]:
        _draw_gradient_text(img, (80, y), line, title_font, GREEN, TEAL)
        y += 76

    points = _extract_numbered_points(body)
    if len(points) < 3:
        points = _extract_sentences(body, 4)

    card_h = 130
    n = min(len(points), 5)
    card_w = (CANVAS_W - 200 - (n - 1) * 24) if n <= 3 else CANVAS_W - 200
    if n > 3:
        card_w = (CANVAS_W - 200) // 2 - 24
    bf = _font("regular", 24)

    cols = 3 if n <= 3 else 2
    rows = math.ceil(n / cols)
    grid_card_w = (CANVAS_W - 200 - (cols - 1) * 30) // cols
    grid_card_h = 220 if rows > 1 else 320
    grid_x0 = 100
    grid_y0 = 360

    palette = [TEAL, GREEN, CORAL, PINK, YELLOW, PURPLE_LIGHT]

    for i, point in enumerate(points[: cols * rows]):
        c = i % cols
        r = i // cols
        x = grid_x0 + c * (grid_card_w + 30)
        y_card = grid_y0 + r * (grid_card_h + 30)
        accent = palette[i % len(palette)]
        img = _draw_card(img, (x, y_card, x + grid_card_w, y_card + grid_card_h),
                         fill=accent + (40,), border=accent + (180,), radius=20, border_w=2)
        draw = ImageDraw.Draw(img)
        nf = _font("black", 64)
        draw.text((x + 40, y_card + 30), f"{i + 1:02d}", font=nf, fill=accent)
        wrapped = _wrap_text(point, bf, grid_card_w - 200, draw)
        py = y_card + 30
        for line in wrapped[: max(2, grid_card_h // 40 - 1)]:
            draw.text((x + 130, py), line, font=bf, fill=WHITE)
            py += 36

        if not OMIT_FOCAL_ICONS:
            point_icon = icon_library.best_icon_for_text(point, fallback="lightbulb")
            if point_icon is not None:
                ic_size = 80 if grid_card_h < 250 else 110
                ic_cx = x + grid_card_w - ic_size // 2 - 20
                ic_cy = y_card + grid_card_h // 2
                img = _paste_icon(img, point_icon, (ic_cx, ic_cy), ic_size)

    return _footer(img, video_title, slide_num, total)


# ---------------- Layout: KEY POINTS ----------------

def render_key_points(title: str, body: str, slide_num: int, total: int, video_title: str) -> Image.Image:
    img = _base_canvas(seed=hash(title) & 0xFFFF)
    img, _, _ = _draw_pill(img, (80, 80), "KEY TAKEAWAYS", bg=PURPLE_LIGHT, font_size=24)

    title_font = _font("black", 64)
    draw = ImageDraw.Draw(img)
    title_lines = _wrap_text(title, title_font, CANVAS_W - 160, draw)
    y = 160
    for line in title_lines[:2]:
        _draw_gradient_text(img, (80, y), line, title_font, PURPLE_LIGHT, TEAL)
        y += 76

    points = _extract_sentences(body, 4)
    bf = _font("regular", 24)
    palette = [TEAL, CORAL, GREEN, YELLOW]

    card_y = 380
    card_w = (CANVAS_W - 240) // min(len(points), 4)
    for i, point in enumerate(points[:4]):
        x = 100 + i * (card_w + 20)
        accent = palette[i]
        img = _draw_card(img, (x, card_y, x + card_w - 20, card_y + 540),
                         fill=accent + (50,), border=accent + (200,), radius=24, border_w=3)
        draw = ImageDraw.Draw(img)

        icon_size = 140
        icon_cx = x + (card_w - 20) // 2
        icon_cy = card_y + 60 + icon_size // 2

        if not OMIT_FOCAL_ICONS:
            point_icon = icon_library.best_icon_for_text(point, fallback="lightbulb")
            if point_icon is not None:
                img = _draw_disc(img, (icon_cx, icon_cy), icon_size // 2 + 12,
                                 fill=accent + (60,), outline=accent + (220,), outline_w=2)
                img = _paste_icon(img, point_icon, (icon_cx, icon_cy), icon_size)
            else:
                img = _draw_disc(img, (icon_cx, icon_cy), 50, fill=accent + (220,))
                nf = _font("black", 56)
                draw = ImageDraw.Draw(img)
                draw.text((icon_cx, icon_cy), str(i + 1), font=nf, fill=BG_DEEP, anchor="mm")

        draw = ImageDraw.Draw(img)
        wrapped = _wrap_text(point, bf, card_w - 60, draw)
        py = card_y + 60 + icon_size + 30
        for line in wrapped[:7]:
            draw.text((x + 30, py), line, font=bf, fill=WHITE)
            py += 36

        idx_font = _font("black", 28)
        draw.text((x + 30, card_y + 30), f"{i + 1:02d}", font=idx_font, fill=accent)

    return _footer(img, video_title, slide_num, total)


# ---------------- Layout: ARCHITECTURE ----------------

def render_architecture(title: str, body: str, slide_num: int, total: int, video_title: str) -> Image.Image:
    img = _base_canvas(seed=hash(title) & 0xFFFF)
    img, _, _ = _draw_pill(img, (80, 80), "ARCHITECTURE", bg=BLUE, font_size=24)

    title_font = _font("black", 64)
    draw = ImageDraw.Draw(img)
    title_lines = _wrap_text(title, title_font, CANVAS_W - 160, draw)
    y = 160
    for line in title_lines[:2]:
        _draw_gradient_text(img, (80, y), line, title_font, TEAL, PURPLE_LIGHT)
        y += 76

    layers = [
        ("Applications", "VMs, Containers, Databases, AI Workloads", PURPLE_LIGHT, "user_vms"),
        ("Platform Services", "Files, Objects, Volumes, Flow, Calm", TEAL, "nutanix_files"),
        ("Core (AOS + AHV)", "Distributed Storage Fabric, Hypervisor, CVM", GREEN, "cvm"),
        ("Infrastructure", "Compute, Memory, NVMe SSD, Network", CORAL, "server"),
    ]
    layer_w = CANVAS_W - 200
    layer_h = 130
    base_y = 360
    icon_size = 96

    for i, (name, desc, color, icon_concept) in enumerate(layers):
        y_layer = base_y + i * (layer_h + 14)
        img = _draw_card(img, (100, y_layer, 100 + layer_w, y_layer + layer_h),
                         fill=color + (60,), border=color + (200,), radius=18, border_w=2)
        draw = ImageDraw.Draw(img)
        lf = _font("black", 38)
        df = _font("regular", 24)
        draw.text((230, y_layer + 30), name, font=lf, fill=WHITE)
        draw.text((230, y_layer + 80), desc, font=df, fill=TEXT_MUTED)

        icon_cx = 100 + 70
        icon_cy = y_layer + layer_h // 2
        if not OMIT_FOCAL_ICONS:
            layer_icon = icon_library.get_icon(icon_concept, size=256)
            if layer_icon is not None:
                img = _draw_disc(img, (icon_cx, icon_cy), icon_size // 2 + 8,
                                 fill=color + (60,), outline=color + (220,), outline_w=2)
                img = _paste_icon(img, layer_icon, (icon_cx, icon_cy), icon_size)
            right_icon = icon_library.get_icon(
                ["application", "calm", "ahv", "storage"][i] if i < 4 else "node",
                size=256,
            )
            if right_icon is not None:
                img = _paste_icon(img, right_icon, (100 + layer_w - 80, icon_cy), 80)

    return _footer(img, video_title, slide_num, total)


# ---------------- Layout: BIBLE_DIAGRAM (canonical PDF figure showcase) ----------------

def render_bible_diagram(
    title: str, body: str, slide_num: int, total: int, video_title: str,
    diagram: dict,
) -> Image.Image:
    """Slide that showcases a diagram extracted from the Cloud Bible PDF.

    Layout:
        - Pill: 'CLOUD BIBLE - PAGE NN' (top-left, accent color)
        - Title: gradient, single line if possible
        - Short body excerpt: 1-2 sentences below the title
        - Diagram: scaled and centered in a glowing rounded white panel
        - Caption strip: source attribution under the diagram
        - Standard footer
    """
    img = _base_canvas(seed=hash(title) & 0xFFFF)
    accent = ACCENT_PALETTES[slide_num % len(ACCENT_PALETTES)]

    page_no = diagram.get("page", 0)
    img, _, _ = _draw_pill(img, (80, 80),
                           f"CLOUD BIBLE - PAGE {page_no:02d}",
                           bg=accent[0], font_size=22)

    title_font = _font("black", 64)
    draw = ImageDraw.Draw(img)
    title_lines = _wrap_text(title, title_font, CANVAS_W - 160, draw)
    y = 150
    for line in title_lines[:2]:
        _draw_gradient_text(img, (80, y), line, title_font, accent[0], accent[1])
        y += 76

    bf = _font("regular", 26)
    excerpt = _first_sentences(body, 2) or body[:160]
    body_lines = _wrap_text(excerpt, bf, CANVAS_W - 160, ImageDraw.Draw(img))
    body_y = y + 14
    for line in body_lines[:2]:
        ImageDraw.Draw(img).text((80, body_y), line, font=bf, fill=TEXT_MUTED)
        body_y += 36

    panel_top = max(body_y + 20, 360)
    panel_bottom = 970
    panel_x0 = 80
    panel_x1 = CANVAS_W - 80
    panel_w = panel_x1 - panel_x0
    panel_h = panel_bottom - panel_top

    img = _draw_card(img, (panel_x0, panel_top, panel_x1, panel_bottom),
                     fill=(255, 255, 255, 240), border=accent[0] + (200,),
                     radius=24, border_w=3)

    if not OMIT_FOCAL_ICONS:
        diagram_img = bible_diagrams.get_diagram_image(diagram)
        if diagram_img is not None:
            max_w = panel_w - 60
            max_h = panel_h - 60
            dw, dh = diagram_img.size
            scale = min(max_w / dw, max_h / dh)
            new_w = max(1, int(dw * scale))
            new_h = max(1, int(dh * scale))
            scaled = diagram_img.resize((new_w, new_h), Image.LANCZOS)
            if scaled.mode != "RGBA":
                scaled = scaled.convert("RGBA")
            cx = panel_x0 + (panel_x1 - panel_x0) // 2
            cy = panel_top + (panel_bottom - panel_top) // 2
            paste_x = cx - new_w // 2
            paste_y = cy - new_h // 2
            canvas_rgba = img.convert("RGBA")
            canvas_rgba.paste(scaled, (paste_x, paste_y), scaled)
            img = canvas_rgba.convert("RGB")

    caption_text = (diagram.get("caption_below") or diagram.get("topic") or "").strip()
    if caption_text:
        cf = _font("bold", 22)
        d = ImageDraw.Draw(img)
        cap = caption_text
        if len(cap) > 100:
            cap = cap[:97] + "..."
        d.text((CANVAS_W // 2, panel_bottom + 18), cap,
               font=cf, fill=accent[1], anchor="mt")

    return _footer(img, video_title, slide_num, total)


# ---------------- Layout: DEFAULT (rich text + visual) ----------------

def render_default(title: str, body: str, slide_num: int, total: int, video_title: str) -> Image.Image:
    img = _base_canvas(seed=hash(title) & 0xFFFF)
    accent = ACCENT_PALETTES[slide_num % len(ACCENT_PALETTES)]

    img, _, _ = _draw_pill(img, (80, 80), f"PART {slide_num:02d} OF {total:02d}", bg=accent[0], font_size=24)

    title_font = _font("black", 78)
    draw = ImageDraw.Draw(img)
    title_lines = _wrap_text(title, title_font, CANVAS_W - 800, draw)
    y = 220
    for line in title_lines[:3]:
        _draw_gradient_text(img, (80, y), line, title_font, accent[0], accent[1])
        y += 92

    bar_y = y + 20
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    od.rectangle([80, bar_y, 200, bar_y + 6], fill=accent[1] + (255,))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")

    if not OMIT_BODY_TEXT:
        sentences = _extract_sentences(body, 3)
        bf = _font("regular", 30)
        draw = ImageDraw.Draw(img)
        body_y = bar_y + 40
        for sent in sentences:
            wrapped = _wrap_text(sent, bf, CANVAS_W - 800, draw)
            for line in wrapped[:3]:
                draw.text((80, body_y), line, font=bf, fill=WHITE)
                body_y += 42
            body_y += 16
            if body_y > CANVAS_H - 200:
                break

    visual_size = 440
    visual_cx = CANVAS_W - 380
    visual_cy = 470

    if not OMIT_FOCAL_ICONS:
        img = _draw_disc(img, (visual_cx, visual_cy), visual_size // 2 + 40,
                         fill=accent[0] + (45,), outline=accent[1] + (180,), outline_w=3)

        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        od = ImageDraw.Draw(overlay)
        od.ellipse(
            [visual_cx - visual_size // 2 - 10, visual_cy - visual_size // 2 - 10,
             visual_cx + visual_size // 2 + 10, visual_cy + visual_size // 2 + 10],
            outline=accent[1] + (110,), width=2,
        )
        for i in range(8):
            angle = i * math.pi / 4
            dx = int(math.cos(angle) * (visual_size // 2 + 35))
            dy = int(math.sin(angle) * (visual_size // 2 + 35))
            od.ellipse([visual_cx + dx - 6, visual_cy + dy - 6,
                        visual_cx + dx + 6, visual_cy + dy + 6], fill=accent[1] + (200,))
        img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")

    brand_icon, matched_concept = _icon_or_letter(title, body)
    if brand_icon is not None and not OMIT_FOCAL_ICONS:
        img = _paste_icon(img, brand_icon, (visual_cx, visual_cy), visual_size,
                          glow_color=accent[0], glow_alpha=140)
    elif not OMIT_FOCAL_ICONS:
        big_font = _font("black", 240)
        draw = ImageDraw.Draw(img)
        draw.text((visual_cx, visual_cy - 10), f"{slide_num:02d}", font=big_font, fill=WHITE, anchor="mm")
        label_font = _font("bold", 28)
        draw.text((visual_cx, visual_cy + 110), f"OF {total:02d}", font=label_font, fill=accent[1], anchor="mm")

    label_font = _font("bold", 22)
    draw = ImageDraw.Draw(img)
    if not OMIT_FOCAL_ICONS:
        if matched_concept:
            tag = matched_concept.replace("_", " ").upper()
        else:
            tag = _extract_keyword(title).upper()[:24]
        draw.text((visual_cx, visual_cy + visual_size // 2 + 60),
                  tag, font=label_font, fill=TEXT_MUTED, anchor="mt")

    return _footer(img, video_title, slide_num, total)


# ---------------- Layout: OUTRO ----------------

def render_outro(video_title: str) -> Image.Image:
    img = _base_canvas(seed=hash("outro" + video_title) & 0xFFFF)
    img = _logo_n(img, (CANVAS_W // 2 - 50, 200), size=100)

    title_font = _font("black", 96)
    _draw_gradient_text(img, (CANVAS_W // 2, 360), "Thanks for Watching!", title_font, TEAL, PURPLE_LIGHT, anchor="mt")

    sub = _font("regular", 38)
    draw = ImageDraw.Draw(img)
    draw.text((CANVAS_W // 2, 510), f"You just learned: {video_title}", font=sub, fill=WHITE, anchor="mt")
    draw.text((CANVAS_W // 2, 580), "Continue your learning journey with the next nugget.", font=sub, fill=TEXT_MUTED, anchor="mt")

    pill_text = "Explore More Videos"
    pf = _font("bold", 32)
    pbbox = draw.textbbox((0, 0), pill_text, font=pf)
    pw = pbbox[2] - pbbox[0] + 80
    img, _, _ = _draw_pill(img, (CANVAS_W // 2 - pw // 2, 720), pill_text, bg=PURPLE_LIGHT, font_size=32, padding=(40, 16))

    cf = _font("regular", 22)
    draw = ImageDraw.Draw(img)
    draw.text((CANVAS_W // 2, CANVAS_H - 80), "Video Nuggets OS", font=cf, fill=TEXT_DIM, anchor="mm")
    return img


# ---------------- Layout detection ----------------

# Score threshold above which we elevate a section to the bible_diagram layout.
# Tokens overlap with topic_path are weighted x5; a strong match is rare so 8 is a
# good signal. Override per-section by setting `section.preferred_layout = "..."`.
BIBLE_DIAGRAM_MIN_SCORE = 8.0


def _pick_bible_diagram(section: ContentSection, used_ids: Optional[set] = None) -> Optional[dict]:
    """Return the best Bible-PDF diagram for this section, or None if no match."""
    used_ids = used_ids or set()
    pinned = getattr(section, "diagram_id", None)
    if pinned:
        for d in bible_diagrams.all_diagrams():
            if d.get("id") == pinned:
                return d
    query = f"{section.title} {section.title} {section.body}"
    candidates = bible_diagrams.find_diagrams_for(query, top_k=5, exclude_ids=used_ids)
    if not candidates:
        return None
    # Re-score and apply minimum threshold.
    best = candidates[0]
    qtokens = bible_diagrams._tokenize(query)
    if not qtokens:
        return None
    counts = {t: qtokens.count(t) for t in set(qtokens)}
    score = 0.0
    topic_tokens = set(bible_diagrams._tokenize(" ".join(best.get("topic_path", []) + [best.get("topic", "")])))
    for t in counts:
        if t in topic_tokens:
            score += 5.0 * counts[t]
    heading_tokens = set(bible_diagrams._tokenize(best.get("heading_above", "")))
    for t in counts:
        if t in heading_tokens:
            score += 3.0 * counts[t]
    body_tokens = set(best.get("tokens", []))
    for t in counts:
        if t in body_tokens:
            score += 1.0 * counts[t]
    if score < BIBLE_DIAGRAM_MIN_SCORE:
        return None
    return best


def _detect_layout(section: ContentSection, index: int, total: int,
                   diagram: Optional[dict] = None) -> str:
    if getattr(section, "preferred_layout", None):
        return section.preferred_layout
    if diagram is not None:
        return "bible_diagram"

    title = section.title.lower()
    body = section.body.lower()
    combined = f"{title} {body}"

    if any(kw in body[:120] for kw in ["imagine", "think of it", "picture a", "imagine a", "picture this", "remember when"]):
        return "analogy"
    if any(kw in title for kw in ["rules", "principles", "steps", "pillars", "the three", "the four", "the five"]):
        return "numbered"
    if re.search(r"\bfirst[, ]+.*\bsecond[, ]", body) or re.search(r"\b1\.\s.*\b2\.\s", body):
        return "numbered"
    if any(kw in combined for kw in ["vs ", "versus", "old way", "traditional vs", "compared to", "before nutanix"]):
        return "comparison"
    if any(kw in combined for kw in ["architecture", "stack of layers", "platform overview", "tech stack"]):
        return "architecture"
    if any(kw in title for kw in ["why ", "key ", "benefits", "takeaways", "what makes"]):
        return "key_points"
    return "default"


# ---------------- Helper extractors ----------------

def _extract_sentences(text: str, n: int) -> list[str]:
    text = re.sub(r"\s+", " ", text.strip())
    sents = re.split(r"(?<=[.!?])\s+", text)
    return [s.strip() for s in sents if s.strip()][:n]


def _first_sentences(text: str, n: int) -> str:
    return " ".join(_extract_sentences(text, n))


def _extract_numbered_points(text: str) -> list[str]:
    """Find numbered/bulleted points in text."""
    points = []
    for match in re.finditer(r"(?:first|second|third|fourth|fifth)[, ]+([^.!?]+[.!?])", text, re.I):
        s = match.group(1).strip()
        if s:
            points.append(s[0].upper() + s[1:])
    if len(points) < 3:
        for match in re.finditer(r"\b\d+[.)]\s*([^.!?]+[.!?])", text):
            s = match.group(1).strip()
            if s:
                points.append(s[0].upper() + s[1:])
    return points


def _split_comparison_points(text: str) -> tuple[list[str], list[str]]:
    sents = _extract_sentences(text, 12)
    left = []
    right = []
    nutanix_kws = ["nutanix", "hci", "modern", "today's", "the new way", "new approach"]
    old_kws = ["traditional", "old way", "legacy", "before", "yesterday", "old setup"]
    for s in sents:
        sl = s.lower()
        if any(kw in sl for kw in nutanix_kws):
            right.append(s)
        elif any(kw in sl for kw in old_kws):
            left.append(s)
        else:
            (left if len(left) <= len(right) else right).append(s)
    if not left:
        left = ["Many separate parts to manage", "Slow to set up and scale", "Different teams for each layer", "Higher costs and complexity"]
    if not right:
        right = ["One simple platform", "Quick to deploy and grow", "Unified management", "Lower cost and complexity"]
    return left, right


def _extract_keyword(title: str) -> str:
    words = re.findall(r"[A-Za-z]+", title)
    stopwords = {"the", "a", "an", "of", "and", "or", "to", "is", "for", "in", "on", "with", "what", "how", "why", "where"}
    interesting = [w for w in words if w.lower() not in stopwords]
    return interesting[0] if interesting else (words[0] if words else "N")


# ---------------- Public entry ----------------

def render_slide_images(content: ParsedContent, video_id: int, output_dir: Path) -> list[str]:
    """Generate one PNG per audio segment (intro + sections + outro)."""
    paths, _, _ = render_slide_images_with_layouts(content, video_id, output_dir)
    return paths


def render_slide_images_with_layouts(
    content: ParsedContent, video_id: int, output_dir: Path
) -> tuple[list[str], list[str], list[Optional[dict]]]:
    """Like `render_slide_images` but also returns the layout name + matched
    Bible diagram (if any) per slide.

    Returned lists are aligned: index 0 is "hero" (intro), 1..N are section
    layouts, last is "outro". The diagram list contains the manifest dict for
    sections rendered with the bible_diagram layout, and None elsewhere.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    images: list[str] = []
    layouts: list[str] = []
    diagrams: list[Optional[dict]] = []

    intro_img = render_hero(content.title)
    intro_path = output_dir / f"slide_{video_id}_000_intro.png"
    intro_img.save(intro_path, "PNG")
    images.append(str(intro_path))
    layouts.append("hero")
    diagrams.append(None)

    total_sections = len(content.sections)
    used_diagram_ids: set[str] = set()
    section_diagrams: list[Optional[dict]] = []
    for i, section in enumerate(content.sections):
        diagram = _pick_bible_diagram(section, used_ids=used_diagram_ids)
        if diagram is not None:
            used_diagram_ids.add(diagram["id"])
        section_diagrams.append(diagram)

    for i, section in enumerate(content.sections):
        diagram = section_diagrams[i]
        layout = _detect_layout(section, i, total_sections, diagram=diagram)
        slide_num = i + 1
        if layout == "bible_diagram" and diagram is not None:
            img_obj = render_bible_diagram(
                section.title, section.body, slide_num, total_sections,
                content.title, diagram=diagram,
            )
        elif layout == "analogy":
            img_obj = render_analogy(section.title, section.body, slide_num, total_sections, content.title)
        elif layout == "comparison":
            img_obj = render_comparison(section.title, section.body, slide_num, total_sections, content.title)
        elif layout == "numbered":
            img_obj = render_numbered(section.title, section.body, slide_num, total_sections, content.title)
        elif layout == "key_points":
            img_obj = render_key_points(section.title, section.body, slide_num, total_sections, content.title)
        elif layout == "architecture":
            img_obj = render_architecture(section.title, section.body, slide_num, total_sections, content.title)
        else:
            img_obj = render_default(section.title, section.body, slide_num, total_sections, content.title)

        path = output_dir / f"slide_{video_id}_{slide_num:03d}.png"
        img_obj.save(path, "PNG")
        images.append(str(path))
        layouts.append(layout)
        diagrams.append(diagram if layout == "bible_diagram" else None)

    outro_img = render_outro(content.title)
    outro_path = output_dir / f"slide_{video_id}_999_outro.png"
    outro_img.save(outro_path, "PNG")
    images.append(str(outro_path))
    layouts.append("outro")
    diagrams.append(None)

    return images, layouts, diagrams
