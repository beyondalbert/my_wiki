"""AI service: LLM wrapper + Karpathy-style Wiki builder + link resolver.

This module implements the AI Knowledge Base feature following Karpathy's LLM Wiki
methodology: convert each source document into a markdown article with a unified
template (Title / Summary / Tags / Content / Related Notes), where related
articles are referenced via ``[[Title]]`` wiki-links. After all articles are
rewritten, a second pass scans the ``[[...]]`` placeholders and resolves them
against the article title + alias table, building the ``ai_kb_links`` table for
backlinks and graph rendering.

By default this requires NO vector database and NO embeddings - it is pure
markdown + bidirectional hyperlinks. Vector search is only used when the
optional RAG augmentation is enabled.
"""
from __future__ import annotations

import json
import os
import re
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

from flask import current_app
from slugify import slugify

from ..extensions import db
from ..models import (
    AIKnowledgeBase,
    AIKBSource,
    AIKBSourceStatus,
    AIKBStatus,
    AIKBArticle,
    AIKBLink,
    Document,
)
from ..utils.markdown import collect_wikilinks
from ..utils.outline import extract_markdown


# ---------------------------------------------------------------------------
# LLM Client
# ---------------------------------------------------------------------------

class LLMClient:
    """Thin wrapper around the OpenAI-compatible SDK.

    ``base_url`` and ``api_key`` come from app config so any compatible vendor
    works (OpenAI / DeepSeek / Tongyi / local proxy).

    Priority: explicit param > DB system_config > app.config > default.
    """

    def __init__(self, base_url: str | None = None, api_key: str | None = None,
                 model: str | None = None):
        from . import config_service  # avoid circular import
        cfg = current_app.config
        # DB config_service may fail in background thread if cache is cold;
        # fall back to app.config in that case.
        def _cfg_get(key: str) -> str:
            try:
                return config_service.get(key) or ""
            except Exception:
                return ""
        self.base_url = base_url or _cfg_get("OPENAI_BASE_URL") or cfg.get("OPENAI_BASE_URL")
        self.api_key = api_key or _cfg_get("OPENAI_API_KEY") or cfg.get("OPENAI_API_KEY")
        self.model = model or _cfg_get("CHAT_MODEL") or cfg.get("CHAT_MODEL") or "gpt-4o-mini"
        self._client = None

    @property
    def client(self):
        if self._client is None:
            try:
                from openai import OpenAI
            except ImportError as e:  # pragma: no cover
                raise RuntimeError("openai SDK 未安装") from e
            self._client = OpenAI(base_url=self.base_url, api_key=self.api_key or "sk-placeholder")
        return self._client

    def chat(self, system: str, user: str, *, temperature: float = 0.4,
             response_format: dict | None = None) -> str:
        kwargs = dict(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=temperature,
        )
        if response_format:
            kwargs["response_format"] = response_format
        resp = self.client.chat.completions.create(**kwargs)
        return resp.choices[0].message.content or ""

    def chat_with_image(self, prompt: str, image_data_url: str, *,
                        temperature: float = 0.2) -> str:
        """多模态调用：传入 data: URL 的图片（OpenAI vision 兼容接口）。

        调用者需保证 self.model 是支持 vision 的型号（如 qwen-vl-plus / gpt-4o）。
        """
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": image_data_url}},
                ],
            }],
            temperature=temperature,
        )
        return resp.choices[0].message.content or ""


# ---------------------------------------------------------------------------
# Wiki Builder
# ---------------------------------------------------------------------------

WIKI_SYSTEM_PROMPT = """你是 Karpathy LLM Wiki 风格的个人知识库编辑助手。核心原则：
1. 一篇原始文档可能包含多个独立概念，请拆分为多个 wiki 条目，每个条目只聊一个概念（原子化）。
2. 对只讲一个主题的短文档，输出 1 个条目即可；长文可以拆 2~6 个。
3. 每个条目的 title 要是可被双链复用的“概念名/术语名”，不要带文档原始标题前缀。
4. aliases 必须列出常见同义词/缩写/中英文对照，用于后续概念去重。
5. 正文使用 [[相关条目标题]] 标注与其它概念的关联，可推断但不要编造事实。
6. 末尾 Related Notes 列出 2~6 个 [[相关概念]]。
7. 严格输出 JSON，不要包装 markdown 代码块。
"""


