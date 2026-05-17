"""Admin (super admin) blueprint."""
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

from ..extensions import db
from ..models import (
    User, Role, Permission, KnowledgeBase, KBVisibility,
    Document, DocumentPrivacy,
)
from ..utils.pagination import get_page_args

bp = Blueprint("admin", __name__)


@bp.before_request
def _guard():
    from flask import redirect as _redirect, url_for as _url_for, request as _req
    if not current_user.is_authenticated:
        return _redirect(_url_for("auth.login", next=_req.path))
    if not getattr(current_user, "is_super_admin", False):
        abort(403)


@bp.route("/")
def index():
    stats = {
        "users": User.query.count(),
        "kbs": KnowledgeBase.query.filter_by(is_archived=False).count(),
        "public_kbs": KnowledgeBase.query.filter_by(visibility=KBVisibility.PUBLIC.value, is_archived=False).count(),
        "docs": Document.query.filter_by(is_deleted=False).count(),
        "admins": User.query.filter_by(is_super_admin=True).count(),
    }
    return render_template("admin/index.html", stats=stats)


# ---------- Users ----------

@bp.route("/users")
def users():
    page, size = get_page_args()
    q = (request.args.get("q") or "").strip()
    query = User.query
    if q:
        like = f"%{q}%"
        query = query.filter((User.username.ilike(like)) | (User.email.ilike(like)))
    pager = query.order_by(User.id.desc()).paginate(page=page, per_page=size, error_out=False)
    return render_template("admin/users.html", pager=pager, q=q)


@bp.route("/users/<int:user_id>/toggle-active", methods=["POST"])
def toggle_active(user_id):
    user = db.session.get(User, user_id)
    if not user:
        abort(404)
    if user.id == current_user.id:
        flash("不能停用自己", "warning")
    else:
        user.is_active = not user.is_active
        db.session.commit()
        flash("已更新用户状态", "success")
    return redirect(url_for("admin.users"))


@bp.route("/users/<int:user_id>/reset-password", methods=["POST"])
def reset_password(user_id):
    user = db.session.get(User, user_id)
    if not user:
        abort(404)
    new_pwd = request.form.get("new_password") or "Mywiki@123"
    user.set_password(new_pwd)
    db.session.commit()
    flash(f"已重置 {user.username} 密码为：{new_pwd}", "success")
    return redirect(url_for("admin.users"))


@bp.route("/users/<int:user_id>/roles", methods=["POST"])
def assign_roles(user_id):
    user = db.session.get(User, user_id)
    if not user:
        abort(404)
    role_ids = request.form.getlist("role_ids")
    user.roles = Role.query.filter(Role.id.in_([int(x) for x in role_ids if x.isdigit()])).all()
    db.session.commit()
    flash("角色已更新", "success")
    return redirect(url_for("admin.users"))


# ---------- Roles & Permissions ----------

@bp.route("/roles", methods=["GET", "POST"])
def roles():
    if request.method == "POST":
        code = (request.form.get("code") or "").strip()
        name = (request.form.get("name") or "").strip()
        if code and name:
            if not Role.query.filter_by(code=code).first():
                db.session.add(Role(code=code, name=name, description=request.form.get("description") or ""))
                db.session.commit()
                flash("已新增角色", "success")
            else:
                flash("角色 code 已存在", "warning")
        return redirect(url_for("admin.roles"))
    roles_ = Role.query.order_by(Role.id.asc()).all()
    perms = Permission.query.order_by(Permission.id.asc()).all()
    return render_template("admin/roles.html", roles=roles_, perms=perms)


@bp.route("/roles/<int:role_id>/permissions", methods=["POST"])
def role_permissions(role_id):
    role = db.session.get(Role, role_id)
    if not role:
        abort(404)
    perm_ids = request.form.getlist("permission_ids")
    role.permissions = Permission.query.filter(Permission.id.in_([int(x) for x in perm_ids if x.isdigit()])).all()
    db.session.commit()
    flash("已更新角色权限", "success")
    return redirect(url_for("admin.roles"))


@bp.route("/roles/<int:role_id>/delete", methods=["POST"])
def delete_role(role_id):
    role = db.session.get(Role, role_id)
    if not role:
        abort(404)
    if role.is_system:
        flash("内置角色不可删除", "warning")
    else:
        db.session.delete(role)
        db.session.commit()
        flash("角色已删除", "info")
    return redirect(url_for("admin.roles"))


