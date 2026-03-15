#!/usr/bin/env python3
from __future__ import annotations

import argparse
import io
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Sequence, Tuple
from urllib.parse import urlparse

import numpy as np
from PIL import Image

try:
    import requests
except Exception:  # pragma: no cover
    requests = None


@dataclass
class Rect:
    x0: int
    y0: int
    x1: int
    y1: int

    @property
    def width(self) -> int:
        return self.x1 - self.x0 + 1

    @property
    def height(self) -> int:
        return self.y1 - self.y0 + 1

    @property
    def area(self) -> int:
        return self.width * self.height

    @property
    def center(self) -> Tuple[float, float]:
        return ((self.x0 + self.x1) / 2.0, (self.y0 + self.y1) / 2.0)


def is_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def load_image(source: str) -> Image.Image:
    if is_url(source):
        if requests is None:
            raise SystemExit(
                "This script needs the 'requests' package for image URLs. Install it with: pip install requests"
            )
        response = requests.get(source, timeout=30)
        response.raise_for_status()
        return Image.open(io.BytesIO(response.content)).convert("RGB")

    path = Path(source).expanduser().resolve()
    if not path.exists():
        raise SystemExit(f"Image file not found: {path}")
    return Image.open(path).convert("RGB")


def to_dark_mask(image: Image.Image, threshold: int) -> np.ndarray:
    arr = np.asarray(image.convert("L"), dtype=np.uint8)
    return arr <= threshold


def bridge_small_gaps(mask: np.ndarray, max_gap: int) -> np.ndarray:
    """
    Fill tiny 1D gaps in dark border lines so stylized/interrupted borders still
    behave like a single connected rectangle.

    This helps with frames whose border is broken by thin horizontal/vertical
    decorations or anti-aliased line crossings.
    """
    if max_gap <= 0:
        return mask

    out = mask.copy()
    h, w = out.shape

    # Fill short vertical gaps.
    for x in range(w):
        y = 0
        while y < h:
            if out[y, x]:
                y += 1
                continue
            start = y
            while y < h and not out[y, x]:
                y += 1
            end = y
            gap = end - start
            if gap <= max_gap and start > 0 and end < h and out[start - 1, x] and out[end, x]:
                out[start:end, x] = True

    # Fill short horizontal gaps.
    for y in range(h):
        x = 0
        while x < w:
            if out[y, x]:
                x += 1
                continue
            start = x
            while x < w and not out[y, x]:
                x += 1
            end = x
            gap = end - start
            if gap <= max_gap and start > 0 and end < w and out[y, start - 1] and out[y, end]:
                out[y, start:end] = True

    return out


def connected_components(mask: np.ndarray) -> List[Rect]:
    h, w = mask.shape
    visited = np.zeros((h, w), dtype=bool)
    rects: List[Rect] = []

    ys, xs = np.nonzero(mask)
    for sy, sx in zip(ys.tolist(), xs.tolist()):
        if visited[sy, sx]:
            continue

        q = deque([(sy, sx)])
        visited[sy, sx] = True
        min_x = max_x = sx
        min_y = max_y = sy

        while q:
            y, x = q.popleft()
            if x < min_x:
                min_x = x
            if x > max_x:
                max_x = x
            if y < min_y:
                min_y = y
            if y > max_y:
                max_y = y

            ny = y - 1
            if ny >= 0 and mask[ny, x] and not visited[ny, x]:
                visited[ny, x] = True
                q.append((ny, x))
            ny = y + 1
            if ny < h and mask[ny, x] and not visited[ny, x]:
                visited[ny, x] = True
                q.append((ny, x))
            nx = x - 1
            if nx >= 0 and mask[y, nx] and not visited[y, nx]:
                visited[y, nx] = True
                q.append((y, nx))
            nx = x + 1
            if nx < w and mask[y, nx] and not visited[y, nx]:
                visited[y, nx] = True
                q.append((y, nx))

        rects.append(Rect(min_x, min_y, max_x, max_y))

    return rects


