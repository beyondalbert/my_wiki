"""Common decorators."""
from functools import wraps

from flask import abort
from flask_login import current_user


def super_admin_required(view):
    """Only allow users with is_super_admin=True."""
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated:
            abort(401)
        if not getattr(current_user, "is_super_admin", False):
            abort(403)
        return view(*args, **kwargs)

    return wrapper


def permission_required(code: str):
    """Require a specific permission code (super admin always passes)."""
    def deco(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            if not current_user.is_authenticated:
                abort(401)
            if not current_user.has_permission(code):
                abort(403)
            return view(*args, **kwargs)
        return wrapper
    return deco