@bp.route("/roles/<int:role_id>/edit", methods=["POST"])
def edit_role(role_id):
    role = db.session.get(Role, role_id)
    if not role:
        abort(404)
    if role.is_system:
        flash("内置角色不可修改", "warning")
        return redirect(url_for("admin.roles"))
    name = (request.form.get("name") or "").strip()
    description = (request.form.get("description") or "").strip()
    if not name:
        flash("角色名称不能为空", "error")
        return redirect(url_for("admin.roles"))
    role.name = name
    role.description = description
    db.session.commit()
    flash("角色已更新", "success")
    return redirect(url_for("admin.roles"))


@bp.route("/permissions", methods=["POST"])
def new_permission():
    code = (request.form.get("code") or "").strip()
    name = (request.form.get("name") or "").strip()
    description = (request.form.get("description") or "").strip()
    if not code or not name:
        flash("权限 code 和名称不能为空", "error")
    elif Permission.query.filter_by(code=code).first():
        flash("权限 code 已存在", "warning")
    else:
        db.session.add(Permission(code=code, name=name, description=description))
        db.session.commit()
        flash("已新增权限项", "success")
    return redirect(url_for("admin.roles"))


@bp.route("/permissions/<int:perm_id>/delete", methods=["POST"])
def delete_permission(perm_id):
    perm = db.session.get(Permission, perm_id)
    if not perm:
        abort(404)
    db.session.delete(perm)
    db.session.commit()
    flash("权限项已删除", "info")
    return redirect(url_for("admin.roles"))


# ---------- Admins ----------

@bp.route("/admins")
def admins():
    admins_ = User.query.filter_by(is_super_admin=True).all()
    return render_template("admin/admins.html", admins=admins_)


@bp.route("/admins/promote", methods=["POST"])
def promote_admin():
    login_value = (request.form.get("user") or "").strip()
    user = User.query.filter((User.username == login_value) | (User.email == login_value)).first()
    if not user:
        flash("用户不存在", "error")
    else:
        user.is_super_admin = True
        db.session.commit()
        flash(f"已提升 {user.username} 为系统管理员", "success")
    return redirect(url_for("admin.admins"))


@bp.route("/admins/<int:user_id>/revoke", methods=["POST"])
def revoke_admin(user_id):
    user = db.session.get(User, user_id)
    if not user:
        abort(404)
    if user.id == current_user.id:
        flash("不能撤销自己的管理员权限", "warning")
    else:
        user.is_super_admin = False
        db.session.commit()
        flash("已撤销管理员", "info")
    return redirect(url_for("admin.admins"))


# ---------- Public KBs / Docs ----------

@bp.route("/public-kbs")
def public_kbs():
    page, size = get_page_args()
    q = (request.args.get("q") or "").strip()
    query = KnowledgeBase.query.filter_by(visibility=KBVisibility.PUBLIC.value, is_archived=False)
    if q:
        query = query.filter(KnowledgeBase.name.ilike(f"%{q}%"))
    pager = query.order_by(KnowledgeBase.updated_at.desc()).paginate(page=page, per_page=size, error_out=False)
    return render_template("admin/public_kbs.html", pager=pager, q=q)


@bp.route("/public-kbs/<int:kb_id>/unpublish", methods=["POST"])
def unpublish_kb(kb_id):
    kb = db.session.get(KnowledgeBase, kb_id)
    if not kb:
        abort(404)
    kb.visibility = KBVisibility.PRIVATE.value
    db.session.commit()
    flash("已下架（改为私密）", "info")
    return redirect(url_for("admin.public_kbs"))


@bp.route("/public-docs")
def public_docs():
    page, size = get_page_args()
    q = (request.args.get("q") or "").strip()
    query = (
        Document.query.join(KnowledgeBase, KnowledgeBase.id == Document.kb_id)
        .filter(Document.is_deleted == False, Document.privacy == DocumentPrivacy.NORMAL.value,
                KnowledgeBase.visibility == KBVisibility.PUBLIC.value, KnowledgeBase.is_archived == False)
    )
    if q:
        query = query.filter(Document.title.ilike(f"%{q}%"))
    pager = query.order_by(Document.updated_at.desc()).paginate(page=page, per_page=size, error_out=False)
    return render_template("admin/public_docs.html", pager=pager, q=q)


@bp.route("/public-docs/<int:doc_id>/takedown", methods=["POST"])
def takedown_doc(doc_id):
    doc = db.session.get(Document, doc_id)
    if not doc:
        abort(404)
    doc.privacy = DocumentPrivacy.PRIVATE.value
    db.session.commit()
    flash("已下架（设为私密）", "info")
    return redirect(url_for("admin.public_docs"))
