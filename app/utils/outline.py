"""Editor.js content helpers: outline + plain text extraction."""
from __future__ import annotations

import json
import re
from typing import Iterable


def _slugify_anchor(text: str) -> str:
    text = (text or "").strip().lower()
    text = re.sub(r"[\s\u3000]+", "-", text)
    text = re.sub(r"[^a-z0-9\u4e00-\u9fa5\-_]", "", text)
    return text or "section"


def _strip_html(html: str) -> str:
    if not html:
        return ""
    return re.sub(r"<[^>]+>", "", html)


def parse_editor_blocks(content_json: str | None) -> list[dict]:
    if not content_json:
        return []
    try:
        data = json.loads(content_json)
    except (TypeError, ValueError):
        return []
    if isinstance(data, dict):
        return data.get("blocks") or []
    return []


def extract_outline(content_json: str | None) -> list[dict]:
    """Extract H1-H3 headers from Editor.js JSON.

    Returns list of {level, text, anchor}.
    """
    outline = []
    used = {}
    for block in parse_editor_blocks(content_json):
        if block.get("type") != "header":
            continue
        data = block.get("data") or {}
        level = int(data.get("level") or 2)
        if level > 3:
            continue
        text = _strip_html(data.get("text") or "")
        if not text.strip():
            continue
        base = _slugify_anchor(text)
        used[base] = used.get(base, 0) + 1
        anchor = base if used[base] == 1 else f"{base}-{used[base]}"
        outline.append({"level": level, "text": text, "anchor": anchor})
    return outline


def extract_plain_text(content_json: str | None) -> str:
    """Convert Editor.js content to plain text for search / AI use."""
    parts: list[str] = []
    for block in parse_editor_blocks(content_json):
        btype = block.get("type")
        data = block.get("data") or {}
        if btype in {"paragraph", "header", "quote"}:
            parts.append(_strip_html(data.get("text") or ""))
        elif btype == "list":
            items = data.get("items") or []
            for it in items:
                if isinstance(it, str):
                    parts.append("- " + _strip_html(it))
                elif isinstance(it, dict):
                    parts.append("- " + _strip_html(it.get("content") or it.get("text") or ""))
        elif btype == "checklist":
            for it in data.get("items") or []:
                parts.append("- " + _strip_html(it.get("text") or ""))
        elif btype == "code":
            parts.append(data.get("code") or "")
        elif btype == "table":
            for row in data.get("content") or []:
                parts.append(" | ".join(_strip_html(c) for c in row))
        elif btype == "delimiter":
            parts.append("---")
        elif btype == "image":
            cap = _strip_html(data.get("caption") or "")
            if cap:
                parts.append(cap)
    return "\n".join(p for p in parts if p)


def extract_markdown(content_json: str | None) -> str:
    """Convert Editor.js content to a simple markdown representation."""
    out: list[str] = []
    for block in parse_editor_blocks(content_json):
        btype = block.get("type")
        data = block.get("data") or {}
        if btype == "header":
            level = int(data.get("level") or 2)
            text = _strip_html(data.get("text") or "")
            out.append("#" * max(1, min(level, 6)) + " " + text)
        elif btype == "paragraph":
            out.append(_strip_html(data.get("text") or ""))
        elif btype == "quote":
            text = _strip_html(data.get("text") or "")
            out.append("> " + text.replace("\n", "\n> "))
        elif btype == "list":
            style = data.get("style") or "unordered"
            items = data.get("items") or []
            for idx, it in enumerate(items, 1):
                content = it if isinstance(it, str) else (it.get("content") or it.get("text") or "")
                content = _strip_html(content)
                prefix = f"{idx}. " if style == "ordered" else "- "
                out.append(prefix + content)
        elif btype == "checklist":
            for it in data.get("items") or []:
                checked = "[x]" if it.get("checked") else "[ ]"
                out.append(f"- {checked} " + _strip_html(it.get("text") or ""))
        elif btype == "code":
            out.append("```\n" + (data.get("code") or "") + "\n```")
        elif btype == "table":
            rows = data.get("content") or []
            if rows:
                header = rows[0]
                out.append("| " + " | ".join(_strip_html(c) for c in header) + " |")
                out.append("| " + " | ".join(["---"] * len(header)) + " |")
                for row in rows[1:]:
                    out.append("| " + " | ".join(_strip_html(c) for c in row) + " |")
        elif btype == "delimiter":
            out.append("---")
        elif btype == "image":
            url = (data.get("file") or {}).get("url") or data.get("url") or ""
            cap = _strip_html(data.get("caption") or "")
            if url:
                out.append(f"![{cap}]({url})")
        out.append("")
    return "\n".join(out).strip()
