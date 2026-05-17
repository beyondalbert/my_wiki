"""Document blueprint."""
import os
from pathlib import Path

from flask import Blueprint, abort, current_app, flash, jsonify, redirect, render_template, request, send_from_directory, session, url_for
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename

from ..extensions import csrf, db
from ..models import Document, DocGroup, KnowledgeBase, DocumentPrivacy, DocumentType, DocumentShare
from ..services import kb_service, doc_service, share_service
from ..utils.ids import generate_id
from ..utils.outline import extract_outline

bp = Blueprint("doc", __name__)


def _get_doc_or_404(doc_id: str) -> Document:
    doc = db.session.get(Document, doc_id)
    if doc is None or doc.is_deleted:
        abort(404)
    return doc


_ALLOWED_IMAGE_EXTS = {"png", "jpg", "jpeg", "gif", "webp", "svg"}


@bp.route("/upload-image", methods=["POST"])
@csrf.exempt          # AJAX FormData 上传，login_required 已提供保护
@login_required
def upload_image():
    """接收编辑器上传的图片，保存到 UPLOAD_DIR/images/ 并返回可访问 URL。"""
    file = request.files.get("image")
    if not file or not file.filename:
        return jsonify({"error": "未选择文件"}), 400
    ext = (file.filename.rsplit(".", 1)[-1] if "." in file.filename else "").lower()
    if ext not in _ALLOWED_IMAGE_EXTS:
        return jsonify({"error": f"不支持的图片格式（仅 {', '.join(sorted(_ALLOWED_IMAGE_EXTS))}）"}), 400
    filename = f"{generate_id(16)}.{ext}"
    upload_dir = Path(current_app.config["UPLOAD_DIR"]) / "images"
    upload_dir.mkdir(parents=True, exist_ok=True)
    file.save(str(upload_dir / filename))
    url = url_for("doc.uploaded_image", filename=filename)
    return jsonify({"url": url})


@bp.route("/uploads/images/<filename>")
def uploaded_image(filename):
    """Serve 上传的图片文件。"""
    upload_dir = Path(current_app.config["UPLOAD_DIR"]) / "images"
    safe_name = secure_filename(filename)
    if not safe_name or not (upload_dir / safe_name).is_file():
        abort(404)
    return send_from_directory(str(upload_dir), safe_name)


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
    group_id = (request.form.get("group_id") or "").strip() or None
    doc_type = request.form.get("type") or DocumentType.DOC.value
    if doc_type not in {t.value for t in DocumentType}:
        doc_type = DocumentType.DOC.value
    privacy = request.form.get("privacy") or DocumentPrivacy.NORMAL.value
    if privacy not in {p.value for p in DocumentPrivacy}:
        privacy = DocumentPrivacy.NORMAL.value
    title = (request.form.get("title") or "未命名").strip()
    doc = doc_service.create_document(kb, current_user, title=title, parent_id=parent_id,
                                      doc_type=doc_type, privacy=privacy, group_id=group_id)
    return redirect(url_for("doc.edit", doc_id=doc.id))


@bp.route("/<doc_id>")
def view(doc_id):
    doc = _get_doc_or_404(doc_id)
    kb = doc.kb
    if not kb_service.can_access(current_user, kb):
        abort(403)
    if kb_service.requires_unlock(current_user, kb, session):
        return redirect(url_for("kb.unlock", kb_id=kb.id, next=request.path))
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
    groups = DocGroup.query.filter_by(kb_id=kb.id).order_by(DocGroup.sort_order.asc(), DocGroup.created_at.asc()).all()
    return render_template("doc/edit.html", doc=doc, kb=kb, tree=tree, groups=groups)


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
    # 分组设置
    if "group_id" in payload:
        gid = (payload["group_id"] or "").strip() or None
        if gid:
            grp = DocGroup.query.filter_by(id=gid, kb_id=kb.id).first()
            if grp:
                doc.group_id = gid
        else:
            doc.group_id = None
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