WIKI_USER_TEMPLATE = """请将下面这篇用户原始文档重写为 1 到多条 wiki 条目（原子化拆分不同概念）。

原始标题：{title}
原始内容（markdown / 纯文本）：
---
{content}
---

请严格按以下 JSON 结构返回（articles 必为数组）：
{{
  "articles": [
    {{
      "title": "概念名（可作为双链错）",
      "aliases": ["同义词1", "缩写", "英文名"],
      "summary": "一句话概述",
      "tags": ["tag1", "tag2"],
      "content_md": "正文 markdown，可包含小节/列表/代码块；可使用 [[相关条目]] 引用其它概念",
      "related": ["相关概念1", "相关概念2"]
    }}
  ]
}}"""


@dataclass
class WikiArticleDraft:
    title: str
    aliases: list[str]
    summary: str
    tags: list[str]
    content_md: str
    related: list[str]


def _safe_json_loads(text: str) -> dict:
    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # try to grab first JSON object
        match = re.search(r"\{[\s\S]*\}", text)
        if match:
            return json.loads(match.group(0))
        raise


def build_articles_from_text(llm: LLMClient, *, title: str, raw_text: str) -> list[WikiArticleDraft]:
    """通用抽取：给定标题 + 纯文本 → 1~N 个 wiki 条目。"""
    raw = (raw_text or "")[:8000]
    user_msg = WIKI_USER_TEMPLATE.format(title=title or "未命名", content=raw or "(空)")
    text = llm.chat(WIKI_SYSTEM_PROMPT, user_msg, temperature=0.3,
                    response_format={"type": "json_object"})
    data = _safe_json_loads(text)
    items = data.get("articles")
    if not items and isinstance(data, dict) and data.get("title"):
        items = [data]
    if not items:
        raise RuntimeError("LLM 未返回有效的 wiki 条目")
    drafts: list[WikiArticleDraft] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        t = (item.get("title") or "").strip()
        if not t:
            continue
        drafts.append(WikiArticleDraft(
            title=t,
            aliases=[str(x).strip() for x in (item.get("aliases") or []) if str(x).strip()],
            summary=(item.get("summary") or "").strip(),
            tags=[str(x).strip().lstrip("#") for x in (item.get("tags") or []) if str(x).strip()],
            content_md=(item.get("content_md") or "").strip(),
            related=[str(x).strip() for x in (item.get("related") or []) if str(x).strip()],
        ))
    if not drafts:
        raise RuntimeError("LLM 返回的条目全部为空")
    return drafts


def build_articles_from_document(llm: LLMClient, doc: Document) -> list[WikiArticleDraft]:
    """Karpathy 式原子化抽取：一篇源文档 → 1~N 个 wiki 条目。"""
    raw = doc.plain_text or extract_markdown(doc.content_json or "") or ""
    return build_articles_from_text(llm, title=doc.title or "未命名", raw_text=raw)


# Backwards-compat single-article helper (still used by regenerate_one_async)
def build_article_from_document(llm: LLMClient, doc: Document) -> WikiArticleDraft:
    drafts = build_articles_from_document(llm, doc)
    return drafts[0]


def _slug_for(title: str, ai_kb_id: str) -> str:
    base = slugify(title or "untitled", lowercase=True, max_length=80) or "untitled"
    candidate = base
    n = 2
    while AIKBArticle.query.filter_by(ai_kb_id=ai_kb_id, slug=candidate).first():
        candidate = f"{base}-{n}"
        n += 1
    return candidate


def _frontmatter(article: AIKBArticle) -> str:
    tags = json.loads(article.tags_json or "[]") or []
    fm = [
        "---",
        f"title: {article.title}",
        f"slug: {article.slug}",
        f"summary: {article.summary or ''}",
        f"tags: [{', '.join(tags)}]",
        f"created: {article.created_at.isoformat() if article.created_at else ''}",
        f"updated: {article.updated_at.isoformat() if article.updated_at else ''}",
        "---",
        "",
    ]
    return "\n".join(fm)


def _wiki_dir(ai_kb: AIKnowledgeBase) -> Path:
    base = Path(current_app.config["AI_WIKI_DIR"]) / str(ai_kb.id)
    base.mkdir(parents=True, exist_ok=True)
    return base


def _write_article_file(ai_kb: AIKnowledgeBase, article: AIKBArticle) -> None:
    path = _wiki_dir(ai_kb) / f"{article.slug}.md"
    body = _frontmatter(article) + (article.content_md or "")
    if (article.content_md or "") and "## Related Notes" not in (article.content_md or ""):
        body += "\n"
    path.write_text(body, encoding="utf-8")


