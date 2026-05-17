"""Markdown content helpers: outline + plain text extraction.

文档采用 Toast UI Editor 后,数据库字段 `content_json` 实际存储的是 Markdown 字符串
(为避免破坏既有迁移,字段名保留)。本模块基于 Markdown 提供以下能力:

- extract_outline(md): 提取 H1-H3 形成大纲
- extract_plain_text(md): 去除 Markdown 标记,生成纯文本(供搜索/AI 使用)
- extract_markdown(md): 兼容旧调用,直接返回 Markdown
"""
from __future__ import annotations

import re
from typing import Iterable


_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_FENCE_RE = re.compile(r"^(```|~~~)")


def _slugify_anchor(text: str) -> str:
    text = (text or "").strip().lower()
    text = re.sub(r"[\s\u3000]+", "-", text)
    text = re.sub(r"[^a-z0-9\u4e00-\u9fa5\-_]", "", text)
    return text or "section"


def _strip_inline_md(text: str) -> str:
    """去除 Markdown 行内格式标记,保留文字。"""
    if not text:
        return ""
    # 图片 ![alt](url) -> alt
    text = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", text)
    # 链接 [text](url) -> text
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    # 代码 `code` -> code
    text = re.sub(r"`([^`]+)`", r"\1", text)
    # 加粗/斜体/删除线
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"__([^_]+)__", r"\1", text)
    text = re.sub(r"\*([^*]+)\*", r"\1", text)
    text = re.sub(r"_([^_]+)_", r"\1", text)
    text = re.sub(r"~~([^~]+)~~", r"\1", text)
    # 残余的 HTML 标签
    text = re.sub(r"<[^>]+>", "", text)
    return text.strip()


def _iter_lines_skip_code(md: str) -> Iterable[tuple[int, str]]:
    """逐行迭代,跳过围栏代码块内容。"""
    in_fence = False
    fence_marker = ""
    for idx, line in enumerate((md or "").splitlines(), 1):
        m = _FENCE_RE.match(line.lstrip())
        if m:
            marker = m.group(1)
            if not in_fence:
                in_fence = True
                fence_marker = marker
                continue
            if marker == fence_marker:
                in_fence = False
                fence_marker = ""
                continue
        if in_fence:
            continue
        yield idx, line


def extract_outline(content_json: str | None) -> list[dict]:
    """从 Markdown 提取 H1-H3 标题,生成 [{level, text, anchor}] 列表。"""
    md = content_json or ""
    if not md.strip():
        return []
    outline: list[dict] = []
    used: dict[str, int] = {}
    for _, line in _iter_lines_skip_code(md):
        m = _HEADING_RE.match(line)
        if not m:
            continue
        level = len(m.group(1))
        if level > 3:
            continue
        text = _strip_inline_md(m.group(2))
        if not text:
            continue
        base = _slugify_anchor(text)
        used[base] = used.get(base, 0) + 1
        anchor = base if used[base] == 1 else f"{base}-{used[base]}"
        outline.append({"level": level, "text": text, "anchor": anchor})
    return outline


def extract_plain_text(content_json: str | None) -> str:
    """从 Markdown 提取纯文本(供搜索/AI 使用)。"""
    md = content_json or ""
    if not md.strip():
        return ""
    parts: list[str] = []
    in_fence = False
    fence_marker = ""
    for line in md.splitlines():
        stripped = line.lstrip()
        m = _FENCE_RE.match(stripped)
        if m:
            marker = m.group(1)
            if not in_fence:
                in_fence = True
                fence_marker = marker
                continue
            if marker == fence_marker:
                in_fence = False
                fence_marker = ""
                continue
        if in_fence:
            parts.append(line)
            continue
        # 标题
        h = _HEADING_RE.match(line)
        if h:
            parts.append(_strip_inline_md(h.group(2)))
            continue
        # 列表 / 引用 前缀去掉
        body = re.sub(r"^\s*([>\-*+]|\d+\.)\s+", "", line)
        # 任务列表 [x] / [ ]
        body = re.sub(r"^\[[ xX]\]\s*", "", body)
        # 表格分隔行(全是 - 和 | )去掉
        if re.fullmatch(r"\s*\|?\s*[-:\s|]+\|?\s*", body) and "|" in line:
            continue
        # 表格内容: | a | b | -> a  b
        if "|" in body and body.strip().startswith("|"):
            cells = [c.strip() for c in body.strip().strip("|").split("|")]
            body = "  ".join(_strip_inline_md(c) for c in cells if c)
        else:
            body = _strip_inline_md(body)
        if body:
            parts.append(body)
    return "\n".join(parts).strip()


def extract_markdown(content_json: str | None) -> str:
    """兼容旧调用:文档已经以 Markdown 存储,直接返回。"""
    return (content_json or "").strip()
