"""
PIL drawing primitives used by animation cues.

Each function returns a transparent RGBA `Image` overlay that the renderer
composites on top of the scene canvas. They take a `progress` scalar in [0,1]
which the renderer has already eased per the cue config.

Convention:
- All sizes/positions are in canvas pixel coordinates (1920 x 1080).
- Text uses Inter / system fonts via `_font` (mirrors slide_image_generator).
- Functions are pure: they don't mutate any shared state.
- The compositor uses alpha blending so primitives can layer.

Available primitives (callable via `apply(canvas, kind, progress, params)`):
- icon_reveal      - pop an icon in with optional scale + glow
- pulse_ring       - pulsing concentric ring around a center
- arrow            - animated stroke arrow from A to B with optional curve
- highlight_box    - rounded outline that draws around a region
- text_in          - typewriter-style text reveal with cursor
- fade_in          - fade an icon/image in over a region
- slide_in         - icon translates from offscreen
- count_up         - integer counts from 0 to a target value
- caption          - subtitle-style word highlight near the bottom
- chip             - rounded label chip that pops in
- spotlight        - dark overlay with a circular cutout that moves
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFilter, ImageFont

CANVAS_W, CANVAS_H = 1920, 1080

PURPLE = (110, 70, 235)
PURPLE_LIGHT = (140, 100, 255)
TEAL = (78, 220, 215)
GREEN = (90, 224, 162)
CORAL = (255, 116, 99)
YELLOW = (255, 210, 92)
PINK = (235, 100, 200)
WHITE = (255, 255, 255)
TEXT_MUTED = (180, 190, 220)


# ---------------- Font helper (mirrors slide_image_generator) ----------------

_FONT_CACHE: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}

_SYSTEM_FONT_CANDIDATES = {
    "regular": ["/System/Library/Fonts/Supplemental/Arial.ttf", "/System/Library/Fonts/Helvetica.ttc"],
    "bold": ["/System/Library/Fonts/Supplemental/Arial Bold.ttf", "/System/Library/Fonts/Helvetica.ttc"],
    "black": ["/System/Library/Fonts/Supplemental/Arial Black.ttf", "/System/Library/Fonts/Helvetica.ttc"],
}


def _font(weight: str, size: int) -> ImageFont.FreeTypeFont:
    key = (weight, size)
    if key in _FONT_CACHE:
        return _FONT_CACHE[key]
    for path in _SYSTEM_FONT_CANDIDATES.get(weight, []):
        if Path(path).exists():
            try:
                f = ImageFont.truetype(path, size=size)
                _FONT_CACHE[key] = f
                return f
            except Exception:
                continue
    _FONT_CACHE[key] = ImageFont.load_default()
    return _FONT_CACHE[key]


# ---------------- Color helpers ----------------

def _color(c) -> tuple[int, int, int, int]:
    """Coerce hex / 3-tuple / 4-tuple to (r,g,b,a)."""
    if isinstance(c, str):
        s = c.lstrip("#")
        if len(s) == 6:
            return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16), 255)
        if len(s) == 8:
            return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16), int(s[6:8], 16))
    if isinstance(c, (list, tuple)):
        if len(c) == 3:
            return (int(c[0]), int(c[1]), int(c[2]), 255)
        if len(c) == 4:
            return (int(c[0]), int(c[1]), int(c[2]), int(c[3]))
    return (255, 255, 255, 255)


def _blank_overlay() -> Image.Image:
    return Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 0))


# ---------------- Icon cache ----------------

_ICON_CACHE: dict[tuple[str, int], Image.Image] = {}


def _load_icon(path: str, size: int) -> Optional[Image.Image]:
    key = (path, size)
    if key in _ICON_CACHE:
        return _ICON_CACHE[key]
    p = Path(path)
    if not p.exists():
        return None
    try:
        img = Image.open(p).convert("RGBA")
    except Exception:
        return None
    if img.size != (size, size):
        img = img.resize((size, size), Image.LANCZOS)
    _ICON_CACHE[key] = img
    return img


# ---------------- Glow / disc helpers ----------------

def _glow(size: int, color, alpha: int = 140, blur: int = 30) -> Image.Image:
    """Soft circular glow."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    margin = blur
    rgb = _color(color)[:3]
    d.ellipse([margin, margin, size - margin, size - margin], fill=rgb + (alpha,))
    return img.filter(ImageFilter.GaussianBlur(blur))


