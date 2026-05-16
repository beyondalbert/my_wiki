"""Main blueprint: landing + dashboard redirect."""
from flask import Blueprint, redirect, render_template, url_for
from flask_login import current_user

from ..services import kb_service

bp = Blueprint("main", __name__)


@bp.route("/")
def index():
    if current_user.is_authenticated:
        return redirect(url_for("user.dashboard"))
    public_kbs = kb_service.list_public_kbs().limit(8).all()
    return render_template("main/landing.html", public_kbs=public_kbs)
