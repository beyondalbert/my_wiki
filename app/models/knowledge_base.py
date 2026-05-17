"""Knowledge Base models."""
from datetime import datetime
from enum import Enum

from werkzeug.security import generate_password_hash, check_password_hash

from ..extensions import db
from ..utils.ids import generate_id


class KBVisibility(str, Enum):
    PRIVATE = "private"      # Only owner
    MEMBERS = "members"      # Owner + members
    PUBLIC = "public"        # Anyone


class KBMemberRole(str, Enum):
    VIEWER = "viewer"
    EDITOR = "editor"


class KnowledgeBase(db.Model):
    __tablename__ = "knowledge_bases"

    id = db.Column(db.String(12), primary_key=True, default=generate_id)
    name = db.Column(db.String(128), nullable=False)
    description = db.Column(db.String(500), default="")
    cover = db.Column(db.String(255), default="")
    icon = db.Column(db.String(32), default="book")

    owner_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    visibility = db.Column(db.String(16), default=KBVisibility.PRIVATE.value, nullable=False, index=True)
    # 仅在 visibility=public 时生效：设置后访客需输入密码才能访问。NULL = 不设密码。
    access_password_hash = db.Column(db.String(255))

    is_archived = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    owner = db.relationship("User", backref=db.backref("owned_kbs", lazy="dynamic"))

    @property
    def is_public(self) -> bool:
        return self.visibility == KBVisibility.PUBLIC.value

    @property
    def has_access_password(self) -> bool:
        return bool(self.access_password_hash)

    def set_access_password(self, password: str | None) -> None:
        if not password:
            self.access_password_hash = None
        else:
            self.access_password_hash = generate_password_hash(password)

    def check_access_password(self, password: str) -> bool:
        if not self.access_password_hash:
            return True
        return check_password_hash(self.access_password_hash, password or "")

    def __repr__(self) -> str:
        return f"<KnowledgeBase {self.id} {self.name}>"


class KBMember(db.Model):
    __tablename__ = "kb_members"
    __table_args__ = (
        db.UniqueConstraint("kb_id", "user_id", name="uq_kb_user"),
    )

    id = db.Column(db.Integer, primary_key=True)
    kb_id = db.Column(db.String(12), db.ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    role = db.Column(db.String(16), default=KBMemberRole.VIEWER.value, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    kb = db.relationship("KnowledgeBase", backref=db.backref("members", lazy="dynamic", cascade="all, delete-orphan"))
    user = db.relationship("User", backref=db.backref("kb_memberships", lazy="dynamic"))

    def __repr__(self) -> str:
        return f"<KBMember kb={self.kb_id} user={self.user_id} role={self.role}>"
