"""Download all third-party static assets to app/static/vendor/.

Run this once after cloning the project:
    python scripts/fetch_vendors.py

Targets are listed in VENDORS below. We use plain `requests` to keep the script
trivially auditable. All URLs point to widely mirrored CDNs (jsdelivr / unpkg);
once downloaded the application never hits the network for static assets.
"""
from __future__ import annotations

import sys
from pathlib import Path

import requests


ROOT = Path(__file__).resolve().parent.parent
VENDOR = ROOT / "app" / "static" / "vendor"


# (relative_path, url)
VENDORS: list[tuple[str, str]] = [
    # Tailwind (standalone bundled CSS via CDN play; you can also build your own)
    ("css/tailwind.min.css",
     "https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css"),
    # Alpine.js
    ("js/alpine.min.js",
     "https://cdn.jsdelivr.net/npm/alpinejs@3.14.1/dist/cdn.min.js"),
    # Editor.js + plugins
    ("js/editorjs/editor.min.js",
     "https://cdn.jsdelivr.net/npm/@editorjs/editorjs@2.30.5/dist/editorjs.umd.min.js"),
    ("js/editorjs/header.min.js",
     "https://cdn.jsdelivr.net/npm/@editorjs/header@2.8.1/dist/header.umd.min.js"),
    ("js/editorjs/list.min.js",
     "https://cdn.jsdelivr.net/npm/@editorjs/list@1.10.0/dist/list.umd.min.js"),
    ("js/editorjs/checklist.min.js",
     "https://cdn.jsdelivr.net/npm/@editorjs/checklist@1.6.0/dist/checklist.umd.min.js"),
    ("js/editorjs/quote.min.js",
     "https://cdn.jsdelivr.net/npm/@editorjs/quote@2.7.3/dist/quote.umd.min.js"),
    ("js/editorjs/code.min.js",
     "https://cdn.jsdelivr.net/npm/@editorjs/code@2.9.0/dist/code.umd.min.js"),
    ("js/editorjs/inline-code.min.js",
     "https://cdn.jsdelivr.net/npm/@editorjs/inline-code@1.5.1/dist/inline-code.umd.min.js"),
    ("js/editorjs/table.min.js",
     "https://cdn.jsdelivr.net/npm/@editorjs/table@2.4.2/dist/table.umd.min.js"),
    ("js/editorjs/marker.min.js",
     "https://cdn.jsdelivr.net/npm/@editorjs/marker@1.4.0/dist/marker.umd.min.js"),
    ("js/editorjs/delimiter.min.js",
     "https://cdn.jsdelivr.net/npm/@editorjs/delimiter@1.4.2/dist/delimiter.umd.min.js"),
    # highlight.js
    ("js/highlight.min.js",
     "https://cdn.jsdelivr.net/npm/highlight.js@11.10.0/lib/index.min.js"),
    ("css/highlight-github.min.css",
     "https://cdn.jsdelivr.net/npm/highlight.js@11.10.0/styles/github.min.css"),
    # Lucide icons (single SVG sprite is more efficient; we use the JS variant)
    ("js/lucide.min.js",
     "https://cdn.jsdelivr.net/npm/lucide@0.452.0/dist/umd/lucide.min.js"),
    # Inter font
    ("css/inter.css",
     "https://cdn.jsdelivr.net/npm/@fontsource/inter@5.1.0/index.min.css"),
]


def download(url: str, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    print(f"  -> {url}")
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    dst.write_bytes(r.content)
    print(f"     saved to {dst.relative_to(ROOT)} ({len(r.content)} bytes)")


def main() -> int:
    VENDOR.mkdir(parents=True, exist_ok=True)
    fail = 0
    for rel, url in VENDORS:
        target = VENDOR / rel
        if target.exists() and target.stat().st_size > 0:
            print(f"[skip] {rel}")
            continue
        try:
            download(url, target)
        except Exception as e:  # pragma: no cover
            print(f"[error] {rel}: {e}")
            fail += 1
    print()
    if fail:
        print(f"完成（{fail} 个失败）。可重试该脚本以补齐缺失资源。")
        return 1
    print("全部资源已下载到 app/static/vendor/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
