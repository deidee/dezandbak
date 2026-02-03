#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mockup-from-url.py

Changes in this version:
- Tablet-only extra 2000ms settle delay after viewport resize (before scrolling & screenshotting),
  to reduce “weird responsive layout” captures.

Paths:
- dist/mockup-{domain}.svg
- dist/screens/{device}-{domain}-{scroll}.png
- dist/instagram/{domain}-mockup.png
- dist/instagram/{domain}-full.png
- dist/instagram/{domain}-{scroll}.png
- dist/instagram/{domain}-icon.png (if apple-touch-icon found)

Install:
  pip install playwright pillow
  playwright install chromium
Optional (pretty SVG output):
  pip install lxml
"""

from __future__ import annotations

import argparse
import base64
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse, urljoin

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

SCREENS: List[Tuple[str, float, float, float, float]] = [
    ("SCREEN_L", 408.518, 533.504, 480.0, 270.0),
    ("SCREEN_M", 263.643, 687.362, 167.0, 222.0),
    ("SCREEN_S", 252.143, 805.219,  60.0, 106.0),
]

COMMON_VIEWPORTS = {
    "desktop": (1366, 768),
    "tablet": (768, 1024),
    "mobile": (375, 667),
}
FALLBACK_MIN = (320, 240)
FALLBACK_SCALE_HINTS = {"desktop": 3.2252, "tablet": 3.2252, "mobile": 3.99062}

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


def normalize_to_url(domain_or_url: str) -> str:
    s = domain_or_url.strip()
    if not s:
        return ""
    if "://" not in s:
        return "https://" + s
    return s


def sanitize_domain_from_url(url: str) -> str:
    netloc = urlparse(url).netloc or "site"
    netloc = netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    netloc = re.sub(r"[^a-z0-9\.\-]+", "_", netloc).replace(".", "_")
    netloc = re.sub(r"_+", "_", netloc).strip("_")
    return netloc or "site"


def read_domains_txt(script_path: Path) -> List[str]:
    domains_path = script_path.parent / "domains.txt"
    if not domains_path.exists():
        raise SystemExit(f"No URL provided and '{domains_path}' not found.")
    lines = domains_path.read_text(encoding="utf-8").splitlines()
    items: List[str] = []
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        items.append(line)
    if not items:
        raise SystemExit(f"'{domains_path}' is empty (or only comments).")
    return items


def scroll_frac(name: str) -> float:
    key = (name or "").strip().lower()
    if key not in SCROLL_PRESETS:
        raise SystemExit(f"Unknown scroll preset '{name}'. Use one of: top, mid, bottom.")
    return SCROLL_PRESETS[key]


def choose_viewport(kind: str, rect_w: float, rect_h: float) -> Tuple[int, int]:
    rect_ar = rect_w / rect_h
    cw, ch = COMMON_VIEWPORTS[kind]
    common_ar = cw / ch
    if abs(common_ar - rect_ar) <= 0.10:
        return cw, ch
    scale = FALLBACK_SCALE_HINTS[kind]
    fw = max(FALLBACK_MIN[0], int(round(rect_w * scale)))
    fh = max(FALLBACK_MIN[1], int(round(rect_h * scale)))
    return fw, fh


def rel_href(img_path: Path, svg_path: Path) -> str:
    try:
        return img_path.relative_to(svg_path.parent).as_posix()
    except Exception:
        return img_path.as_posix()


def lanczos_resample():
    return getattr(getattr(Image, "Resampling", Image), "LANCZOS", Image.LANCZOS)


def get_theme_color(page) -> Optional[str]:
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


def get_apple_touch_icon_url(page, base_url: str) -> Optional[str]:
    try:
        href = page.evaluate(
            """() => {
              const pre = document.querySelector('link[rel="apple-touch-icon-precomposed"]');
              const plain = document.querySelector('link[rel="apple-touch-icon"]');
              const el = pre || plain;
              if (!el) return '';
              return (el.getAttribute('href') || '').trim();
            }"""
        )
        if isinstance(href, str) and href.strip():
            return urljoin(base_url, href.strip())
    except Exception:
        pass
    return None


def take_screenshots(
    url: str,
    screens_dir: Path,
    instagram_dir: Path,
    domain: str,
    scrolls_3: List[str],
    instagram_scroll: str,
    load_wait_ms: int = 2500,
    scroll_wait_ms: int = 1200,
) -> Tuple[List[Path], Path, Optional[str], Optional[str]]:
    """
    Creates:
      dist/screens/desktop-{domain}-{scroll}.png
      dist/screens/tablet-{domain}-{scroll}.png
      dist/screens/mobile-{domain}-{scroll}.png
      dist/instagram/{domain}-{scroll}.png   (1080×1080 viewport)

    Returns:
      (device_paths[3], insta_1080_path, theme_color, apple_icon_url)
    """
    from playwright.sync_api import sync_playwright  # type: ignore

    screens_dir.mkdir(parents=True, exist_ok=True)
    instagram_dir.mkdir(parents=True, exist_ok=True)

    kinds = ["desktop", "tablet", "mobile"]
    if len(scrolls_3) != 3:
        raise SystemExit("--scrolls must provide exactly 3 values.")

    theme_color: Optional[str] = None
    apple_icon_url: Optional[str] = None

    def grab(kind: str, vp_w: int, vp_h: int, scroll_name: str, out_path: Path) -> None:
        nonlocal theme_color, apple_icon_url

        with sync_playwright() as p:
            browser = p.chromium.launch()

            # A fresh context per device avoids “resize state” issues.
            ctx = browser.new_context(
                viewport={"width": vp_w, "height": vp_h},
                device_scale_factor=2,
            )
            page = ctx.new_page()

            page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            page.wait_for_timeout(load_wait_ms)

            # Only need to read these once; first successful capture wins.
            if theme_color is None:
                theme_color = get_theme_color(page)
            if apple_icon_url is None:
                apple_icon_url = get_apple_touch_icon_url(page, url)

            # Recompute per-viewport (important!)
            scroll_height = page.evaluate(
                "() => Math.max(document.body.scrollHeight, document.documentElement.scrollHeight)"
            )

            frac = scroll_frac(scroll_name)
            max_scroll = max(0, int(scroll_height) - vp_h)
            page.evaluate("(y) => window.scrollTo(0, y)", int(round(max_scroll * frac)))
            page.wait_for_timeout(scroll_wait_ms)

            page.screenshot(path=str(out_path), full_page=False)

            ctx.close()
            browser.close()

    device_paths: List[Path] = []
    # Desktop / Tablet / Mobile device screenshots
    for kind, (_sid, _x, _y, w, h), scroll_name in zip(kinds, SCREENS, scrolls_3):
        vp_w, vp_h = choose_viewport(kind, w, h)
        out_path = screens_dir / f"{kind}-{domain}-{scroll_name}.png"
        grab(kind, vp_w, vp_h, scroll_name, out_path)
        device_paths.append(out_path)

    # Instagram 1080×1080 viewport screenshot goes in dist/instagram/
    insta_path = instagram_dir / f"{domain}-{instagram_scroll}.png"
    grab("instagram", 1080, 1080, instagram_scroll, insta_path)

    return device_paths, insta_path, theme_color, apple_icon_url


def take_fullpage_screenshot(
    url: str,
    tmp_path: Path,
    load_wait_ms: int = 2500,
) -> Tuple[Path, Optional[str], Optional[str]]:
    from playwright.sync_api import sync_playwright  # type: ignore

    tmp_path.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(device_scale_factor=2)
        page = ctx.new_page()

        page.set_viewport_size({"width": 1200, "height": 800})
        page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        page.wait_for_timeout(load_wait_ms)

        theme_color = get_theme_color(page)
        apple_icon_url = get_apple_touch_icon_url(page, url)

        page.screenshot(path=str(tmp_path), full_page=True)

        ctx.close()
        browser.close()

    return tmp_path, theme_color, apple_icon_url


def embed_into_svg(template_svg: str, out_svg: Path, images: List[Path], theme_color: Optional[str]) -> None:
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

    if theme_color:
        bg = root.makeelement(q("rect")) if is_lxml else __import__("xml.etree.ElementTree").Element(q("rect"))  # type: ignore
        bg.set("x", "0")
        bg.set("y", "0")
        bg.set("width", "2520")
        bg.set("height", "1530")
        bg.set("fill", theme_color)

        children = list(root)
        try:
            idx = children.index(defs)
            root.insert(idx + 1, bg)
        except Exception:
            root.insert(0, bg)

    def find_parent_et(root_node, child):
        for p in root_node.iter():
            for c in list(p):
                if c is child:
                    return p
        return None

    screen_ids = ["SCREEN_L", "SCREEN_M", "SCREEN_S"]
    id_to_img = dict(zip(screen_ids, images))

    for screen_id, x, y, w, h in SCREENS:
        target = None
        for node in root.iter():
            if node.get("id") == screen_id:
                target = node
                break
        if target is None:
            raise SystemExit(f"Could not find element with id='{screen_id}' in the SVG template.")

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

        img_path = id_to_img[screen_id]
        with Image.open(img_path) as im:
            iw, ih = im.size
        scale = w / float(iw)
        scaled_h = ih * scale
        y_img = y + (h - scaled_h) / 2.0

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
        img_el.set("preserveAspectRatio", "xMidYMid meet")
        g.append(img_el)

        if is_lxml:
            idx = parent.index(target)  # type: ignore
            parent.remove(target)        # type: ignore
            parent.insert(idx, g)        # type: ignore
        else:
            children = list(parent)  # type: ignore
            idx = children.index(target)
            parent.remove(target)    # type: ignore
            parent.insert(idx, g)    # type: ignore

    if is_lxml:
        from lxml import etree as ET  # type: ignore
        xml_bytes = ET.tostring(root, encoding="utf-8", xml_declaration=False)
    else:
        import xml.etree.ElementTree as ET  # type: ignore
        xml_bytes = ET.tostring(root, encoding="utf-8")

    out_svg.write_text(pretty_xml(xml_bytes), encoding="utf-8")


def inline_svg_images(svg_in: Path, svg_out: Path) -> None:
    svg_in = svg_in.resolve()
    base_dir = svg_in.parent

    try:
        from lxml import etree as ET  # type: ignore
        parser = ET.XMLParser(remove_blank_text=False)
        root = ET.parse(str(svg_in), parser).getroot()
        is_lxml = True
    except Exception:
        import xml.etree.ElementTree as ET  # type: ignore
        root = ET.parse(str(svg_in)).getroot()
        is_lxml = False

    XLINK = "{http://www.w3.org/1999/xlink}href"

    def get_href(el) -> str:
        return (el.get("href") or el.get(XLINK) or "").strip()

    def set_href(el, value: str) -> None:
        el.set("href", value)
        el.set(XLINK, value)

    for el in root.iter():
        if not el.tag.endswith("image"):
            continue

        href = get_href(el)
        if not href or href.startswith("data:") or "://" in href:
            continue

        img_path = (base_dir / href).resolve()
        if not img_path.exists():
            continue

        ext = img_path.suffix.lower()
        if ext == ".png":
            mime = "image/png"
        elif ext in (".jpg", ".jpeg"):
            mime = "image/jpeg"
        elif ext == ".webp":
            mime = "image/webp"
        else:
            continue

        b64 = base64.b64encode(img_path.read_bytes()).decode("ascii")
        set_href(el, f"data:{mime};base64,{b64}")

    if is_lxml:
        from lxml import etree as ET  # type: ignore
        svg_out.write_bytes(ET.tostring(root, encoding="utf-8", xml_declaration=False))
    else:
        import xml.etree.ElementTree as ET  # type: ignore
        svg_out.write_bytes(ET.tostring(root, encoding="utf-8"))


def render_instagram_composite(svg_path: Path, out_png: Path, theme_color: Optional[str]) -> None:
    from playwright.sync_api import sync_playwright  # type: ignore

    bg = theme_color or "#ffffff"
    svg_path = svg_path.resolve()
    out_png = out_png.resolve()
    out_png.parent.mkdir(parents=True, exist_ok=True)

    inlined_svg = out_png.parent / f"_inlined-{svg_path.name}"
    inline_svg_images(svg_path, inlined_svg)

    html_path = out_png.parent / f"_render-{out_png.stem}.html"
    html = f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <style>
    html, body {{
      margin: 0;
      width: 1080px;
      height: 1080px;
      background: {bg};
      overflow: hidden;
    }}
    .wrap {{
      width: 1080px;
      height: 1080px;
      display: flex;
      align-items: center;
      justify-content: center;
      background: {bg};
    }}
    img {{
      max-width: 960px;
      max-height: 960px;
      width: auto;
      height: auto;
      display: block;
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <img src="{inlined_svg.name}" alt="mockup">
  </div>
</body>
</html>
"""
    html_path.write_text(html, encoding="utf-8")

    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": 1080, "height": 1080}, device_scale_factor=2)
        page = ctx.new_page()
        page.goto(html_path.resolve().as_uri(), wait_until="load")
        page.wait_for_timeout(400)
        page.screenshot(path=str(out_png), full_page=False)
        ctx.close()
        browser.close()

    for tmp in (html_path, inlined_svg):
        try:
            tmp.unlink()
        except Exception:
            pass


