#!/usr/bin/env python3
"""Check local documentation links, UI assets and readable project images."""
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


def main():
    failures = []
    checked = 0
    documents = [ROOT / "README.md", ROOT / "SETUP_RASPBERRY_PI.md", *sorted((ROOT / "docs").glob("*.md"))]
    for path in documents:
        if path.name.startswith("."):
            continue
        text = path.read_text(encoding="utf-8")
        links = re.findall(r"!?\[[^\]]*\]\(([^)]+)\)", text)
        links += re.findall(r'<img[^>]+src="([^"]+)"', text)
        for link in links:
            parsed = urlsplit(link)
            if parsed.scheme or link.startswith("#"):
                continue
            target = (path.parent / unquote(parsed.path)).resolve()
            if not target.is_relative_to(ROOT) or not target.exists():
                failures.append(f"{path.relative_to(ROOT)}: missing local link {link}")
            checked += 1
    ui = (ROOT / "src/templates/index.html").read_text(encoding="utf-8")
    for asset in re.findall(r'(?:src="|href="|url\(")(/static/[^"\)]+)', ui):
        if not (ROOT / "src" / asset.lstrip("/")).is_file():
            failures.append("Missing UI asset: " + asset)
        checked += 1
    for image in [*sorted((ROOT / "docs/assets").glob("*.png")), *sorted((ROOT / "src/static").glob("*.png"))]:
        with Image.open(image) as content:
            content.verify()
        checked += 1
    if failures:
        print("\n".join(failures))
        return 1
    print(f"Checked {checked} local links/assets; no broken references or unreadable PNGs.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
