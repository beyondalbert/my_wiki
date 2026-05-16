"""User blueprint: dashboard / profile."""
from flask import Blueprint, render_template
from flask_login import login_required, current_user

from ..extensions import db
from ..models import Document, KnowledgeBase, AIKnowledgeBase
from ..services import kb_service

bp = Blueprint("user", __name__)


@bp.route("/dashboard")
@login_required
def dashboard():
    my_kbs = kb_service.list_my_kbs(current_user).limit(8).all()
    public_kbs = kb_service.list_public_kbs().limit(6).all()
    recent_docs = (
        Document.query.filter_by(author_id=current_user.id, is_deleted=False)
        .order_by(Document.updated_at.desc()).limit(8).all()
    )
    ai_kbs = AIKnowledgeBase.query.filter_by(owner_id=current_user.id).order_by(AIKnowledgeBase.updated_at.desc()).limit(6).all()
    counts = {
        "kbs": KnowledgeBase.query.filter_by(owner_id=current_user.id, is_archived=False).count(),
        "docs": Document.query.filter_by(author_id=current_user.id, is_deleted=False).count(),
        "ai_kbs": AIKnowledgeBase.query.filter_by(owner_id=current_user.id).count(),
    }
    return render_template("user/dashboard.html", my_kbs=my_kbs, public_kbs=public_kbs,
                           recent_docs=recent_docs, ai_kbs=ai_kbs, counts=counts)


@bp.route("/profile")
@login_required
def profile():
    return render_template("user/profile.html", user=current_user)
