#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
embed-url-screenshots-into-svg.py

Given a URL, this script:
1) Takes 3 screenshots (desktop/tablet/mobile by default), with default scroll = top/top/top.
2) Embeds those PNGs into the 3 “screen” rectangles of the SVG mockup.
3) Ensures the embedded screenshots are scaled so that WIDTH is never cropped (only height may be clipped).
4) Names outputs using the requested domain.
5) If the page has <meta name="theme-color" content="...">, uses that as the SVG background color.

Install:
  pip install playwright pillow
  playwright install chromium
Optional (prettier SVG output):
  pip install lxml

Usage:
  python embed-url-screenshots-into-svg.py "https://example.com" --out dist

Scroll control (defaults to top top top):
  --scrolls top top top
  --scrolls top mid bottom

Notes:
- The three screens in this mockup have aspect ratios that closely match common:
  Desktop 1366×768 (≈16:9), Tablet 768×1024 (≈3:4 portrait), Mobile 375×667 (≈iPhone 8 portrait).
  This script will only use those “common” sizes if they match the mockup aspect reasonably.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

from PIL import Image

DEFAULT_TEMPLATE_SVG = """\
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 2520 1530">
  <defs>
    <linearGradient id="bevel" x1="693.03" x2="693.59" y1="823.515" y2="917.459" gradientUnits="userSpaceOnUse">
      <stop offset="0" stop-color="#333" />
      <stop offset="0.088" stop-color="#aaa" />
      <stop offset="0.75" stop-color="#aaa" />
      <stop offset="1" stop-color="#333" />
    </linearGradient>

    <filter id="shadow" x="-0.139" y="-0.891" width="1.277" height="2.782" color-interpolation-filters="sRGB">
      <feGaussianBlur stdDeviation="50.255" />
    </filter>

    <path id="shadow-oval" d="M1217.234 667.015c0 37.379-194.698 67.68-434.87 67.68-240.173 0-434.872-30.301-434.872-67.68 0-37.379 194.699-67.68 434.871-67.68 240.173 0 434.87 30.301 434.87 67.68z" />
  </defs>

  <use href="#shadow-oval" fill="#1a1a1a" fill-opacity="0.667" filter="url(#shadow)" transform="matrix(2.02914 0 0 .71847 -49.924 821.7)" />

  <g transform="matrix(3.2252 0 0 3.2252 -553.996 -1612.41)">
    <path fill="url(#bevel)" d="M640.5 823.112c-1.01 42.427-50 94.75-50 94.75H809s-48.99-52.323-50-94.75l-56.22.25z" transform="translate(-51.232)" />
    <rect x="387.899" y="513.951" width="521.239" height="309.107" rx="19.041" ry="18.269" stroke="#aaa" stroke-width="1.55" />
    <path id="SCREEN_L" fill="#fff" d="M408.518 533.504h480v270h-480z" />
    <path fill="#aaa" d="M538.664 909.931h219.708v9.091H538.664z" />
  </g>

  <use href="#shadow-oval" fill="#1a1a1a" fill-opacity="0.667" filter="url(#shadow)" transform="matrix(.85876 0 0 .71847 92.26 906.991)" />
  <g transform="matrix(3.2252 0 0 3.2252 -367.88 -1606.204)">
    <rect x="247.143" y="671.362" width="200" height="266" rx="20" ry="20" stroke="#aaa" stroke-width="0.93" />
    <path id="SCREEN_M" fill="#fff" d="M263.643 687.362h167v222h-167z" />
  </g>

  <use href="#shadow-oval" fill="#1a1a1a" fill-opacity="0.667" filter="url(#shadow)" transform="matrix(.34001 0 0 .71847 87.614 959.77)" />
  <g transform="translate(-767.574 -2230.898) scale(3.99062)">
    <rect x="247.143" y="797.077" width="70" height="130.286" rx="7" ry="9.796" stroke="#aaa" stroke-width="0.752" />
    <path id="SCREEN_S" fill="#fff" d="M252.143 805.219h60v106h-60z" />
  </g>
</svg>
"""

# (id, x, y, w, h)
SCREENS: List[Tuple[str, float, float, float, float]] = [
    ("SCREEN_L", 408.518, 533.504, 480.0, 270.0),  # large (desktop)
    ("SCREEN_M", 263.643, 687.362, 167.0, 222.0),  # medium (tablet portrait)
    ("SCREEN_S", 252.143, 805.219,  60.0, 106.0),  # small (mobile portrait)
]