def _find_existing_article(ai_kb_id: str, draft: WikiArticleDraft) -> AIKBArticle | None:
    """跨文档概念合并查找：依次按
    1) title 精确匹配
    2) title 大小写忽略匹配
    3) draft.title 命中某个现有条目的 alias
    4) draft.aliases 中任一项命中某个现有条目的 title/alias
    """
    title = (draft.title or "").strip()
    if not title:
        return None
    # 1) 精确 title
    hit = AIKBArticle.query.filter_by(ai_kb_id=ai_kb_id, title=title).first()
    if hit:
        return hit
    # 全量扫（个人知识库量级较小，不设索引成本可接受）
    title_lc = title.lower()
    new_alias_set = {a.lower() for a in draft.aliases if a}
    new_alias_set.add(title_lc)
    for art in AIKBArticle.query.filter_by(ai_kb_id=ai_kb_id).all():
        # 2) title 大小写忽略
        if (art.title or "").lower() == title_lc:
            return art
        # 3) + 4) alias 交集
        try:
            art_aliases = {str(a).lower() for a in json.loads(art.aliases_json or "[]") if a}
        except Exception:
            art_aliases = set()
        art_aliases.add((art.title or "").lower())
        if new_alias_set & art_aliases:
            return art
    return None


def _merge_content(old_md: str, new_md: str, source_title: str) -> str:
    """概念合并：保留原正文，追加「补充从 <源>」小节。"""
    old = (old_md or "").rstrip()
    new = (new_md or "").strip()
    if not new:
        return old
    if not old:
        return new
    # 如果新内容完全被旧内容包含，跳过
    if new in old:
        return old
    header = f"\n\n## 补充来源：{source_title}\n\n"
    return old + header + new


def upsert_article(ai_kb: AIKnowledgeBase, draft: WikiArticleDraft, source_doc_id: str,
                   source_title: str = "") -> AIKBArticle:
    article = _find_existing_article(ai_kb.id, draft)
    if article:
        # 概念合并：aliases / tags / sources 取并集；content 追加；summary 保留较长者
        try:
            old_aliases = set(json.loads(article.aliases_json or "[]"))
        except Exception:
            old_aliases = set()
        # 原 title 与新 title 不一致时，把新 title 也存为别名，以便后续双链解析
        if draft.title and draft.title != article.title:
            old_aliases.add(draft.title)
        old_aliases.update(draft.aliases or [])
        # 过滤掉与 title 重复的别名
        old_aliases = {a for a in old_aliases if a and a != article.title}
        article.aliases_json = json.dumps(sorted(old_aliases), ensure_ascii=False)

        try:
            old_tags = set(json.loads(article.tags_json or "[]"))
        except Exception:
            old_tags = set()
        old_tags.update(draft.tags or [])
        article.tags_json = json.dumps(sorted(old_tags), ensure_ascii=False)

        if draft.summary and len(draft.summary) > len(article.summary or ""):
            article.summary = draft.summary

        article.content_md = _merge_content(article.content_md or "", draft.content_md or "",
                                            source_title or "原文档")

        try:
            srcs = json.loads(article.source_doc_ids_json or "[]")
        except Exception:
            srcs = []
        if source_doc_id not in srcs:
            srcs.append(source_doc_id)
        article.source_doc_ids_json = json.dumps(srcs)
    else:
        slug = _slug_for(draft.title, ai_kb.id)
        article = AIKBArticle(
            ai_kb_id=ai_kb.id,
            title=draft.title,
            slug=slug,
            summary=draft.summary,
            tags_json=json.dumps(draft.tags, ensure_ascii=False),
            aliases_json=json.dumps(draft.aliases, ensure_ascii=False),
            content_md=draft.content_md,
            source_doc_ids_json=json.dumps([source_doc_id]),
        )
        db.session.add(article)
    db.session.commit()
    _write_article_file(ai_kb, article)
    return article


# ---------------------------------------------------------------------------
# Wiki link resolver
# ---------------------------------------------------------------------------

def _build_alias_index(ai_kb_id: str) -> dict[str, AIKBArticle]:
    index: dict[str, AIKBArticle] = {}
    for art in AIKBArticle.query.filter_by(ai_kb_id=ai_kb_id).all():
        index[art.title.lower()] = art
        index[art.slug.lower()] = art
        try:
            for a in json.loads(art.aliases_json or "[]"):
                if a:
                    index[str(a).lower()] = art
        except Exception:
            pass
    return index


