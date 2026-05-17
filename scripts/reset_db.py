"""一次性数据库重置脚本：drop_all + create_all + 种子。
用于主键类型从 Integer 改为 String(12) 后重建表结构。
跑完即可删除。
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402
from app.cli import _seed_perms_and_roles  # noqa: E402
from app.models import User, Role  # noqa: E402


def main():
    app = create_app(os.getenv("FLASK_CONFIG", "development"))
    with app.app_context():
        print(">>> Dropping all tables...")
        db.drop_all()
        print(">>> Creating all tables (string primary keys)...")
        db.create_all()
        print(">>> Seeding permissions & roles...")
        _seed_perms_and_roles()

        username = os.getenv("INIT_ADMIN_USERNAME", "admin")
        email = os.getenv("INIT_ADMIN_EMAIL", "admin@mywiki.local")
        password = os.getenv("INIT_ADMIN_PASSWORD", "Admin@123456")
        admin = User.query.filter_by(username=username).first()
        if not admin:
            admin = User(username=username, email=email, is_super_admin=True, is_active=True)
            admin.set_password(password)
            db.session.add(admin)
            db.session.commit()
            print(f">>> Created super admin: {username} / {password}")
        else:
            admin.is_super_admin = True
            admin.is_active = True
            db.session.commit()

        admin_role = Role.query.filter_by(code="admin").first()
        if admin_role and admin_role not in admin.roles:
            admin.roles.append(admin_role)
            db.session.commit()
        print(">>> Done.")


if __name__ == "__main__":
    main()
