"""Knowledge base service: visibility / membership / queries."""
from __future__ import annotations

from sqlalchemy import or_

from ..extensions import db
from ..models import KnowledgeBase, KBMember, KBVisibility, KBMemberRole, User


def can_access(user, kb: KnowledgeBase | None) -> bool:
    if kb is None or kb.is_archived:
        return False
    if kb.visibility == KBVisibility.PUBLIC.value:
        return True
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_super_admin", False):
        return True
    if kb.owner_id == user.id:
        return True
    if kb.visibility == KBVisibility.MEMBERS.value:
        return KBMember.query.filter_by(kb_id=kb.id, user_id=user.id).first() is not None
    return False


def can_edit(user, kb: KnowledgeBase | None) -> bool:
    if kb is None:
        return False
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_super_admin", False):
        return True
    if kb.owner_id == user.id:
        return True
    member = KBMember.query.filter_by(kb_id=kb.id, user_id=user.id).first()
    return bool(member and member.role == KBMemberRole.EDITOR.value)


def can_manage(user, kb: KnowledgeBase | None) -> bool:
    """Manage = invite members / change visibility / delete."""
    if kb is None or user is None or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_super_admin", False):
        return True
    return kb.owner_id == user.id


def list_my_kbs(user: User):
    own = KnowledgeBase.query.filter_by(owner_id=user.id, is_archived=False)
    member_ids = [m.kb_id for m in KBMember.query.filter_by(user_id=user.id).all()]
    if member_ids:
        joined = KnowledgeBase.query.filter(KnowledgeBase.id.in_(member_ids), KnowledgeBase.is_archived == False)
        return own.union(joined).order_by(KnowledgeBase.updated_at.desc())
    return own.order_by(KnowledgeBase.updated_at.desc())


def list_public_kbs():
    return (
        KnowledgeBase.query
        .filter_by(visibility=KBVisibility.PUBLIC.value, is_archived=False)
        .order_by(KnowledgeBase.updated_at.desc())
    )


def add_member(kb: KnowledgeBase, user: User, role: str = KBMemberRole.VIEWER.value) -> KBMember:
    existing = KBMember.query.filter_by(kb_id=kb.id, user_id=user.id).first()
    if existing:
        existing.role = role
        db.session.commit()
        return existing
    m = KBMember(kb_id=kb.id, user_id=user.id, role=role)
    db.session.add(m)
    db.session.commit()
    return m


def remove_member(kb: KnowledgeBase, user_id: int) -> None:
    KBMember.query.filter_by(kb_id=kb.id, user_id=user_id).delete()
    db.session.commit()
