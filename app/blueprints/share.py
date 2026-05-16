"""Public share blueprint."""
from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for

from ..extensions import db
from ..models import DocumentShare
from ..services import share_service
from ..utils.outline import extract_outline

bp = Blueprint("share", __name__)

SESSION_PREFIX = "_share_unlocked:"


def _is_unlocked(token: str) -> bool:
    return bool(session.get(SESSION_PREFIX + token))


def _mark_unlocked(token: str) -> None:
    session[SESSION_PREFIX + token] = True


@bp.route("/<token>", methods=["GET", "POST"])
def view(token):
    s = share_service.get_active_share(token)
    if not s:
        return render_template("share/invalid.html"), 410
    if s.has_password and not _is_unlocked(token):
        if request.method == "POST":
            password = request.form.get("password") or ""
            if s.check_password(password):
                _mark_unlocked(token)
                return redirect(url_for("share.view", token=token))
            flash("密码错误", "error")
        return render_template("share/password.html", token=token)

    share_service.increment_view(s)
    doc = s.document
    if doc is None or doc.is_deleted:
        return render_template("share/invalid.html"), 410
    outline = extract_outline(doc.content_json)
    return render_template("share/view.html", doc=doc, share=s, outline=outline)
