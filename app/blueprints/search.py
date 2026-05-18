"""Search blueprint: global document search API."""
from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user

from ..extensions import db
from ..models import Document, KnowledgeBase, KBMember, KBVisibility

bp = Blueprint("search", __name__)


@bp.route("/search")
@login_required
def search():
    """Search documents the current user can access.

    Query params:
      q  - search keyword (min 2 chars)
      page - page number (default 1)
      size - page size (default 20, max 50)

    Returns JSON:
      { results: [{id, title, type, kb_id, kb_name, snippet, updated_at}], total }
    """
    q = (request.args.get("q") or "").strip()
    page = max(1, request.args.get("page", 1, type=int))
    size = min(50, max(1, request.args.get("size", 20, type=int)))

    if len(q) < 2:
        return jsonify({"results": [], "total": 0})

    like = f"%{q}%"

    # --- Build accessible KB IDs for current user ---
    # 1) Public KBs
    public_kb_ids = (
        db.session.query(KnowledgeBase.id)
        .filter_by(visibility=KBVisibility.PUBLIC.value, is_archived=False)
        .all()
    )
    accessible_kb_ids = {kid for (kid,) in public_kb_ids}

    # 2) KBs owned by user
    owned_kb_ids = (
        db.session.query(KnowledgeBase.id)
        .filter_by(owner_id=current_user.id, is_archived=False)
        .all()
    )
    accessible_kb_ids |= {kid for (kid,) in owned_kb_ids}

    # 3) KBs where user is a member
    member_kb_ids = (
        db.session.query(KBMember.kb_id)
        .filter_by(user_id=current_user.id)
        .all()
    )
    accessible_kb_ids |= {kid for (kid,) in member_kb_ids}

    # Super admin sees everything
    if current_user.is_super_admin:
        all_kb_ids = (
            db.session.query(KnowledgeBase.id)
            .filter_by(is_archived=False)
            .all()
        )
        accessible_kb_ids = {kid for (kid,) in all_kb_ids}

    if not accessible_kb_ids:
        return jsonify({"results": [], "total": 0})

    # --- Query documents ---
    query = (
        Document.query
        .filter(
            Document.is_deleted == False,  # noqa: E712
            Document.kb_id.in_(accessible_kb_ids),
            db.or_(
                Document.title.like(like),
                Document.plain_text.like(like),
            ),
        )
        .order_by(Document.updated_at.desc())
    )

    total = query.count()
    docs = query.offset((page - 1) * size).limit(size).all()

    # Preload KB names
    kb_ids_in_results = {d.kb_id for d in docs}
    kb_map = {}
    if kb_ids_in_results:
        kbs = KnowledgeBase.query.filter(KnowledgeBase.id.in_(kb_ids_in_results)).all()
        kb_map = {kb.id: kb.name for kb in kbs}

    results = []
    for d in docs:
        snippet = _make_snippet(d.plain_text or "", q, max_len=120)
        results.append({
            "id": d.id,
            "title": d.title or "未命名",
            "type": d.type,
            "kb_id": d.kb_id,
            "kb_name": kb_map.get(d.kb_id, ""),
            "snippet": snippet,
            "updated_at": d.updated_at.strftime("%Y-%m-%d %H:%M") if d.updated_at else "",
        })

    return jsonify({"results": results, "total": total})


def _make_snippet(text: str, keyword: str, max_len: int = 120) -> str:
    """Extract a snippet around the first occurrence of keyword."""
    if not text:
        return ""
    lower = text.lower()
    kw_lower = keyword.lower()
    pos = lower.find(kw_lower)
    if pos == -1:
        # Keyword not found in plain_text (matched by title); return beginning
        return text[:max_len] + ("..." if len(text) > max_len else "")

    # Center the snippet around the match
    start = max(0, pos - max_len // 3)
    end = min(len(text), start + max_len)
    snippet = text[start:end]
    if start > 0:
        snippet = "..." + snippet
    if end < len(text):
        snippet = snippet + "..."
    return snippet
