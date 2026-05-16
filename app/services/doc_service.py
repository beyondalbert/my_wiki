"""Document service."""
from __future__ import annotations

from typing import Iterable

from ..extensions import db
from ..models import Document, KnowledgeBase, DocumentType, DocumentPrivacy
from ..utils.outline import extract_plain_text


def list_kb_doc_tree(kb_id: int) -> list[dict]:
    """Return a nested list representation of all (non-deleted) docs in a KB."""
    docs = (
        Document.query.filter_by(kb_id=kb_id, is_deleted=False)
        .order_by(Document.parent_id.is_(None).desc(), Document.sort_order.asc(), Document.id.asc())
        .all()
    )
    by_parent: dict[int | None, list[Document]] = {}
    for d in docs:
        by_parent.setdefault(d.parent_id, []).append(d)

    def build(parent_id):
        items = []
        for d in by_parent.get(parent_id, []):
            items.append({
                "id": d.id,
                "title": d.title or "未命名",
                "type": d.type,
                "privacy": d.privacy,
                "children": build(d.id),
            })
        return items

    return build(None)


def create_document(kb: KnowledgeBase, user, title: str = "未命名", parent_id: int | None = None,
                    doc_type: str = DocumentType.DOC.value,
                    privacy: str = DocumentPrivacy.NORMAL.value) -> Document:
    doc = Document(
        kb_id=kb.id,
        parent_id=parent_id,
        title=title or "未命名",
        type=doc_type,
        privacy=privacy,
        author_id=getattr(user, "id", None),
        content_json="",
        plain_text="",
        sort_order=0,
    )
    db.session.add(doc)
    db.session.commit()
    return doc


def update_content(doc: Document, content_json: str, title: str | None = None) -> Document:
    if title is not None:
        doc.title = title.strip() or "未命名"
    doc.content_json = content_json or ""
    doc.plain_text = extract_plain_text(content_json or "")
    db.session.commit()
    return doc


def soft_delete(doc: Document) -> None:
    doc.is_deleted = True
    db.session.commit()


def collect_descendants(doc_id: int) -> list[int]:
    """Return all descendant doc ids including itself."""
    result = [doc_id]
    queue = [doc_id]
    while queue:
        current = queue.pop()
        children = Document.query.filter_by(parent_id=current, is_deleted=False).all()
        for c in children:
            result.append(c.id)
            queue.append(c.id)
    return result