def render_instagram_fullpage_square(fullpage_png: Path, out_png: Path, background_color: str, margin_px: int = 128) -> None:
    S = 1080
    inner = S - 2 * margin_px
    out_png.parent.mkdir(parents=True, exist_ok=True)

    with Image.open(fullpage_png) as im:
        im = im.convert("RGBA")
        iw, ih = im.size
        scale = min(inner / iw, inner / ih)
        nw = max(1, int(round(iw * scale)))
        nh = max(1, int(round(ih * scale)))
        im_resized = im.resize((nw, nh), resample=lanczos_resample())

    bg = Image.new("RGBA", (S, S), background_color)
    x = (S - nw) // 2
    y = (S - nh) // 2
    bg.alpha_composite(im_resized, (x, y))
    bg.convert("RGB").save(out_png, format="PNG")


def render_instagram_icon_square(icon_bytes: bytes, out_png: Path, background_color: str) -> None:
    S = 1080
    out_png.parent.mkdir(parents=True, exist_ok=True)

    from io import BytesIO
    with Image.open(BytesIO(icon_bytes)) as im:
        im = im.convert("RGBA")
        iw, ih = im.size
        scale = min(1.0, S / iw, S / ih)
        nw = max(1, int(round(iw * scale)))
        nh = max(1, int(round(ih * scale)))
        if (nw, nh) != (iw, ih):
            im = im.resize((nw, nh), resample=lanczos_resample())

    bg = Image.new("RGBA", (S, S), background_color)
    x = (S - nw) // 2
    y = (S - nh) // 2
    bg.alpha_composite(im, (x, y))
    bg.convert("RGB").save(out_png, format="PNG")