def edge_has_line(section: np.ndarray, axis: int, min_coverage: float) -> bool:
    if section.size == 0:
        return False
    coverage = section.mean(axis=axis)
    return bool(np.any(coverage >= min_coverage))


def looks_like_bordered_rectangle(mask: np.ndarray, rect: Rect, border_band: int, min_coverage: float) -> bool:
    x0, y0, x1, y1 = rect.x0, rect.y0, rect.x1, rect.y1
    band = max(1, border_band)

    roi = mask[y0:y1 + 1, x0:x1 + 1]
    if roi.shape[0] < band * 2 or roi.shape[1] < band * 2:
        return False

    top = roi[:band, :]
    bottom = roi[-band:, :]
    left = roi[:, :band]
    right = roi[:, -band:]

    top_ok = edge_has_line(top, axis=1, min_coverage=min_coverage)
    bottom_ok = edge_has_line(bottom, axis=1, min_coverage=min_coverage)
    left_ok = edge_has_line(left, axis=0, min_coverage=min_coverage)
    right_ok = edge_has_line(right, axis=0, min_coverage=min_coverage)
    if not (top_ok and bottom_ok and left_ok and right_ok):
        return False

    if roi.shape[0] > band * 2 and roi.shape[1] > band * 2:
        inner = roi[band:-band, band:-band]
        inner_density = float(inner.mean()) if inner.size else 0.0
        if inner_density > 0.35:
            return False

    return True


def dedupe_nested(rects: Sequence[Rect], tolerance: int = 2) -> List[Rect]:
    kept: List[Rect] = []
    for rect in sorted(rects, key=lambda r: r.area, reverse=True):
        is_nested = False
        for other in kept:
            if (
                rect.x0 >= other.x0 - tolerance
                and rect.y0 >= other.y0 - tolerance
                and rect.x1 <= other.x1 + tolerance
                and rect.y1 <= other.y1 + tolerance
            ):
                is_nested = True
                break
        if not is_nested:
            kept.append(rect)
    return kept


