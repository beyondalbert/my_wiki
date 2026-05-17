"""Document service."""
from __future__ import annotations

from typing import Iterable

from ..extensions import db
from ..models import Document, DocGroup, KnowledgeBase, DocumentType, DocumentPrivacy
from ..utils.outline import extract_plain_text


def list_kb_doc_tree(kb_id: str) -> list[dict]:
    """Return grouped doc tree: [{group info, docs: [...]}, ...]

    Structure returned:
    [
        {"group": None, "docs": [doc_nodes...]},   # ungrouped docs
        {"group": {"id":..., "name":...}, "docs": [doc_nodes...]},
        ...
    ]
    Each doc_node = {"id", "title", "type", "privacy", "children": [...]}
    """
    docs = (
        Document.query.filter_by(kb_id=kb_id, is_deleted=False)
        .order_by(Document.sort_order.asc(), Document.id.asc())
        .all()
    )
    groups = (
        DocGroup.query.filter_by(kb_id=kb_id)
        .order_by(DocGroup.sort_order.asc(), DocGroup.created_at.asc())
        .all()
    )

    # Build per-group buckets
    group_map = {g.id: g for g in groups}
    docs_by_group: dict[str | None, list[Document]] = {None: []}
    for g in groups:
        docs_by_group[g.id] = []
    for d in docs:
        gid = d.group_id if d.group_id in group_map else None
        docs_by_group.setdefault(gid, []).append(d)

    def _build_tree(doc_list: list[Document]) -> list[dict]:
        by_parent: dict[str | None, list[Document]] = {}
        for d in doc_list:
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

    result = []
    # Ungrouped docs always present (as drop target even if empty)
    ungrouped = docs_by_group.get(None, [])
    result.append({"group": None, "docs": _build_tree(ungrouped)})
    # Then each group
    for g in groups:
        gdocs = docs_by_group.get(g.id, [])
        result.append({
            "group": {"id": g.id, "name": g.name},
            "docs": _build_tree(gdocs),
        })

    return result


def list_kb_doc_flat(kb_id: str) -> list[Document]:
    """Return flat list of non-deleted docs in a KB (for backward compat)."""
    return (
        Document.query.filter_by(kb_id=kb_id, is_deleted=False)
        .order_by(Document.sort_order.asc(), Document.id.asc())
        .all()
    )


def create_document(kb: KnowledgeBase, user, title: str = "未命名", parent_id: str | None = None,
                    doc_type: str = DocumentType.DOC.value,
                    privacy: str = DocumentPrivacy.NORMAL.value,
                    group_id: str | None = None) -> Document:
    doc = Document(
        kb_id=kb.id,
        parent_id=parent_id,
        group_id=group_id,
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


def collect_descendants(doc_id: str) -> list[str]:
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