def _disc(center, radius, fill, outline=None, outline_w=0) -> Image.Image:
    overlay = _blank_overlay()
    d = ImageDraw.Draw(overlay)
    cx, cy = center
    bbox = [cx - radius, cy - radius, cx + radius, cy + radius]
    fill_rgba = _color(fill)
    if outline is None:
        d.ellipse(bbox, fill=fill_rgba)
    else:
        d.ellipse(bbox, fill=fill_rgba, outline=_color(outline), width=outline_w)
    return overlay


# ---------------- Primitives ----------------

def icon_reveal(progress: float, params: dict) -> Image.Image:
    """Pop an icon in with scale-up + fade-in + optional glow halo.

    params:
      icon: path to PNG (preferred) OR pil_image (already-loaded RGBA Image)
      center: (x, y)
      size: target px (default 256)
      glow: color or None
      glow_alpha: 0..255
      tag: optional label drawn under the icon (string)
      tag_color: tag text color
    """
    overlay = _blank_overlay()
    icon_path = params.get("icon")
    pil_image = params.get("pil_image")
    cx, cy = params["center"]
    size = int(params.get("size", 256))
    glow_color = params.get("glow")
    glow_alpha = int(params.get("glow_alpha", 150))

    scale = 0.6 + 0.4 * progress
    alpha_mul = progress
    drawn_size = max(8, int(size * scale))

    if glow_color is not None and progress > 0.05:
        glow_size = drawn_size + drawn_size // 3
        g = _glow(glow_size, glow_color, alpha=int(glow_alpha * progress))
        overlay.paste(g, (cx - glow_size // 2, cy - glow_size // 2), g)

    icon_img: Optional[Image.Image] = pil_image
    if icon_img is None and icon_path:
        icon_img = _load_icon(icon_path, size)
    if icon_img is not None:
        if icon_img.size != (drawn_size, drawn_size):
            icon_img = icon_img.resize((drawn_size, drawn_size), Image.LANCZOS)
        if alpha_mul < 1.0:
            faded = icon_img.copy()
            alpha = faded.split()[3].point(lambda v: int(v * alpha_mul))
            faded.putalpha(alpha)
            icon_img = faded
        overlay.paste(icon_img, (cx - drawn_size // 2, cy - drawn_size // 2), icon_img)

    tag = params.get("tag")
    if tag and progress > 0.6:
        d = ImageDraw.Draw(overlay)
        f = _font("bold", int(params.get("tag_size", 22)))
        tag_progress = (progress - 0.6) / 0.4
        tag_color = _color(params.get("tag_color", TEXT_MUTED))
        tag_color = tag_color[:3] + (int(255 * tag_progress),)
        d.text(
            (cx, cy + size // 2 + 30),
            tag.upper(),
            font=f,
            fill=tag_color,
            anchor="mm",
        )

    return overlay


def fade_in(progress: float, params: dict) -> Image.Image:
    """Same as icon_reveal but no scale-up - just an alpha fade."""
    new_params = dict(params)
    return _icon_basic(progress, new_params, scale_curve=lambda p: 1.0)


def _icon_basic(progress: float, params: dict, scale_curve=lambda p: 1.0) -> Image.Image:
    overlay = _blank_overlay()
    cx, cy = params["center"]
    size = int(params.get("size", 256))
    icon_path = params.get("icon")
    pil_image = params.get("pil_image")
    scale = scale_curve(progress)
    drawn_size = max(8, int(size * scale))
    icon_img = pil_image or (_load_icon(icon_path, size) if icon_path else None)
    if icon_img is None:
        return overlay
    if icon_img.size != (drawn_size, drawn_size):
        icon_img = icon_img.resize((drawn_size, drawn_size), Image.LANCZOS)
    if progress < 1.0:
        faded = icon_img.copy()
        alpha = faded.split()[3].point(lambda v: int(v * progress))
        faded.putalpha(alpha)
        icon_img = faded
    overlay.paste(icon_img, (cx - drawn_size // 2, cy - drawn_size // 2), icon_img)
    return overlay


def slide_in(progress: float, params: dict) -> Image.Image:
    """Icon translates from `from_offset` to its target `center` while fading in."""
    overlay = _blank_overlay()
    target_cx, target_cy = params["center"]
    fx, fy = params.get("from_offset", (-200, 0))
    cx = int(target_cx + fx * (1.0 - progress))
    cy = int(target_cy + fy * (1.0 - progress))
    size = int(params.get("size", 256))
    icon_path = params.get("icon")
    pil_image = params.get("pil_image")
    icon_img = pil_image or (_load_icon(icon_path, size) if icon_path else None)
    if icon_img is None:
        return overlay
    if progress < 1.0:
        faded = icon_img.copy()
        alpha = faded.split()[3].point(lambda v: int(v * progress))
        faded.putalpha(alpha)
        icon_img = faded
    overlay.paste(icon_img, (cx - size // 2, cy - size // 2), icon_img)
    return overlay


def pulse_ring(progress: float, params: dict) -> Image.Image:
    """Expanding ring that fades out as it grows. Use ease='pulse' for repeating effect."""
    overlay = _blank_overlay()
    cx, cy = params["center"]
    base_radius = int(params.get("base_radius", 100))
    max_radius = int(params.get("max_radius", 200))
    color = _color(params.get("color", PURPLE_LIGHT))
    width = int(params.get("width", 4))
    cycles = int(params.get("cycles", 1))

    p = (progress * cycles) % 1.0 if cycles > 1 else progress
    r = int(base_radius + (max_radius - base_radius) * p)
    alpha = max(0, int(255 * (1.0 - p)))
    d = ImageDraw.Draw(overlay)
    d.ellipse(
        [cx - r, cy - r, cx + r, cy + r],
        outline=color[:3] + (alpha,),
        width=width,
    )
    return overlay


def arrow(progress: float, params: dict) -> Image.Image:
    """Animated arrow that grows from `start` toward `end`, drawing an arrowhead at the tip."""
    overlay = _blank_overlay()
    sx, sy = params["start"]
    ex, ey = params["end"]
    color = _color(params.get("color", YELLOW))
    width = int(params.get("width", 8))
    head_size = int(params.get("head_size", 24))
    curve = float(params.get("curve", 0.0))  # 0 = straight, 0.3 = gentle bow

    cur_x = sx + (ex - sx) * progress
    cur_y = sy + (ey - sy) * progress

    d = ImageDraw.Draw(overlay)
    if abs(curve) < 0.001:
        d.line([(sx, sy), (cur_x, cur_y)], fill=color, width=width)
    else:
        mx = (sx + ex) / 2
        my = (sy + ey) / 2
        dx = ex - sx
        dy = ey - sy
        length = max(1.0, math.hypot(dx, dy))
        nx = -dy / length
        ny = dx / length
        bow_x = mx + nx * length * curve
        bow_y = my + ny * length * curve
        steps = 30
        last = (sx, sy)
        for i in range(1, int(steps * progress) + 1):
            t = i / steps
            x = (1 - t) ** 2 * sx + 2 * (1 - t) * t * bow_x + t * t * ex
            y = (1 - t) ** 2 * sy + 2 * (1 - t) * t * bow_y + t * t * ey
            d.line([last, (x, y)], fill=color, width=width)
            last = (x, y)
        cur_x, cur_y = last

    if progress > 0.85:
        ang = math.atan2(cur_y - sy, cur_x - sx)
        for i, side in enumerate([1, -1]):
            ax = cur_x - head_size * math.cos(ang - side * 0.5)
            ay = cur_y - head_size * math.sin(ang - side * 0.5)
            d.line([(cur_x, cur_y), (ax, ay)], fill=color, width=width)

    return overlay


def highlight_box(progress: float, params: dict) -> Image.Image:
    """Rounded outline that draws clockwise around a region.

    params:
      box: (x0, y0, x1, y1)
      color, width, radius
    """
    overlay = _blank_overlay()
    x0, y0, x1, y1 = params["box"]
    color = _color(params.get("color", YELLOW))
    width = int(params.get("width", 6))
    radius = int(params.get("radius", 18))

    perimeter = 2 * ((x1 - x0) + (y1 - y0))
    drawn = perimeter * progress

    d = ImageDraw.Draw(overlay)
    if progress >= 0.99:
        d.rounded_rectangle([x0, y0, x1, y1], outline=color, width=width, radius=radius)
        return overlay

    # Manual progressive outline by drawing four sides up to drawn length.
    side1 = x1 - x0
    side2 = y1 - y0
    side3 = x1 - x0
    side4 = y1 - y0
    sides = [side1, side2, side3, side4]
    starts = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    ends = [(x1, y0), (x1, y1), (x0, y1), (x0, y0)]
    remaining = drawn
    for i in range(4):
        if remaining <= 0:
            break
        seg = min(remaining, sides[i])
        sx, sy = starts[i]
        ex, ey = ends[i]
        if sides[i] > 0:
            t = seg / sides[i]
        else:
            t = 0
        cx = sx + (ex - sx) * t
        cy = sy + (ey - sy) * t
        d.line([(sx, sy), (cx, cy)], fill=color, width=width)
        remaining -= seg

    return overlay


def text_in(progress: float, params: dict) -> Image.Image:
    """Typewriter-style text reveal.

    params:
      text: full string
      anchor_xy: top-left anchor point
      font_weight: regular / bold / black
      font_size: int
      color: rgb/rgba
      cursor: bool (default True) - blinking caret while progress < 1
      max_width: optional wrap width
    """
    overlay = _blank_overlay()
    text = params["text"]
    x, y = params["anchor_xy"]
    font_size = int(params.get("font_size", 36))
    weight = params.get("font_weight", "bold")
    color = _color(params.get("color", WHITE))
    n = max(1, int(len(text) * progress))
    visible = text[:n]
    f = _font(weight, font_size)
    d = ImageDraw.Draw(overlay)
    d.text((x, y), visible, font=f, fill=color)

    if params.get("cursor", True) and progress < 1.0:
        bbox = d.textbbox((x, y), visible, font=f)
        cx = bbox[2] + 4
        cy0 = bbox[1]
        cy1 = bbox[3]
        d.rectangle([cx, cy0, cx + 6, cy1], fill=color)

    return overlay


def caption(progress: float, params: dict) -> Image.Image:
    """Bottom-center subtitle strip used for narration captions / call-outs.

    params:
      text: string
      y: top y of the caption block (default 920)
      bg: background rgb/rgba (default dark translucent)
      fg: text color
      max_width: wrap width
    """
    overlay = _blank_overlay()
    text = params["text"]
    y = int(params.get("y", 920))
    bg = _color(params.get("bg", (10, 14, 38, 200)))
    fg = _color(params.get("fg", WHITE))
    font_size = int(params.get("font_size", 36))
    f = _font("bold", font_size)
    d = ImageDraw.Draw(overlay)
    bbox = d.textbbox((0, 0), text, font=f)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    pad_x, pad_y = 32, 18
    box_w = tw + pad_x * 2
    box_h = th + pad_y * 2
    box_x = (CANVAS_W - box_w) // 2
    box_y = y
    alpha = int(255 * progress)
    bg_with_alpha = bg[:3] + (min(alpha, bg[3]),)
    d.rounded_rectangle([box_x, box_y, box_x + box_w, box_y + box_h],
                        fill=bg_with_alpha, radius=18)
    fg_alpha = fg[:3] + (alpha,)
    d.text((box_x + pad_x - bbox[0], box_y + pad_y - bbox[1]), text, font=f, fill=fg_alpha)
    return overlay


def chip(progress: float, params: dict) -> Image.Image:
    """Rounded label chip that pops in.

    params:
      text, anchor_xy, bg, fg, font_size, padding
    """
    overlay = _blank_overlay()
    text = params["text"]
    x, y = params["anchor_xy"]
    bg = _color(params.get("bg", PURPLE_LIGHT))
    fg = _color(params.get("fg", WHITE))
    fs = int(params.get("font_size", 24))
    px, py = params.get("padding", (24, 10))
    f = _font("bold", fs)
    d = ImageDraw.Draw(overlay)
    bbox = d.textbbox((0, 0), text, font=f)
    w = bbox[2] - bbox[0] + px * 2
    h = bbox[3] - bbox[1] + py * 2
    scale = 0.7 + 0.3 * progress
    drawn_w = int(w * scale)
    drawn_h = int(h * scale)
    cx = x + w // 2
    cy = y + h // 2
    bx0 = cx - drawn_w // 2
    by0 = cy - drawn_h // 2
    alpha = int(255 * progress)
    d.rounded_rectangle([bx0, by0, bx0 + drawn_w, by0 + drawn_h],
                        fill=bg[:3] + (alpha,), radius=drawn_h // 2)
    if progress > 0.6:
        text_alpha = int(255 * (progress - 0.6) / 0.4)
        d.text((cx, cy), text, font=f, fill=fg[:3] + (text_alpha,), anchor="mm")
    return overlay


def count_up(progress: float, params: dict) -> Image.Image:
    """Animated number counting from `from_value` to `to_value`.

    params:
      from_value, to_value, anchor_xy, font_size, color, suffix
    """
    overlay = _blank_overlay()
    fv = float(params.get("from_value", 0))
    tv = float(params.get("to_value", 100))
    x, y = params["anchor_xy"]
    fs = int(params.get("font_size", 96))
    color = _color(params.get("color", TEAL))
    suffix = params.get("suffix", "")
    cur = fv + (tv - fv) * progress
    txt = f"{int(cur)}{suffix}"
    f = _font("black", fs)
    d = ImageDraw.Draw(overlay)
    d.text((x, y), txt, font=f, fill=color, anchor="mm")
    return overlay


def diagram_reveal(progress: float, params: dict) -> Image.Image:
    """Reveal a non-square image (e.g. a Cloud Bible figure) with scale-up + fade-in,
    preserving its aspect ratio.

    params:
      pil_image: RGBA PIL.Image already sized to its target render dimensions.
      center: (x, y) - center point in canvas coordinates.
      glow: optional accent color for a soft halo.
      glow_alpha: 0..255.
      scale_start: starting scale (default 0.8).
    """
    overlay = _blank_overlay()
    img: Optional[Image.Image] = params.get("pil_image")
    if img is None:
        return overlay
    cx, cy = params["center"]
    scale_start = float(params.get("scale_start", 0.85))
    scale = scale_start + (1.0 - scale_start) * progress

    full_w, full_h = img.size
    drawn_w = max(8, int(full_w * scale))
    drawn_h = max(8, int(full_h * scale))

    glow_color = params.get("glow")
    glow_alpha = int(params.get("glow_alpha", 130))
    if glow_color is not None and progress > 0.05:
        glow_size = int(max(drawn_w, drawn_h) * 1.05)
        g = _glow(glow_size, glow_color, alpha=int(glow_alpha * progress))
        overlay.paste(g, (cx - glow_size // 2, cy - glow_size // 2), g)

    if (drawn_w, drawn_h) != (full_w, full_h):
        scaled = img.resize((drawn_w, drawn_h), Image.LANCZOS)
    else:
        scaled = img.copy() if progress < 1.0 else img

    if progress < 1.0:
        scaled = scaled.copy()
        if scaled.mode != "RGBA":
            scaled = scaled.convert("RGBA")
        alpha = scaled.split()[3].point(lambda v: int(v * progress))
        scaled.putalpha(alpha)

    overlay.paste(scaled, (cx - drawn_w // 2, cy - drawn_h // 2), scaled)
    return overlay


def spotlight(progress: float, params: dict) -> Image.Image:
    """Dim the canvas with a circular cutout that highlights a region.

    params:
      center, radius (target), dim (0..255 alpha of overlay)
    """
    overlay = _blank_overlay()
    cx, cy = params["center"]
    radius = int(params.get("radius", 200) * progress)
    dim = int(params.get("dim", 130) * progress)
    full = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, dim))
    mask = Image.new("L", (CANVAS_W, CANVAS_H), 0)
    md = ImageDraw.Draw(mask)
    md.ellipse([cx - radius, cy - radius, cx + radius, cy + radius], fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(20))
    inv = mask.point(lambda v: 255 - v)
    full.putalpha(inv)
    overlay.alpha_composite(full)
    return overlay


# ---------------- Dispatch ----------------

PRIMITIVES = {
    "icon_reveal": icon_reveal,
    "diagram_reveal": diagram_reveal,
    "fade_in": fade_in,
    "slide_in": slide_in,
    "pulse_ring": pulse_ring,
    "arrow": arrow,
    "highlight_box": highlight_box,
    "text_in": text_in,
    "caption": caption,
    "chip": chip,
    "count_up": count_up,
    "spotlight": spotlight,
}


def render_cue(canvas: Image.Image, kind: str, progress: float, params: dict) -> Image.Image:
    """Composite the named primitive onto `canvas` at the given progress.

    Returns the new canvas (alpha-blended). Unknown kinds are silently ignored.
    """
    fn = PRIMITIVES.get(kind)
    if fn is None:
        return canvas
    overlay = fn(progress, params)
    if overlay is None:
        return canvas
    return Image.alpha_composite(canvas.convert("RGBA"), overlay)