def sort_reading_order(rects: Sequence[Rect]) -> List[Rect]:
    if not rects:
        return []

    rects = list(rects)
    median_h = sorted(r.height for r in rects)[len(rects) // 2]
    row_tol = max(10, int(median_h * 0.35))

    rects_sorted = sorted(rects, key=lambda r: (r.center[1], r.center[0]))
    rows: List[List[Rect]] = []
    row_ys: List[float] = []

    for rect in rects_sorted:
        cy = rect.center[1]
        placed = False
        for i, row_y in enumerate(row_ys):
            if abs(cy - row_y) <= row_tol:
                rows[i].append(rect)
                row_ys[i] = sum(r.center[1] for r in rows[i]) / len(rows[i])
                placed = True
                break
        if not placed:
            rows.append([rect])
            row_ys.append(cy)

    ordered: List[Rect] = []
    for row in [r for _, r in sorted(zip(row_ys, rows), key=lambda t: t[0])]:
        ordered.extend(sorted(row, key=lambda r: r.center[0]))
    return ordered


def detect_frames(
    image: Image.Image,
    threshold: int,
    min_width: int,
    min_height: int,
    border_band: int,
    line_coverage: float,
    bridge_gap: int,
) -> List[Rect]:
    mask = to_dark_mask(image, threshold)
    mask = bridge_small_gaps(mask, max_gap=bridge_gap)

    candidates = []
    for rect in connected_components(mask):
        if rect.width < min_width or rect.height < min_height:
            continue
        if looks_like_bordered_rectangle(mask, rect, border_band=border_band, min_coverage=line_coverage):
            candidates.append(rect)

    candidates = dedupe_nested(candidates)
    return sort_reading_order(candidates)


def scale_to_canvas(frame: Image.Image, canvas_w: int, canvas_h: int, padding_frac: float) -> Image.Image:
    pad_x = int(round(canvas_w * padding_frac))
    pad_y = int(round(canvas_h * padding_frac))
    max_w = max(1, canvas_w - 2 * pad_x)
    max_h = max(1, canvas_h - 2 * pad_y)

    scale = min(max_w / frame.width, max_h / frame.height)
    new_w = max(1, int(round(frame.width * scale)))
    new_h = max(1, int(round(frame.height * scale)))
    resized = frame.resize((new_w, new_h), Image.Resampling.LANCZOS)

    canvas = Image.new("RGB", (canvas_w, canvas_h), "white")
    x = (canvas_w - new_w) // 2
    y = (canvas_h - new_h) // 2
    canvas.paste(resized, (x, y))
    return canvas


def export_frames(
    image: Image.Image,
    frames: Sequence[Rect],
    outdir: Path,
    timestamp: str,
    canvas_w: int,
    canvas_h: int,
    padding_frac: float,
) -> List[Path]:
    outdir.mkdir(parents=True, exist_ok=True)
    written: List[Path] = []

    for idx, rect in enumerate(frames, start=1):
        crop = image.crop((rect.x0, rect.y0, rect.x1 + 1, rect.y1 + 1))
        insta = scale_to_canvas(crop, canvas_w=canvas_w, canvas_h=canvas_h, padding_frac=padding_frac)
        out_path = outdir / f"{timestamp}-{idx:02d}.png"
        insta.save(out_path, "PNG")
        written.append(out_path)

    return written


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Detect black-bordered comic frames and export each one as a 1080x1350 Instagram image."
    )
    p.add_argument("source", help="Image URL or local file path")
    p.add_argument("--outdir", type=Path, default=Path("instagram"), help="Directory to write exported PNGs")
    p.add_argument("--width", type=int, default=1080, help="Output canvas width")
    p.add_argument("--height", type=int, default=1350, help="Output canvas height")
    p.add_argument("--padding-frac", type=float, default=0.06, help="Outer white margin as a fraction of canvas size")
    p.add_argument("--threshold", type=int, default=70, help="Grayscale threshold for detecting black borders")
    p.add_argument("--min-width", type=int, default=100, help="Minimum rectangle width to count as a frame")
    p.add_argument("--min-height", type=int, default=100, help="Minimum rectangle height to count as a frame")
    p.add_argument("--border-band", type=int, default=4, help="How many pixels near each edge to inspect")
    p.add_argument("--line-coverage", type=float, default=0.6, help="Minimum dark-pixel coverage for an edge line")
    p.add_argument(
        "--bridge-gap",
        type=int,
        default=2,
        help="Fill tiny border interruptions up to this many pixels before rectangle detection",
    )
    p.add_argument("--timestamp", default=None, help="Override timestamp prefix (default: current local time)")
    p.add_argument("--verbose", action="store_true", help="Print detected frame coordinates")
    return p


def main() -> int:
    args = build_parser().parse_args()
    image = load_image(args.source)
    frames = detect_frames(
        image,
        threshold=args.threshold,
        min_width=args.min_width,
        min_height=args.min_height,
        border_band=args.border_band,
        line_coverage=args.line_coverage,
        bridge_gap=args.bridge_gap,
    )

    if not frames:
        raise SystemExit(
            "No frames detected. Try increasing --threshold slightly, lowering --min-width/--min-height, or raising --bridge-gap."
        )

    timestamp = args.timestamp or datetime.now().strftime("%Y%m%d-%H%M%S")
    written = export_frames(
        image,
        frames,
        outdir=args.outdir.expanduser(),
        timestamp=timestamp,
        canvas_w=args.width,
        canvas_h=args.height,
        padding_frac=args.padding_frac,
    )

    print(f"Detected {len(frames)} frame(s).")
    if args.verbose:
        for i, rect in enumerate(frames, start=1):
            print(f"  {i:02d}: x={rect.x0}..{rect.x1}, y={rect.y0}..{rect.y1}, w={rect.width}, h={rect.height}")
    for path in written:
        print(path.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
