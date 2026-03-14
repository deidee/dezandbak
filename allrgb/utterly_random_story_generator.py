
#!/usr/bin/env python3
"""
Generate a wordless comic strip inspired by the minimalist, absurd side of
Utterly Random.

Requires:
    pip install pillow

Examples:
    python utterly_random_story_generator.py --out strip.png --seed 42
    python utterly_random_story_generator.py --theme museum --date 2026-03-14
    python utterly_random_story_generator.py --theme portal --seed 7 --width 1500 --height 320
"""

from __future__ import annotations

import argparse
import math
import random
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

from PIL import Image, ImageColor, ImageDraw, ImageFilter, ImageFont


Color = Tuple[int, int, int]
Point = Tuple[float, float]


# ---------- small geometry helpers ----------

def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def rgba(rgb: Color, a: int) -> Tuple[int, int, int, int]:
    return (rgb[0], rgb[1], rgb[2], a)


def load_font(size: int, mono: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "DejaVuSansMono.ttf" if mono else "DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf" if mono else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationMono-Regular.ttf" if mono else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
        "/System/Library/Fonts/Supplemental/Courier New.ttf" if mono else "/System/Library/Fonts/Supplemental/Arial.ttf",
        "arial.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size=size)
        except Exception:
            pass
    return ImageFont.load_default()


def regular_polygon(cx: float, cy: float, r: float, sides: int, rot: float = 0.0) -> List[Point]:
    pts: List[Point] = []
    for i in range(sides):
        a = rot + i * (math.tau / sides)
        pts.append((cx + math.cos(a) * r, cy + math.sin(a) * r))
    return pts


def wobble_closed_poly(
    center: Point,
    rx: float,
    ry: float,
    rng: random.Random,
    points: int = 30,
    jitter: float = 4.0,
) -> List[Point]:
    cx, cy = center
    pts: List[Point] = []
    for i in range(points):
        t = i / points
        a = t * math.tau
        local_jitter = rng.uniform(-jitter, jitter)
        x = cx + math.cos(a) * (rx + local_jitter)
        y = cy + math.sin(a) * (ry + rng.uniform(-jitter, jitter))
        pts.append((x, y))
    return pts


def offset_polyline(points: Sequence[Point], dx: float, dy: float) -> List[Point]:
    return [(x + dx, y + dy) for x, y in points]


# ---------- drawing helpers ----------

def draw_wobbly_outline(
    draw: ImageDraw.ImageDraw,
    points: Sequence[Point],
    color: Color = (0, 0, 0),
    width: int = 3,
) -> None:
    if len(points) < 2:
        return
    pts = list(points) + [points[0]]
    draw.line(pts, fill=color, width=width, joint="curve")


def draw_shadow(base: Image.Image, center: Point, rx: float, ry: float, alpha: int = 48) -> None:
    shadow = Image.new("RGBA", base.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(shadow)
    cx, cy = center
    bbox = [cx - rx, cy - ry, cx + rx, cy + ry]
    d.ellipse(bbox, fill=(0, 0, 0, alpha))
    shadow = shadow.filter(ImageFilter.GaussianBlur(radius=max(2, int(rx * 0.08))))
    base.alpha_composite(shadow)


def draw_blob(
    img: Image.Image,
    box: Tuple[int, int, int, int],
    rng: random.Random,
    expression: str = "neutral",
    look: str = "center",
    stripes: bool = False,
    framed: bool = False,
    cracked: bool = False,
    tint: Color | None = None,
    scale: float = 1.0,
    lean: float = 0.0,
    y_shift: float = 0.0,
) -> Dict[str, Tuple[float, float]]:
    draw = ImageDraw.Draw(img)
    x0, y0, x1, y1 = box
    w = x1 - x0
    h = y1 - y0

    cx = x0 + w * (0.50 + 0.08 * lean)
    cy = y0 + h * (0.58 + y_shift)
    rx = w * 0.18 * scale
    ry = h * 0.26 * scale

    draw_shadow(img, (cx, cy + ry * 0.98), rx * 0.50, ry * 0.14, alpha=36 if tint is None else 30)

    body_fill = tint if tint else (236, 236, 236)
    body = wobble_closed_poly((cx, cy), rx, ry, rng, points=36, jitter=max(2.0, w * 0.007))
    draw.polygon(body, fill=body_fill)
    draw_wobbly_outline(draw, body, color=(20, 20, 20), width=max(2, int(w * 0.01)))

    if stripes:
        stripe_color = (180, 205, 232)
        for offset in (-0.08, 0.03):
            sx = cx + rx * offset
            path = []
            for i in range(10):
                t = i / 9
                y = cy - ry * 0.70 + t * ry * 1.42
                x = sx + math.sin(t * math.tau * 1.4) * rx * 0.05
                path.append((x, y))
            draw.line(path, fill=stripe_color, width=max(4, int(w * 0.018)))
            draw.line(path, fill=(40, 40, 40), width=max(1, int(w * 0.006)))

    eye_y = cy - ry * 0.24
    if look == "left":
        ex = -rx * 0.07
    elif look == "right":
        ex = rx * 0.07
    else:
        ex = 0.0

    left_eye = (cx - rx * 0.17 + ex, eye_y)
    right_eye = (cx - rx * 0.01 + ex, eye_y + ry * 0.02)

    eye_len = max(4, int(w * 0.018))

    def eye_vertical(pt: Point) -> None:
        x, y = pt
        draw.line([(x, y - eye_len / 2), (x, y + eye_len / 2)], fill=(25, 25, 25), width=max(1, int(w * 0.006)))

    def eye_sleep(pt: Point) -> None:
        x, y = pt
        draw.line([(x - eye_len / 2, y), (x + eye_len / 2, y)], fill=(25, 25, 25), width=max(1, int(w * 0.006)))

    eye_vertical(left_eye)
    eye_vertical(right_eye)

    mouth_y = cy + ry * 0.16
    mx0 = cx - rx * 0.12
    mx1 = cx + rx * 0.07

    if expression == "smile":
        draw.arc([mx0, mouth_y - ry * 0.08, mx1, mouth_y + ry * 0.10], start=18, end=162, fill=(25, 25, 25), width=max(1, int(w * 0.006)))
    elif expression == "neutral":
        draw.line([(mx0, mouth_y), (mx1, mouth_y)], fill=(25, 25, 25), width=max(1, int(w * 0.006)))
    elif expression == "skeptical":
        draw.line([(mx0, mouth_y + 3), (mx1, mouth_y - 2)], fill=(25, 25, 25), width=max(1, int(w * 0.006)))
    elif expression == "sleepy":
        eye_sleep(left_eye)
        eye_sleep(right_eye)
        draw.line([(mx0, mouth_y), (mx1, mouth_y)], fill=(25, 25, 25), width=max(1, int(w * 0.006)))
    elif expression == "surprised":
        r = max(3, int(w * 0.012))
        draw.ellipse([cx - r, mouth_y - r, cx + r, mouth_y + r], outline=(25, 25, 25), width=max(1, int(w * 0.006)))
    elif expression == "sad":
        draw.arc([mx0, mouth_y - ry * 0.02, mx1, mouth_y + ry * 0.14], start=200, end=340, fill=(25, 25, 25), width=max(1, int(w * 0.006)))
    elif expression == "none":
        pass

    if cracked:
        crack = []
        base_x = cx + rx * 0.14
        for i in range(7):
            t = i / 6
            y = cy - ry * 0.60 + t * ry * 1.16
            x = base_x + (rx * 0.05 if i % 2 else -rx * 0.03)
            crack.append((x, y))
        draw.line(crack, fill=(35, 35, 35), width=max(1, int(w * 0.007)))

    if framed:
        margin = w * 0.05
        fx0, fy0, fx1, fy1 = x0 + margin, y0 + margin, x1 - margin, y1 - margin
        draw.rectangle([fx0, fy0, fx1, fy1], outline=(40, 90, 110), width=max(5, int(w * 0.024)))
        for i in range(4):
            inset = i + 1
            draw.rectangle([fx0 + inset, fy0 + inset, fx1 - inset, fy1 - inset], outline=(70, 150, 170), width=1)

    return {
        "center": (cx, cy),
        "rxry": (rx, ry),
        "left_eye": left_eye,
        "right_eye": right_eye,
        "mouth": ((mx0 + mx1) / 2, mouth_y),
    }


def draw_frame(draw: ImageDraw.ImageDraw, box: Tuple[int, int, int, int], fill: Color) -> None:
    draw.rectangle(box, fill=fill, outline=(40, 40, 40), width=2)


def draw_portal(draw: ImageDraw.ImageDraw, center: Point, radius: float, color: Color) -> None:
    cx, cy = center
    draw.ellipse([cx - radius, cy - radius, cx + radius, cy + radius], fill=color, outline=(30, 30, 30), width=2)
    draw.ellipse([cx - radius * 0.55, cy - radius * 0.55, cx + radius * 0.55, cy + radius * 0.55], fill=(250, 250, 250), outline=(30, 30, 30), width=1)


def draw_arrow(draw: ImageDraw.ImageDraw, start: Point, end: Point, color: Color = (120, 220, 40)) -> None:
    x0, y0 = start
    x1, y1 = end
    draw.line([start, end], fill=color, width=8)
    angle = math.atan2(y1 - y0, x1 - x0)
    head = 18
    a1 = angle + math.radians(150)
    a2 = angle - math.radians(150)
    p1 = (x1 + math.cos(a1) * head, y1 + math.sin(a1) * head)
    p2 = (x1 + math.cos(a2) * head, y1 + math.sin(a2) * head)
    draw.polygon([end, p1, p2], fill=color)


# ---------- story templates ----------

@dataclass
class StoryBeat:
    expression: str = "neutral"
    look: str = "center"
    stripes: bool = False
    framed: bool = False
    cracked: bool = False
    tint: Color | None = None
    scale: float = 1.0
    lean: float = 0.0
    y_shift: float = 0.0
    dot: Point | None = None
    frame_fill: Color | None = None
    extra: str = ""


def museum_story() -> List[StoryBeat]:
    return [
        StoryBeat(expression="smile"),
        StoryBeat(expression="neutral"),
        StoryBeat(expression="sleepy"),
        StoryBeat(expression="none", stripes=True, tint=(236, 236, 236)),
        StoryBeat(expression="none", framed=True, tint=(150, 195, 220), scale=0.90),
    ]


def portal_story() -> List[StoryBeat]:
    return [
        StoryBeat(expression="neutral", look="right", dot=(0.72, 0.72)),
        StoryBeat(expression="surprised", look="right", dot=(0.72, 0.72)),
        StoryBeat(expression="neutral", look="right", dot=(0.52, 0.62), lean=0.10),
        StoryBeat(expression="surprised", look="left", dot=(0.34, 0.55), scale=0.82),
        StoryBeat(expression="none", dot=(0.23, 0.48), scale=0.0, extra="empty"),
    ]


def split_story() -> List[StoryBeat]:
    return [
        StoryBeat(expression="smile"),
        StoryBeat(expression="skeptical"),
        StoryBeat(expression="surprised", cracked=True),
        StoryBeat(expression="neutral", cracked=True),
        StoryBeat(expression="none", extra="double"),
    ]


def float_story() -> List[StoryBeat]:
    return [
        StoryBeat(expression="neutral", y_shift=0.02),
        StoryBeat(expression="surprised", y_shift=-0.02),
        StoryBeat(expression="smile", y_shift=-0.12, scale=0.94),
        StoryBeat(expression="smile", y_shift=-0.26, scale=0.88),
        StoryBeat(expression="none", extra="empty_sky"),
    ]


STORIES = {
    "museum": museum_story,
    "portal": portal_story,
    "split": split_story,
    "float": float_story,
}


# ---------- strip assembly ----------

@dataclass
class ComicConfig:
    width: int = 1214
    height: int = 256
    gutter_width: int = 82
    margin: int = 4
    panels: int = 5
    theme: str = "museum"
    episode: str = "random"
    date_text: str = field(default_factory=lambda: str(date.today()))
    out: Path = Path("utterly-random-story.png")
    seed: int = 1
    title_text: str = "UTTERLY\nRANDOM"
    bg: Color = (239, 239, 239)


def draw_sidebar(img: Image.Image, cfg: ComicConfig) -> None:
    draw = ImageDraw.Draw(img)
    x0, y0, x1, y1 = 0, 0, cfg.gutter_width - 1, cfg.height - 1
    draw.rectangle([x0, y0, x1, y1], fill=(250, 250, 250), outline=(40, 40, 40), width=2)

    small = load_font(max(9, cfg.height // 28), mono=True)
    vert = load_font(max(10, cfg.height // 18), mono=True)
    date_font = load_font(max(9, cfg.height // 30), mono=True)

    # simple UR-ish block logo
    draw.rectangle([12, 6, 53, 36], outline=(30, 30, 30), width=1)
    for x in (14, 23, 32, 41, 50):
        draw.line([(x, 6), (x, 26)], fill=(30, 30, 30), width=1)
    draw.line([(14, 26), (50, 26)], fill=(30, 30, 30), width=1)

    draw.rectangle([12, 48, 53, 95], outline=(30, 30, 30), width=1)
    for yy in (53, 62, 71, 80):
        draw.line([(12, yy), (53, yy)], fill=(30, 30, 30), width=1)
    for xx in (12, 22, 32, 42, 53):
        draw.line([(xx, 48), (xx, 95)], fill=(30, 30, 30), width=1)

    tx = cfg.gutter_width - 13
    ty = 30
    step = max(10, cfg.height // 18)
    for ch in "UTTERLY RANDOM":
        if ch == " ":
            ty += step
            continue
        draw.text((tx, ty), ch, font=vert, fill=(20, 20, 20), anchor="mm")
        ty += step

    draw.text((cfg.gutter_width // 2, cfg.height - 12), cfg.date_text, font=date_font, fill=(20, 20, 20), anchor="ms")

    epi_color = (0, 130, 255) if cfg.theme != "museum" else (220, 0, 0)
    draw.text((cfg.gutter_width // 2, cfg.height - 62), str(cfg.episode), font=small, fill=epi_color, anchor="mm")
    draw.ellipse([cfg.gutter_width // 2 - 2, cfg.height - 86, cfg.gutter_width // 2 + 2, cfg.height - 82], fill=epi_color)


def panel_boxes(cfg: ComicConfig) -> List[Tuple[int, int, int, int]]:
    panel_area_w = cfg.width - cfg.gutter_width
    gap = cfg.margin
    panel_w = (panel_area_w - gap * (cfg.panels + 1)) // cfg.panels
    boxes = []
    for i in range(cfg.panels):
        x0 = cfg.gutter_width + gap + i * (panel_w + gap)
        y0 = gap
        x1 = x0 + panel_w
        y1 = cfg.height - gap
        boxes.append((x0, y0, x1, y1))
    return boxes


def render_background(draw: ImageDraw.ImageDraw, box: Tuple[int, int, int, int], idx: int, story_name: str) -> None:
    if story_name == "museum" and idx == 4:
        draw.rectangle(box, fill=(104, 166, 188), outline=(40, 40, 40), width=2)
        x0, y0, x1, y1 = box
        for j in range(10):
            t = j / 9
            yy = lerp(y0, y1, t)
            col = int(lerp(180, 90, t))
            draw.line([(x0, yy), (x1, yy)], fill=(col, col + 20, col + 30), width=1)
        return
    draw.rectangle(box, fill=(238, 238, 238), outline=(40, 40, 40), width=2)


def render_strip(cfg: ComicConfig) -> Image.Image:
    rng = random.Random(cfg.seed)
    story = STORIES[cfg.theme]()
    img = Image.new("RGBA", (cfg.width, cfg.height), (255, 255, 255, 255))
    draw = ImageDraw.Draw(img)

    draw_sidebar(img, cfg)

    boxes = panel_boxes(cfg)
    for idx, box in enumerate(boxes):
        render_background(draw, box, idx, cfg.theme)
        beat = story[idx]
        x0, y0, x1, y1 = box
        pw, ph = x1 - x0, y1 - y0

        if beat.extra == "empty":
            # just portal left behind
            portal = (x0 + pw * 0.23, y0 + ph * 0.48)
            draw_portal(draw, portal, pw * 0.05, (90, 170, 255))
            continue
        if beat.extra == "empty_sky":
            for j in range(5):
                yy = y0 + j * ph / 5
                col = int(lerp(240, 225, j / 4))
                draw.line([(x0, yy), (x1, yy)], fill=(col, col, col), width=1)
            continue

        blob_box = (x0 + int(pw * 0.08), y0 + int(ph * 0.03), x1 - int(pw * 0.08), y1 - int(ph * 0.08))

        if beat.extra == "double":
            draw_blob(img, (x0 + int(pw * 0.06), y0 + int(ph * 0.06), x0 + int(pw * 0.62), y1 - int(ph * 0.08)),
                      rng, expression="sad", look="left", scale=0.84)
            draw_blob(img, (x0 + int(pw * 0.38), y0 + int(ph * 0.03), x1 - int(pw * 0.05), y1 - int(ph * 0.10)),
                      rng, expression="neutral", look="right", scale=0.84)
            continue

        features = draw_blob(
            img, blob_box, rng,
            expression=beat.expression,
            look=beat.look,
            stripes=beat.stripes,
            framed=beat.framed,
            cracked=beat.cracked,
            tint=beat.tint,
            scale=beat.scale,
            lean=beat.lean,
            y_shift=beat.y_shift,
        )

        if beat.dot is not None:
            dx = x0 + pw * beat.dot[0]
            dy = y0 + ph * beat.dot[1]
            draw_portal(draw, (dx, dy), pw * 0.045, (90, 170, 255))
            if idx in (1, 2):
                draw_arrow(draw, features["mouth"], (dx - 10, dy - 8))
        if cfg.theme == "museum" and idx == 4:
            # extra "painting" feeling
            shadow = Image.new("RGBA", img.size, (0, 0, 0, 0))
            sd = ImageDraw.Draw(shadow)
            fx0, fy0, fx1, fy1 = x0 + 10, y0 + 10, x1 - 10, y1 - 10
            sd.rectangle([fx0 + 6, fy0 + 8, fx1 + 6, fy1 + 8], fill=(0, 0, 0, 35))
            shadow = shadow.filter(ImageFilter.GaussianBlur(3))
            img.alpha_composite(shadow)

    return img


def build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Generate a wordless comic strip in an Utterly Random-ish minimalist style.")
    p.add_argument("--out", type=Path, default=Path("utterly-random-story.png"), help="Output PNG path.")
    p.add_argument("--theme", choices=sorted(STORIES) + ["random"], default="museum", help="Story template.")
    p.add_argument("--seed", type=int, default=1, help="Random seed.")
    p.add_argument("--width", type=int, default=1214, help="Canvas width.")
    p.add_argument("--height", type=int, default=256, help="Canvas height.")
    p.add_argument("--episode", default="random", help="Episode label shown in the gutter.")
    p.add_argument("--date", dest="date_text", default=str(date.today()), help="Date label, e.g. 2026-03-14.")
    return p


def main() -> int:
    args = build_argparser().parse_args()
    theme = random.choice(sorted(STORIES)) if args.theme == "random" else args.theme

    script_dir = Path(__file__).resolve().parent
    out_path = args.out.expanduser()
    if not out_path.is_absolute():
        out_path = (script_dir / out_path).resolve()

    cfg = ComicConfig(
        width=args.width,
        height=args.height,
        theme=theme,
        episode=args.episode,
        date_text=args.date_text,
        out=out_path,
        seed=args.seed,
    )
    img = render_strip(cfg).convert("RGB")
    cfg.out.parent.mkdir(parents=True, exist_ok=True)
    img.save(cfg.out, "PNG")
    print(f"Wrote {cfg.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
