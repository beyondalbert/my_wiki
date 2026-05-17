"""Document blueprint."""
from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, url_for
from flask_login import login_required, current_user

from ..extensions import db
from ..models import Document, KnowledgeBase, DocumentPrivacy, DocumentType, DocumentShare
from ..services import kb_service, doc_service, share_service
from ..utils.outline import extract_outline

bp = Blueprint("doc", __name__)


def _get_doc_or_404(doc_id: str) -> Document:
    doc = db.session.get(Document, doc_id)
    if doc is None or doc.is_deleted:
        abort(404)
    return doc


@bp.route("/new", methods=["POST"])
@login_required
def new_doc():
    kb_id = (request.form.get("kb_id") or request.args.get("kb_id") or "").strip()
    if not kb_id:
        abort(404)
    kb = db.session.get(KnowledgeBase, kb_id)
    if not kb:
        abort(404)
    if not kb_service.can_edit(current_user, kb):
        abort(403)
    parent_id = (request.form.get("parent_id") or "").strip() or None
    doc_type = request.form.get("type") or DocumentType.DOC.value
    if doc_type not in {t.value for t in DocumentType}:
        doc_type = DocumentType.DOC.value
    privacy = request.form.get("privacy") or DocumentPrivacy.NORMAL.value
    if privacy not in {p.value for p in DocumentPrivacy}:
        privacy = DocumentPrivacy.NORMAL.value
    title = (request.form.get("title") or "未命名").strip()
    doc = doc_service.create_document(kb, current_user, title=title, parent_id=parent_id,
                                      doc_type=doc_type, privacy=privacy)
    return redirect(url_for("doc.edit", doc_id=doc.id))


@bp.route("/<doc_id>")
def view(doc_id):
    doc = _get_doc_or_404(doc_id)
    kb = doc.kb
    if not kb_service.can_access(current_user, kb):
        abort(403)
    tree = doc_service.list_kb_doc_tree(kb.id)
    outline = extract_outline(doc.content_json)
    return render_template(
        "doc/view.html", doc=doc, kb=kb, tree=tree, outline=outline,
        can_edit=kb_service.can_edit(current_user, kb),
        can_manage=kb_service.can_manage(current_user, kb),
    )


@bp.route("/<doc_id>/edit")
@login_required
def edit(doc_id):
    doc = _get_doc_or_404(doc_id)
    kb = doc.kb
    if not kb_service.can_edit(current_user, kb):
        abort(403)
    tree = doc_service.list_kb_doc_tree(kb.id)
    return render_template("doc/edit.html", doc=doc, kb=kb, tree=tree)


@bp.route("/<doc_id>/save", methods=["POST"])
@login_required
def save(doc_id):
    doc = _get_doc_or_404(doc_id)
    kb = doc.kb
    if not kb_service.can_edit(current_user, kb):
        abort(403)
    payload = request.get_json(silent=True) or {}
    title = payload.get("title")
    content_json = payload.get("content_json")
    privacy = payload.get("privacy")
    if privacy in {p.value for p in DocumentPrivacy}:
        doc.privacy = privacy
    doc_service.update_content(doc, content_json or "", title=title)
    outline = extract_outline(doc.content_json)
    return jsonify({"ok": True, "outline": outline, "updated_at": doc.updated_at.isoformat()})


@bp.route("/<doc_id>/delete", methods=["POST"])
@login_required
def delete(doc_id):
    doc = _get_doc_or_404(doc_id)
    kb = doc.kb
    if not kb_service.can_edit(current_user, kb):
        abort(403)
    for desc_id in doc_service.collect_descendants(doc.id):
        d = db.session.get(Document, desc_id)
        if d:
            d.is_deleted = True
    db.session.commit()
    flash("文档已删除", "info")
    return redirect(url_for("kb.detail", kb_id=kb.id))


@bp.route("/<doc_id>/share", methods=["GET", "POST"])
@login_required
def share(doc_id):
    doc = _get_doc_or_404(doc_id)
    kb = doc.kb
    if not kb_service.can_edit(current_user, kb):
        abort(403)
    if not doc.can_be_shared:
        flash("私密文档不可分享，请先在编辑页将类型改为常规", "warning")
        return redirect(url_for("doc.view", doc_id=doc.id))
    if request.method == "POST":
        password = request.form.get("password") or None
        ttl_hours = request.form.get("ttl_hours")
        ttl = int(ttl_hours) if ttl_hours and ttl_hours.isdigit() else None
        try:
            new_share = share_service.create_share(doc, current_user.id, password=password, ttl_hours=ttl)
            flash("分享链接已生成", "success")
        except share_service.ShareError as e:
            flash(str(e), "error")
        return redirect(url_for("doc.share", doc_id=doc.id))
    shares = doc.shares.order_by(DocumentShare.created_at.desc()).all()
    return render_template("doc/share.html", doc=doc, shares=shares)


@bp.route("/share/<int:share_id>/revoke", methods=["POST"])
@login_required
def revoke_share(share_id):
    s = db.session.get(DocumentShare, share_id)
    if not s:
        abort(404)
    doc = s.document
    if not kb_service.can_edit(current_user, doc.kb):
        abort(403)
    share_service.revoke(s)
    flash("分享已撤销", "info")
    return redirect(url_for("doc.share", doc_id=doc.id))
