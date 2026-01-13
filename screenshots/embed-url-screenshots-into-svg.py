#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
embed-url-screenshots-into-svg.py

Takes a URL, makes 3 PNG screenshots, and embeds them into the 3 "screen"
rectangles of the SVG design.

Changes vs previous:
- The embedded <image href="..."> is written as a path *relative to the output SVG*,
  so if the SVG and images live under the same output dir, you won't get "dist/" in href.
- By default, all three screenshots are taken from the TOP of the page.
  You can opt into top/mid/bottom with --scrolls top mid bottom (or any 3 values).

Requires:
  pip install playwright
  playwright install chromium
Optional (prettier SVG):
  pip install lxml
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import List, Tuple

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

# Screen specs in *local* coordinates (inside their groups).
# (id, x, y, w, h, group_scale)
SCREENS: List[Tuple[str, float, float, float, float, float]] = [
    ("SCREEN_L", 408.518, 533.504, 480.0, 270.0, 3.2252),
    ("SCREEN_M", 263.643, 687.362, 167.0, 222.0, 3.2252),
    ("SCREEN_S", 252.143, 805.219,  60.0, 106.0, 3.99062),
]

SCROLL_PRESETS = {
    "top": 0.0,
    "mid": 0.5,
    "middle": 0.5,
    "bottom": 1.0,
}


def _pretty_xml(xml_bytes: bytes) -> str:
    # Prefer lxml pretty_print when available; else minidom.
    try:
        from lxml import etree as LET  # type: ignore
        root = LET.fromstring(xml_bytes)
        return LET.tostring(root, pretty_print=True, xml_declaration=False, encoding="unicode")
    except Exception:
        import xml.dom.minidom as minidom
        dom = minidom.parseString(xml_bytes)
        return dom.toprettyxml(indent="  ")


def _scroll_frac_from_name(name: str) -> float:
    key = (name or "").strip().lower()
    if key not in SCROLL_PRESETS:
        raise SystemExit(f"Unknown scroll preset '{name}'. Use one of: top, mid, bottom.")
    return SCROLL_PRESETS[key]


def take_three_screenshots(url: str, out_dir: Path, scrolls: List[str]) -> List[Path]:
    """
    Creates 3 screenshots of the URL sized roughly to match each screen's on-canvas size.
    By default scrolls are all 'top' unless overridden.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    shots: List[Path] = []

    from playwright.sync_api import sync_playwright  # type: ignore

    scroll_fracs = [_scroll_frac_from_name(s) for s in scrolls]

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(device_scale_factor=2)  # crisp screenshots

        page.goto(url, wait_until="networkidle", timeout=60_000)

        scroll_height = page.evaluate(
            "() => Math.max(document.body.scrollHeight, document.documentElement.scrollHeight)"
        )

        for i, ((screen_id, x, y, w, h, scale), frac) in enumerate(zip(SCREENS, scroll_fracs), start=1):
            # Choose a viewport that matches target aspect and roughly matches visual size.
            target_w = max(320, int(round(w * scale)))
            target_h = max(240, int(round(h * scale)))

            page.set_viewport_size({"width": target_w, "height": target_h})

            max_scroll = max(0, int(scroll_height) - target_h)
            scroll_y = int(round(max_scroll * frac))
            page.evaluate("(y) => window.scrollTo(0, y)", scroll_y)
            page.wait_for_timeout(200)  # let layout settle

            shot_path = out_dir / f"screen_{i}.png"
            page.screenshot(path=str(shot_path), full_page=False)
            shots.append(shot_path)

        browser.close()

    return shots


def embed_images_into_svg(template_svg: str, image_paths: List[Path], out_svg: Path) -> None:
    """
    Replaces the 3 white 'screen' paths (ids SCREEN_L/M/S) with <image> elements.
    Image hrefs are written relative to the SVG file location.
    """
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

    # href should be relative to output svg path
    def rel_href(img_path: Path) -> str:
        try:
            return img_path.relative_to(out_svg.parent).as_posix()
        except Exception:
            # fallback: best-effort relative path
            return img_path.as_posix()

    id_to_href = {
        "SCREEN_L": rel_href(image_paths[0]),
        "SCREEN_M": rel_href(image_paths[1]),
        "SCREEN_S": rel_href(image_paths[2]),
    }

    # xml.etree has no getparent; provide helper for that case
    def find_parent_et(root_node, child):
        for p in root_node.iter():
            for c in list(p):
                if c is child:
                    return p
        return None

    for screen_id, x, y, w, h, _scale in SCREENS:
        target = None
        for node in root.iter():
            if node.get("id") == screen_id:
                target = node
                break
        if target is None:
            raise SystemExit(f"Could not find element with id='{screen_id}' in the SVG template.")

        if is_lxml:
            parent = target.getparent()  # type: ignore
            img = parent.makeelement(q("image"))  # type: ignore
        else:
            import xml.etree.ElementTree as ET  # type: ignore
            parent = find_parent_et(root, target)
            if parent is None:
                raise SystemExit(f"Internal error: could not locate parent for '{screen_id}'.")
            img = ET.Element(q("image"))

        img.set("href", id_to_href[screen_id])  # SVG2 `href` (xlink is deprecated)
        img.set("x", f"{x}")
        img.set("y", f"{y}")
        img.set("width", f"{w}")
        img.set("height", f"{h}")
        img.set("preserveAspectRatio", "xMidYMid slice")

        # Replace in-place
        if is_lxml:
            idx = parent.index(target)  # type: ignore
            parent.remove(target)        # type: ignore
            parent.insert(idx, img)      # type: ignore
        else:
            children = list(parent)  # type: ignore
            idx = children.index(target)
            parent.remove(target)    # type: ignore
            parent.insert(idx, img)  # type: ignore

    if is_lxml:
        from lxml import etree as ET  # type: ignore
        xml_bytes = ET.tostring(root, encoding="utf-8", xml_declaration=False)
    else:
        import xml.etree.ElementTree as ET  # type: ignore
        xml_bytes = ET.tostring(root, encoding="utf-8")

    out_svg.write_text(_pretty_xml(xml_bytes), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("url", help="URL to screenshot")
    ap.add_argument("--out", default="dist", help="Output directory (default: dist)")
    ap.add_argument("--template", default="", help="Optional SVG template file. If omitted, uses built-in template.")
    ap.add_argument("--svg-name", default="composited.svg", help="Output SVG filename (default: composited.svg)")
    ap.add_argument(
        "--scrolls",
        nargs=3,
        default=["top", "top", "top"],
        metavar=("S1", "S2", "S3"),
        help="Scroll presets for the 3 screenshots: top|mid|bottom (default: top top top)",
    )
    args = ap.parse_args()

    out_dir = Path(args.out)
    screens_dir = out_dir / "screens"
    out_dir.mkdir(parents=True, exist_ok=True)

    template_svg = DEFAULT_TEMPLATE_SVG if not args.template else Path(args.template).read_text(encoding="utf-8")

    # 1) Screenshots
    shots = take_three_screenshots(args.url, screens_dir, args.scrolls)

    # 2) Embed into SVG
    out_svg = out_dir / args.svg_name
    embed_images_into_svg(template_svg, shots, out_svg)

    print("✓ Wrote screenshots:")
    for p in shots:
        # print relative to out_dir for readability
        try:
            rp = p.relative_to(out_dir)
            print(f"  - {out_dir.name}/{rp.as_posix()}")
        except Exception:
            print(f"  - {p}")
    print(f"✓ Wrote SVG: {out_svg}")


if __name__ == "__main__":
    main()
