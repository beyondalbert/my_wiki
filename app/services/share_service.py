"""Document share service."""
from __future__ import annotations

from datetime import datetime, timedelta

from ..extensions import db
from ..models import Document, DocumentShare, DocumentPrivacy
from ..utils.security import generate_token


class ShareError(Exception):
    pass


def create_share(doc: Document, creator_id: int, password: str | None = None,
                 ttl_hours: int | None = None) -> DocumentShare:
    if doc.privacy == DocumentPrivacy.PRIVATE.value:
        raise ShareError("私密文档不可分享")
    expires_at = None
    if ttl_hours and ttl_hours > 0:
        expires_at = datetime.utcnow() + timedelta(hours=ttl_hours)
    share = DocumentShare(
        doc_id=doc.id,
        token=generate_token(20),
        expires_at=expires_at,
        created_by=creator_id,
    )
    share.set_password(password)
    db.session.add(share)
    db.session.commit()
    return share


def revoke(share: DocumentShare) -> None:
    share.is_revoked = True
    db.session.commit()


def get_active_share(token: str) -> DocumentShare | None:
    share = DocumentShare.query.filter_by(token=token).first()
    if share and share.is_valid:
        return share
    return None


def increment_view(share: DocumentShare) -> None:
    share.view_count = (share.view_count or 0) + 1
    db.session.commit()
