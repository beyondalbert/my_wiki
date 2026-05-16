"""Custom Flask CLI commands."""
import click

from .extensions import db
from .models import User, Role, Permission


DEFAULT_PERMISSIONS = [
    ("kb.create", "创建知识库"),
    ("kb.manage_own", "管理个人知识库"),
    ("doc.create", "创建文档"),
    ("doc.share", "分享文档"),
    ("ai.use", "使用 AI 知识库"),
    ("admin.users", "用户管理"),
    ("admin.roles", "角色管理"),
    ("admin.public", "公开内容审核"),
]

DEFAULT_ROLES = [
    {
        "code": "user",
        "name": "普通用户",
        "is_system": True,
        "permissions": ["kb.create", "kb.manage_own", "doc.create", "doc.share", "ai.use"],
    },
    {
        "code": "moderator",
        "name": "内容审核员",
        "is_system": True,
        "permissions": ["admin.public"],
    },
    {
        "code": "admin",
        "name": "系统管理员",
        "is_system": True,
        "permissions": [p[0] for p in DEFAULT_PERMISSIONS],
    },
]


def _seed_perms_and_roles():
    code_map = {}
    for code, name in DEFAULT_PERMISSIONS:
        p = Permission.query.filter_by(code=code).first()
        if not p:
            p = Permission(code=code, name=name)
            db.session.add(p)
        code_map[code] = p
    db.session.commit()
    for r in DEFAULT_ROLES:
        role = Role.query.filter_by(code=r["code"]).first()
        if not role:
            role = Role(code=r["code"], name=r["name"], is_system=r["is_system"])
            db.session.add(role)
            db.session.flush()
        role.is_system = r["is_system"]
        role.permissions = [code_map[c] for c in r["permissions"] if c in code_map]
    db.session.commit()


def register_cli(app):
    @app.cli.command("init-db")
    @click.option("--admin-username", default="admin", show_default=True)
    @click.option("--admin-email", default="admin@mywiki.local", show_default=True)
    @click.option("--admin-password", default="Admin@123456", show_default=True,
                  help="初始超管密码，建议登录后立即修改")
    def init_db(admin_username, admin_email, admin_password):
        """Create tables, seed default roles/permissions, ensure super admin."""
        db.create_all()
        _seed_perms_and_roles()

        admin = User.query.filter_by(username=admin_username).first()
        if not admin:
            admin = User(
                username=admin_username,
                email=admin_email,
                is_super_admin=True,
                is_active=True,
            )
            admin.set_password(admin_password)
            db.session.add(admin)
            db.session.commit()
            click.echo(f"已创建超管账号：{admin_username} / {admin_password}")
        else:
            admin.is_super_admin = True
            admin.is_active = True
            db.session.commit()
            click.echo(f"超管账号已存在：{admin_username}")

        # attach admin role
        admin_role = Role.query.filter_by(code="admin").first()
        if admin_role and admin_role not in admin.roles:
            admin.roles.append(admin_role)
            db.session.commit()
        click.echo("初始化完成。")

    @app.cli.command("create-user")
    @click.argument("username")
    @click.argument("email")
    @click.argument("password")
    def create_user(username, email, password):
        """Create a normal user."""
        if User.query.filter_by(username=username).first():
            click.echo("用户名已存在")
            return
        u = User(username=username, email=email)
        u.set_password(password)
        user_role = Role.query.filter_by(code="user").first()
        if user_role:
            u.roles.append(user_role)
        db.session.add(u)
        db.session.commit()
        click.echo(f"已创建用户 {username}")