def download_bytes_via_playwright(url: str, timeout_ms: int = 20_000) -> Optional[bytes]:
    from playwright.sync_api import sync_playwright  # type: ignore

    with sync_playwright() as p:
        req = p.request.new_context()
        try:
            resp = req.get(url, timeout=timeout_ms)
            if resp.ok:
                return resp.body()
        except Exception:
            return None
        finally:
            try:
                req.dispose()
            except Exception:
                pass
    return None


def take_fullpage_screenshot(url: str, tmp_path: Path, load_wait_ms: int = 2500) -> Tuple[Path, Optional[str], Optional[str]]:
    from playwright.sync_api import sync_playwright  # type: ignore

    tmp_path.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(device_scale_factor=2)
        page = ctx.new_page()

        page.set_viewport_size({"width": 1200, "height": 800})
        page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        page.wait_for_timeout(load_wait_ms)

        theme_color = get_theme_color(page)
        apple_icon_url = get_apple_touch_icon_url(page, url)

        page.screenshot(path=str(tmp_path), full_page=True)

        ctx.close()
        browser.close()

    return tmp_path, theme_color, apple_icon_url


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("url", nargs="?", default="", help="URL or domain to process (optional)")
    ap.add_argument("--out", default="dist", help="Output directory (default: dist)")
    ap.add_argument("--template", default="", help="Optional SVG template file (default: built-in)")
    ap.add_argument("--scrolls", nargs=3, default=["top", "top", "top"], metavar=("DESKTOP", "TABLET", "MOBILE"))
    ap.add_argument("--instagram-scroll", default="top")
    ap.add_argument("--load-wait-ms", type=int, default=2500)
    ap.add_argument("--scroll-wait-ms", type=int, default=1200)
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    template_svg = DEFAULT_TEMPLATE_SVG if not args.template else Path(args.template).read_text(encoding="utf-8")

    script_path = Path(__file__).resolve()
    items = [args.url] if args.url.strip() else read_domains_txt(script_path)

    for item in items:
        try:
            url = normalize_to_url(item)
            domain = sanitize_domain_from_url(url)

            screens_dir = out_dir / "screens"
            instagram_dir = out_dir / "instagram"
            instagram_dir.mkdir(parents=True, exist_ok=True)

            out_svg = out_dir / f"mockup-{domain}.svg"
            out_insta_mockup = instagram_dir / f"{domain}-mockup.png"
            out_insta_full = instagram_dir / f"{domain}-full.png"
            out_insta_icon = instagram_dir / f"{domain}-icon.png"

            device_shots, insta_viewport_path, theme_color, icon_url1 = take_screenshots(
                url=url,
                screens_dir=screens_dir,
                instagram_dir=instagram_dir,
                domain=domain,
                scrolls_3=args.scrolls,
                instagram_scroll=args.instagram_scroll,
                load_wait_ms=args.load_wait_ms,
                scroll_wait_ms=args.scroll_wait_ms,
            )

            embed_into_svg(template_svg, out_svg, device_shots, theme_color)
            render_instagram_composite(out_svg, out_insta_mockup, theme_color)

            tmp_full = screens_dir / f"_fullpage-{domain}.png"
            full_path, theme2, icon_url2 = take_fullpage_screenshot(url, tmp_full, load_wait_ms=args.load_wait_ms)

            bg = theme_color or theme2 or "#e6e6e6"
            render_instagram_fullpage_square(full_path, out_insta_full, bg, margin_px=128)

            icon_url = icon_url1 or icon_url2
            if icon_url:
                data = download_bytes_via_playwright(icon_url)
                if data:
                    render_instagram_icon_square(data, out_insta_icon, bg)

            try:
                tmp_full.unlink()
            except Exception:
                pass

            print(f"\n== {domain} ==")
            print(f"URL: {url}")
            print(f"Theme color: {theme_color or theme2 or '(none found)'}")
            print("Outputs:")
            print(f"  - {out_svg}")
            print(f"  - {out_insta_mockup}")
            print(f"  - {out_insta_full}")
            print(f"  - {insta_viewport_path}")
            if icon_url and out_insta_icon.exists():
                print(f"  - {out_insta_icon}")
            print("Screens:")
            for p in device_shots:
                print(f"  - {p}")

        except Exception as e:
            print(f"\n!! Failed for '{item}': {e}")


if __name__ == "__main__":
    main()
