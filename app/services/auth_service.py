"""Auth service."""
from __future__ import annotations

import re
from datetime import datetime

from flask import request

from ..extensions import db
from ..models import User


USERNAME_RE = re.compile(r"^[A-Za-z0-9_\u4e00-\u9fa5]{2,32}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class AuthError(Exception):
    pass


def validate_register(username: str, email: str, password: str, password2: str) -> None:
    if not username or not USERNAME_RE.match(username):
        raise AuthError("用户名需为 2-32 位字母/数字/下划线/中文")
    if not email or not EMAIL_RE.match(email):
        raise AuthError("邮箱格式不正确")
    if not password or len(password) < 6:
        raise AuthError("密码长度至少 6 位")
    if password != password2:
        raise AuthError("两次密码不一致")
    if User.query.filter_by(username=username).first():
        raise AuthError("用户名已被占用")
    if User.query.filter_by(email=email).first():
        raise AuthError("邮箱已被注册")


def register(username: str, email: str, password: str) -> User:
    user = User(username=username, email=email)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return user


def authenticate(login: str, password: str) -> User | None:
    user = (
        User.query.filter((User.username == login) | (User.email == login)).first()
    )
    if user and user.is_active and user.check_password(password):
        return user
    return None


def mark_login(user: User) -> None:
    user.last_login_at = datetime.utcnow()
    user.last_login_ip = (request.headers.get("X-Forwarded-For") or request.remote_addr or "")[:64]
    db.session.commit()


def change_password(user: User, old_password: str, new_password: str, new_password2: str) -> None:
    if not user.check_password(old_password or ""):
        raise AuthError("原密码不正确")
    if not new_password or len(new_password) < 6:
        raise AuthError("新密码长度至少 6 位")
    if new_password != new_password2:
        raise AuthError("两次新密码不一致")
    if new_password == old_password:
        raise AuthError("新密码不能与原密码相同")
    user.set_password(new_password)
    db.session.commit()