# Common device viewport sizes we *may* use if they match the mockup aspect ratio.
COMMON_VIEWPORTS = {
    "desktop": (1366, 768),   # ~16:9
    "tablet":  (768, 1024),   # ~3:4 portrait
    "mobile":  (375, 667),    # iPhone 8 portrait (~0.562)
}

# Fallback: derive viewport sizes from the mockup rectangle size * a scale factor.
FALLBACK_MIN = (320, 240)
FALLBACK_SCALE_HINTS = {
    "desktop": 3.2252,
    "tablet":  3.2252,
    "mobile":  3.99062,
}

SCROLL_PRESETS: Dict[str, float] = {"top": 0.0, "mid": 0.5, "middle": 0.5, "bottom": 1.0}


def pretty_xml(xml_bytes: bytes) -> str:
    try:
        from lxml import etree as LET  # type: ignore
        root = LET.fromstring(xml_bytes)
        return LET.tostring(root, pretty_print=True, xml_declaration=False, encoding="unicode")
    except Exception:
        import xml.dom.minidom as minidom
        dom = minidom.parseString(xml_bytes)
        return dom.toprettyxml(indent="  ")


def sanitize_domain(url: str) -> str:
    netloc = urlparse(url).netloc or "site"
    netloc = netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    # Replace anything not alnum, dot, dash with underscore, then dots to underscores
    netloc = re.sub(r"[^a-z0-9\.\-]+", "_", netloc).replace(".", "_")
    netloc = re.sub(r"_+", "_", netloc).strip("_")
    return netloc or "site"


def scroll_frac(name: str) -> float:
    key = (name or "").strip().lower()
    if key not in SCROLL_PRESETS:
        raise SystemExit(f"Unknown scroll preset '{name}'. Use one of: top, mid, bottom.")
    return SCROLL_PRESETS[key]


def choose_viewport(kind: str, rect_w: float, rect_h: float) -> Tuple[int, int]:
    """
    Use common viewport sizes only if aspect ratio is close enough to the mockup rectangle.
    Otherwise, fall back to rect size * a scale hint.
    """
    rect_ar = rect_w / rect_h
    cw, ch = COMMON_VIEWPORTS[kind]
    common_ar = cw / ch

    # "If (only if) it makes sense": require fairly close aspect match.
    # Tolerance chosen to be forgiving but not silly.
    if abs(common_ar - rect_ar) <= 0.10:
        return cw, ch

    # Fallback: scale rect up to a reasonable screenshot resolution.
    scale = FALLBACK_SCALE_HINTS[kind]
    fw = max(FALLBACK_MIN[0], int(round(rect_w * scale)))
    fh = max(FALLBACK_MIN[1], int(round(rect_h * scale)))
    return fw, fh


def get_theme_color_from_page(page) -> Optional[str]:
    """
    Returns meta theme-color (string) if present, else None.
    """
    try:
        val = page.evaluate(
            """() => {
              const m = document.querySelector('meta[name="theme-color"]');
              return m ? (m.getAttribute('content') || '').trim() : '';
            }"""
        )
        if isinstance(val, str) and val.strip():
            return val.strip()
    except Exception:
        pass
    return None


