"""Markdown rendering helpers."""
from __future__ import annotations

import re

import bleach
import markdown as md


_ALLOWED_TAGS = list(bleach.sanitizer.ALLOWED_TAGS) + [
    "p", "pre", "code", "h1", "h2", "h3", "h4", "h5", "h6",
    "img", "table", "thead", "tbody", "tr", "th", "td",
    "hr", "br", "span", "div", "del", "input", "blockquote",
]
_ALLOWED_ATTRS = {
    **bleach.sanitizer.ALLOWED_ATTRIBUTES,
    "a": ["href", "title", "class", "data-slug", "data-redlink"],
    "img": ["src", "alt", "title"],
    "span": ["class"],
    "div": ["class"],
    "code": ["class"],
    "input": ["type", "checked", "disabled"],
    "th": ["align"],
    "td": ["align"],
}


WIKILINK_RE = re.compile(r"\[\[([^\[\]\n]+?)\]\]")


def render_markdown(text: str) -> str:
    if not text:
        return ""
    html = md.markdown(
        text,
        extensions=["extra", "sane_lists", "tables", "fenced_code", "toc", "nl2br"],
        output_format="html5",
    )
    return bleach.clean(html, tags=_ALLOWED_TAGS, attributes=_ALLOWED_ATTRS, strip=True)


def render_wiki_markdown(text: str, resolver) -> str:
    """Render markdown for AI Wiki article.

    [[Title]] / [[Title|Anchor]] -> link via resolver(title) returning slug or None.
    """
    if not text:
        return ""

    def replace(m: re.Match) -> str:
        raw = m.group(1).strip()
        if "|" in raw:
            target, anchor = raw.split("|", 1)
            target, anchor = target.strip(), anchor.strip()
        else:
            target, anchor = raw, raw
        slug = resolver(target)
        if slug:
            return f'[{anchor}](#WIKI:{slug})'
        return f'<span class="wiki-redlink" data-redlink="1">{anchor}</span>'

    text = WIKILINK_RE.sub(replace, text)
    html = render_markdown(text)
    # Replace placeholder anchor "#WIKI:slug" with actual route placeholder. We keep
    # it as-is here; the route layer will rewrite to the actual URL.
    return html


def collect_wikilinks(text: str) -> list[str]:
    if not text:
        return []
    out = []
    for m in WIKILINK_RE.finditer(text):
        raw = m.group(1).strip()
        target = raw.split("|", 1)[0].strip()
        if target:
            out.append(target)
    # de-dup but keep order
    seen = set()
    result = []
    for t in out:
        if t.lower() in seen:
            continue
        seen.add(t.lower())
        result.append(t)
    return result