def resolve_links(ai_kb: AIKnowledgeBase) -> tuple[int, int]:
    """Scan all articles' [[...]] placeholders and rebuild ai_kb_links.

    Returns (resolved_count, redlink_count).
    """
    AIKBLink.query.filter_by(ai_kb_id=ai_kb.id).delete()
    db.session.commit()

    index = _build_alias_index(ai_kb.id)
    resolved = 0
    red = 0
    articles = AIKBArticle.query.filter_by(ai_kb_id=ai_kb.id).all()
    for art in articles:
        for target in collect_wikilinks(art.content_md or ""):
            target_art = index.get(target.lower())
            link = AIKBLink(
                ai_kb_id=ai_kb.id,
                from_article_id=art.id,
                to_article_id=target_art.id if target_art else None,
                anchor_text=target,
            )
            db.session.add(link)
            if target_art:
                resolved += 1
            else:
                red += 1
    db.session.commit()
    return resolved, red


def article_resolver(ai_kb_id: str):
    """Return a callable mapping a wiki target -> article slug or None."""
    index = _build_alias_index(ai_kb_id)

    def _resolve(target: str) -> str | None:
        art = index.get((target or "").lower())
        return art.slug if art else None

    return _resolve


# ---------------------------------------------------------------------------
# Async build pipeline
# ---------------------------------------------------------------------------

def _process_one_source(llm: LLMClient, ai_kb: AIKnowledgeBase, src: AIKBSource) -> None:
    from ..models import AIKBSourceKind
    from ..utils.extract_upload import extract_text_from_upload

    src.status = AIKBSourceStatus.PROCESSING.value
    src.err_msg = ""
    db.session.commit()
    try:
        if src.kind == AIKBSourceKind.UPLOAD.value:
            # 外部上传件：先抽取为纯文本，再走通用 wiki 化
            up_path = src.upload_path or ""
            if not up_path:
                raise RuntimeError("上传文件路径丢失")
            full_path = str(Path(current_app.instance_path) / up_path) if not Path(up_path).is_absolute() else up_path
            raw = extract_text_from_upload(full_path, src.upload_filename or up_path, llm=llm)
            drafts = build_articles_from_text(llm, title=src.upload_filename or "上传文档", raw_text=raw)
            # 上传件没有 doc_id，用 "upload:<source_id>" 作为 source_doc_id 标识以避免空值
            for d in drafts:
                upsert_article(ai_kb, d, source_doc_id=f"upload:{src.id}",
                               source_title=src.upload_filename or "上传文档")
        else:
            doc = src.document
            if doc is None or doc.is_deleted:
                raise RuntimeError("源文档不存在或已被删除")
            raw = doc.plain_text or extract_markdown(doc.content_json or "") or ""
            if not raw.strip():
                raise RuntimeError("源文档内容为空，无法生成 Wiki 条目")
            drafts = build_articles_from_document(llm, doc)
            for d in drafts:
                upsert_article(ai_kb, d, source_doc_id=doc.id, source_title=doc.title or "原文档")
        src.status = AIKBSourceStatus.PROCESSED.value
    except Exception as e:
        src.status = AIKBSourceStatus.FAILED.value
        src.err_msg = str(e)[:480]
    db.session.commit()


