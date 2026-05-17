"""Knowledge Base blueprint."""
from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, session, url_for
from flask_login import login_required, current_user

from ..extensions import db
from ..models import (
    KnowledgeBase, KBMember, KBVisibility, KBMemberRole, User, Document
)
from ..services import kb_service, doc_service

bp = Blueprint("kb", __name__)


def _get_kb_or_404(kb_id: str) -> KnowledgeBase:
    kb = db.session.get(KnowledgeBase, kb_id)
    if kb is None or kb.is_archived:
        abort(404)
    return kb


@bp.route("/")
@login_required
def list_kbs():
    tab = request.args.get("tab", "mine")
    if tab == "public":
        kbs = kb_service.list_public_kbs().all()
    else:
        kbs = kb_service.list_my_kbs(current_user).all()
    return render_template("kb/list.html", kbs=kbs, tab=tab)


@bp.route("/new", methods=["GET", "POST"])
@login_required
def new_kb():
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        description = (request.form.get("description") or "").strip()
        visibility = request.form.get("visibility") or KBVisibility.PRIVATE.value
        if visibility not in {v.value for v in KBVisibility}:
            visibility = KBVisibility.PRIVATE.value
        if not name:
            flash("请输入知识库名称", "error")
            return render_template("kb/new.html", form=request.form)
        kb = KnowledgeBase(
            name=name, description=description,
            visibility=visibility, owner_id=current_user.id,
            icon=request.form.get("icon") or "book",
        )
        db.session.add(kb)
        db.session.commit()
        flash("知识库已创建", "success")
        return redirect(url_for("kb.detail", kb_id=kb.id))
    return render_template("kb/new.html", form={})


@bp.route("/<kb_id>")
def detail(kb_id):
    kb = _get_kb_or_404(kb_id)
    if not kb_service.can_access(current_user, kb):
        abort(403)
    if kb_service.requires_unlock(current_user, kb, session):
        return redirect(url_for("kb.unlock", kb_id=kb.id, next=request.path))
    tree = doc_service.list_kb_doc_tree(kb.id)
    # Default open first doc if any
    first_doc = (
        Document.query.filter_by(kb_id=kb.id, is_deleted=False)
        .order_by(Document.parent_id.is_(None).desc(), Document.sort_order.asc(), Document.id.asc())
        .first()
    )
    return render_template(
        "kb/detail.html", kb=kb, tree=tree, first_doc=first_doc,
        can_edit=kb_service.can_edit(current_user, kb),
        can_manage=kb_service.can_manage(current_user, kb),
    )


@bp.route("/<kb_id>/edit", methods=["GET", "POST"])
@login_required
def edit_kb(kb_id):
    kb = _get_kb_or_404(kb_id)
    if not kb_service.can_manage(current_user, kb):
        abort(403)
    if request.method == "POST":
        kb.name = (request.form.get("name") or kb.name).strip()
        kb.description = (request.form.get("description") or "").strip()
        v = request.form.get("visibility")
        if v in {x.value for x in KBVisibility}:
            kb.visibility = v
        kb.icon = request.form.get("icon") or kb.icon
        # 访问密码：仅公开知识库生效
        if kb.is_public:
            new_pwd = (request.form.get("access_password") or "").strip()
            if request.form.get("clear_access_password") == "1":
                kb.set_access_password(None)
            elif new_pwd:
                kb.set_access_password(new_pwd)
        else:
            # 非公开 → 自动清除旧密码，避免后续转回 public 时遗留
            kb.set_access_password(None)
        db.session.commit()
        flash("已保存", "success")
        return redirect(url_for("kb.detail", kb_id=kb.id))
    return render_template("kb/edit.html", kb=kb)


@bp.route("/<kb_id>/unlock", methods=["GET", "POST"])
def unlock(kb_id):
    kb = _get_kb_or_404(kb_id)
    if not kb_service.can_access(current_user, kb):
        abort(403)
    # 已豁免或未设密码 → 直接跳回
    if not kb_service.requires_unlock(current_user, kb, session):
        return redirect(url_for("kb.detail", kb_id=kb.id))
    next_url = request.args.get("next") or url_for("kb.detail", kb_id=kb.id)
    if request.method == "POST":
        password = (request.form.get("password") or "").strip()
        if kb.check_access_password(password) and password:
            kb_service.mark_unlocked(session, kb)
            return redirect(next_url)
        flash("访问密码错误", "error")
    return render_template("kb/unlock.html", kb=kb, next_url=next_url)


@bp.route("/<kb_id>/delete", methods=["POST"])
@login_required
def delete_kb(kb_id):
    kb = _get_kb_or_404(kb_id)
    if not kb_service.can_manage(current_user, kb):
        abort(403)
    kb.is_archived = True
    db.session.commit()
    flash("知识库已归档", "info")
    return redirect(url_for("kb.list_kbs"))


@bp.route("/<kb_id>/members", methods=["GET", "POST"])
@login_required
def members(kb_id):
    kb = _get_kb_or_404(kb_id)
    if not kb_service.can_manage(current_user, kb):
        abort(403)
    if request.method == "POST":
        login_value = (request.form.get("user") or "").strip()
        role = request.form.get("role") or KBMemberRole.VIEWER.value
        if role not in {r.value for r in KBMemberRole}:
            role = KBMemberRole.VIEWER.value
        user = User.query.filter((User.username == login_value) | (User.email == login_value)).first()
        if not user:
            flash("用户不存在", "error")
        elif user.id == kb.owner_id:
            flash("无需添加 owner 自己", "warning")
        else:
            kb_service.add_member(kb, user, role=role)
            flash(f"已添加成员 {user.username}", "success")
        return redirect(url_for("kb.members", kb_id=kb.id))
    members_ = (
        KBMember.query.filter_by(kb_id=kb.id).all()
    )
    return render_template("kb/members.html", kb=kb, members=members_)


@bp.route("/<kb_id>/members/<int:user_id>/delete", methods=["POST"])
@login_required
def remove_member(kb_id, user_id):
    kb = _get_kb_or_404(kb_id)
    if not kb_service.can_manage(current_user, kb):
        abort(403)
    kb_service.remove_member(kb, user_id)
    flash("已移除成员", "info")
    return redirect(url_for("kb.members", kb_id=kb.id))