def take_screenshots(url: str, out_dir: Path, domain: str, scrolls: List[str]) -> Tuple[List[Path], Optional[str]]:
    """
    Takes 3 screenshots (desktop/tablet/mobile) and returns their paths + optional theme-color.
    Default scrolls should be ["top","top","top"].
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    from playwright.sync_api import sync_playwright  # type: ignore

    kinds = ["desktop", "tablet", "mobile"]
    if len(scrolls) != 3:
        raise SystemExit("--scrolls must provide exactly 3 values (top|mid|bottom).")

    with sync_playwright() as p:
        browser = p.chromium.launch()
        # Create a context with a higher DPR for crisp screenshots.
        ctx = browser.new_context(device_scale_factor=2)

        page = ctx.new_page()
        page.goto(url, wait_until="networkidle", timeout=60_000)

        theme = get_theme_color_from_page(page)

        scroll_height = page.evaluate(
            "() => Math.max(document.body.scrollHeight, document.documentElement.scrollHeight)"
        )

        shots: List[Path] = []
        for i, (kind, (screen_id, x, y, w, h), scroll_name) in enumerate(zip(kinds, SCREENS, scrolls), start=1):
            vp_w, vp_h = choose_viewport(kind, w, h)
            page.set_viewport_size({"width": vp_w, "height": vp_h})

            frac = scroll_frac(scroll_name)
            max_scroll = max(0, int(scroll_height) - vp_h)
            scroll_y = int(round(max_scroll * frac))
            page.evaluate("(y) => window.scrollTo(0, y)", scroll_y)
            page.wait_for_timeout(250)

            filename = f"{domain}-{kind}-{scroll_name}.png"
            path = out_dir / filename
            page.screenshot(path=str(path), full_page=False)
            shots.append(path)

        ctx.close()
        browser.close()

    return shots, theme


def rel_href(img_path: Path, svg_path: Path) -> str:
    """
    Write image href relative to the SVG's directory (so no leading 'dist/' if SVG is in dist/).
    """
    try:
        return img_path.relative_to(svg_path.parent).as_posix()
    except Exception:
        return img_path.as_posix()


def embed_into_svg(template_svg: str, out_svg: Path, images: List[Path], theme_color: Optional[str]) -> None:
    """
    Replaces SCREEN_L/M/S paths with a clipped image group.

    Width is never cropped:
      - We scale each embedded image so its *width* exactly matches the screen width.
      - Then we vertically center it and clip to the screen rectangle, which may crop height.
    """
    # Parse SVG
    try:
        from lxml import etree as ET  # type: ignore
        parser = ET.XMLParser(remove_blank_text=True)
        root = ET.fromstring(template_svg.encode("utf-8"), parser=parser)
        is_lxml = True
    except Exception:
        import xml.etree.ElementTree as ET  # type: ignore
        root = ET.fromstring(template_svg.encode("utf-8"))
        is_lxml = False

    def q(tag: str) -> str:
        if root.tag.startswith("{"):
            ns = root.tag.split("}")[0].strip("{")
            return f"{{{ns}}}{tag}"
        return tag

    # Find or create <defs>
    defs = None
    for child in list(root):
        if child.tag.endswith("defs"):
            defs = child
            break
    if defs is None:
        if is_lxml:
            defs = root.makeelement(q("defs"))  # type: ignore
        else:
            import xml.etree.ElementTree as ET  # type: ignore
            defs = ET.Element(q("defs"))
        root.insert(0, defs)

    # Optional background rect (theme-color)
    if theme_color:
        # Insert as the very first drawable element (after defs if defs exists first).
        bg = root.makeelement(q("rect")) if is_lxml else __import__("xml.etree.ElementTree").Element(q("rect"))  # type: ignore
        bg.set("x", "0")
        bg.set("y", "0")
        bg.set("width", "2520")
        bg.set("height", "1530")
        bg.set("fill", theme_color)

        # Put it right after <defs> if defs is first; else at index 0.
        inserted = False
        children = list(root)
        for idx, ch in enumerate(children):
            if ch is defs:
                root.insert(idx + 1, bg)
                inserted = True
                break
        if not inserted:
            root.insert(0, bg)

    # Map images to screen ids
    screen_ids = ["SCREEN_L", "SCREEN_M", "SCREEN_S"]
    id_to_img = dict(zip(screen_ids, images))

    # Helper for xml.etree parent-finding
    def find_parent_et(root_node, child):
        for p in root_node.iter():
            for c in list(p):
                if c is child:
                    return p
        return None

    # Create clipPaths and replace screen paths with clipped image groups
    for screen_id, x, y, w, h in SCREENS:
        # Find target element by id
        target = None
        for node in root.iter():
            if node.get("id") == screen_id:
                target = node
                break
        if target is None:
            raise SystemExit(f"Could not find element with id='{screen_id}' in the SVG template.")

        # Build clipPath
        clip_id = f"clip_{screen_id}"
        clip = defs.makeelement(q("clipPath")) if is_lxml else __import__("xml.etree.ElementTree").Element(q("clipPath"))  # type: ignore
        clip.set("id", clip_id)
        clip.set("clipPathUnits", "userSpaceOnUse")

        clip_rect = defs.makeelement(q("rect")) if is_lxml else __import__("xml.etree.ElementTree").Element(q("rect"))  # type: ignore
        clip_rect.set("x", f"{x}")
        clip_rect.set("y", f"{y}")
        clip_rect.set("width", f"{w}")
        clip_rect.set("height", f"{h}")
        clip.append(clip_rect)

        defs.append(clip)

        # Determine embedded image placement so width is never cropped
        img_path = id_to_img[screen_id]
        with Image.open(img_path) as im:
            iw, ih = im.size

        # Scale to match width exactly
        scale = w / float(iw)
        scaled_h = ih * scale
        # Center vertically
        y_img = y + (h - scaled_h) / 2.0

        # Create group with clip
        if is_lxml:
            parent = target.getparent()  # type: ignore
            g = parent.makeelement(q("g"))  # type: ignore
        else:
            import xml.etree.ElementTree as ET  # type: ignore
            parent = find_parent_et(root, target)
            if parent is None:
                raise SystemExit(f"Internal error: could not locate parent for '{screen_id}'.")
            g = ET.Element(q("g"))

        g.set("clip-path", f"url(#{clip_id})")

        # Optional white backdrop inside the screen
        backdrop = g.makeelement(q("rect")) if is_lxml else __import__("xml.etree.ElementTree").Element(q("rect"))  # type: ignore
        backdrop.set("x", f"{x}")
        backdrop.set("y", f"{y}")
        backdrop.set("width", f"{w}")
        backdrop.set("height", f"{h}")
        backdrop.set("fill", "#fff")
        g.append(backdrop)

        img_el = g.makeelement(q("image")) if is_lxml else __import__("xml.etree.ElementTree").Element(q("image"))  # type: ignore
        img_el.set("href", rel_href(img_path, out_svg))
        img_el.set("x", f"{x}")
        img_el.set("y", f"{y_img}")
        img_el.set("width", f"{w}")
        img_el.set("height", f"{scaled_h}")
        # "meet" behavior achieved by our explicit sizing; no cropping in width.
        img_el.set("preserveAspectRatio", "xMidYMid meet")
        g.append(img_el)

        # Replace target path with the group
        if is_lxml:
            idx = parent.index(target)  # type: ignore
            parent.remove(target)        # type: ignore
            parent.insert(idx, g)        # type: ignore
        else:
            children = list(parent)  # type: ignore
            idx = children.index(target)
            parent.remove(target)    # type: ignore
            parent.insert(idx, g)    # type: ignore

    # Write output
    if is_lxml:
        from lxml import etree as ET  # type: ignore
        xml_bytes = ET.tostring(root, encoding="utf-8", xml_declaration=False)
    else:
        import xml.etree.ElementTree as ET  # type: ignore
        xml_bytes = ET.tostring(root, encoding="utf-8")

    out_svg.write_text(pretty_xml(xml_bytes), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("url", help="URL to screenshot")
    ap.add_argument("--out", default="dist", help="Output directory (default: dist)")
    ap.add_argument("--template", default="", help="Optional SVG template file (default: built-in).")
    ap.add_argument(
        "--scrolls",
        nargs=3,
        default=["top", "top", "top"],
        metavar=("DESKTOP", "TABLET", "MOBILE"),
        help="Scroll presets for the 3 screenshots: top|mid|bottom (default: top top top)",
    )
    ap.add_argument("--svg-name", default="", help="Output SVG filename (default: {domain}-mockup.svg)")
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    domain = sanitize_domain(args.url)
    screens_dir = out_dir / "screens"
    screens_dir.mkdir(parents=True, exist_ok=True)

    template_svg = DEFAULT_TEMPLATE_SVG if not args.template else Path(args.template).read_text(encoding="utf-8")

    # 1) Take screenshots
    shots, theme_color = take_screenshots(args.url, screens_dir, domain, args.scrolls)

    # 2) Embed into SVG
    svg_name = args.svg_name.strip() or f"{domain}-mockup.svg"
    out_svg = out_dir / svg_name
    embed_into_svg(template_svg, out_svg, shots, theme_color)

    print("✓ Wrote screenshots:")
    for p in shots:
        try:
            print(f"  - {p.relative_to(out_dir).as_posix()}")
        except Exception:
            print(f"  - {p}")
    print(f"✓ Theme color: {theme_color or '(none found)'}")
    print(f"✓ Wrote SVG: {out_svg}")


if __name__ == "__main__":
    main()