def build_wiki_async(app, ai_kb_id: str, *, only_pending: bool = True) -> None:
    """Run the full wiki build inside a background thread."""
    import logging
    logger = logging.getLogger(__name__)

    def _job():
        with app.app_context():
            ai_kb = db.session.get(AIKnowledgeBase, ai_kb_id)
            if not ai_kb:
                return
            ai_kb.status = AIKBStatus.BUILDING.value
            ai_kb.error_msg = ""
            db.session.commit()
            try:
                model = (ai_kb.chat_model or "").strip() or None
                api_key = current_app.config.get("OPENAI_API_KEY") or ""
                # 也查一下 DB 配置（用户可能只在系统设置里填了 key）
                if not api_key:
                    try:
                        from . import config_service
                        api_key = config_service.get("OPENAI_API_KEY") or ""
                    except Exception:
                        pass
                if not api_key:
                    raise RuntimeError(
                        "OPENAI_API_KEY 未配置，请在系统设置中配置 API 密钥"
                    )
                llm = LLMClient(model=model)
                logger.info("build_wiki start: ai_kb=%s model=%s", ai_kb_id, llm.model)
                q = AIKBSource.query.filter_by(ai_kb_id=ai_kb.id)
                if only_pending:
                    q = q.filter(AIKBSource.status.in_([
                        AIKBSourceStatus.PENDING.value,
                        AIKBSourceStatus.FAILED.value,
                    ]))
                sources = q.all()
                if not sources:
                    ai_kb.status = AIKBStatus.READY.value
                    ai_kb.error_msg = "没有待处理的源文档"
                    db.session.commit()
                    return
                for src in sources:
                    _process_one_source(llm, ai_kb, src)
                resolve_links(ai_kb)
                ai_kb.status = AIKBStatus.READY.value
                ai_kb.last_built_at = datetime.utcnow()
                logger.info("build_wiki done: ai_kb=%s", ai_kb_id)
            except Exception as e:
                logger.exception("build_wiki failed: ai_kb=%s", ai_kb_id)
                ai_kb.status = AIKBStatus.FAILED.value
                ai_kb.error_msg = str(e)[:480]
            db.session.commit()

    t = threading.Thread(target=_job, daemon=True)
    t.start()


def regenerate_one_async(app, ai_kb_id: str, article_id: str) -> None:
    def _job():
        with app.app_context():
            ai_kb = db.session.get(AIKnowledgeBase, ai_kb_id)
            article = db.session.get(AIKBArticle, article_id)
            if not ai_kb or not article:
                return
            ai_kb.status = AIKBStatus.BUILDING.value
            db.session.commit()
            try:
                src_ids = json.loads(article.source_doc_ids_json or "[]")
                if not src_ids:
                    raise RuntimeError("缺少源文档")
                doc = db.session.get(Document, src_ids[0])
                if not doc:
                    raise RuntimeError("源文档不存在")
                llm = LLMClient(model=(ai_kb.chat_model or "").strip() or None)
                draft = build_article_from_document(llm, doc)
                # overwrite this article (keep slug)
                article.title = draft.title or article.title
                article.summary = draft.summary
                article.tags_json = json.dumps(draft.tags, ensure_ascii=False)
                article.aliases_json = json.dumps(draft.aliases, ensure_ascii=False)
                article.content_md = draft.content_md
                db.session.commit()
                _write_article_file(ai_kb, article)
                resolve_links(ai_kb)
                ai_kb.status = AIKBStatus.READY.value
                ai_kb.last_built_at = datetime.utcnow()
            except Exception as e:
                ai_kb.status = AIKBStatus.FAILED.value
                ai_kb.error_msg = str(e)[:480]
            db.session.commit()

    threading.Thread(target=_job, daemon=True).start()


# ---------------------------------------------------------------------------
# Optional RAG chat (only when ai_kb.enable_rag=True)
# ---------------------------------------------------------------------------

WIKI_CHAT_SYSTEM = """你是用户个人 wiki 的问答助手。请基于给定的 wiki 条目原文回答问题，并在回答末尾用 “参考：[[Title1]] [[Title2]]” 形式列出引用条目。若 wiki 中没有相关信息，明确说明无法回答。"""


def chat_with_wiki(ai_kb: AIKnowledgeBase, question: str, max_articles: int = 6) -> str:
    """Plain Karpathy-style chat: pick top-N articles by simple keyword overlap and feed full text."""
    articles = AIKBArticle.query.filter_by(ai_kb_id=ai_kb.id).all()
    if not articles:
        return "知识库为空，请先生成 Wiki 条目。"
    q_tokens = set(re.findall(r"[\w\u4e00-\u9fa5]+", (question or "").lower()))

    def score(a: AIKBArticle) -> int:
        text = (a.title + " " + (a.summary or "") + " " + (a.content_md or "")).lower()
        return sum(1 for t in q_tokens if t and t in text)

    ranked = sorted(articles, key=score, reverse=True)[:max_articles]
    context = "\n\n".join(
        f"# {a.title}\n{a.summary or ''}\n\n{(a.content_md or '')[:2000]}" for a in ranked
    )
    llm = LLMClient(model=(ai_kb.chat_model or "").strip() or None)
    return llm.chat(WIKI_CHAT_SYSTEM, f"WIKI 上下文：\n{context}\n\n问题：{question}", temperature=0.2)
