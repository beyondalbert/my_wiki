"""Document and DocumentShare models."""
from datetime import datetime
from enum import Enum

from werkzeug.security import generate_password_hash, check_password_hash

from ..extensions import db


class DocumentType(str, Enum):
    DOC = "doc"
    SHEET = "sheet"


class DocumentPrivacy(str, Enum):
    NORMAL = "normal"     # 可被分享
    PRIVATE = "private"   # 不可被分享


class Document(db.Model):
    __tablename__ = "documents"

    id = db.Column(db.Integer, primary_key=True)
    kb_id = db.Column(db.Integer, db.ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False, index=True)
    parent_id = db.Column(db.Integer, db.ForeignKey("documents.id", ondelete="SET NULL"), index=True)

    title = db.Column(db.String(255), nullable=False, default="未命名")
    type = db.Column(db.String(16), default=DocumentType.DOC.value, nullable=False)
    privacy = db.Column(db.String(16), default=DocumentPrivacy.NORMAL.value, nullable=False, index=True)

    # Editor.js JSON content. We use LONGTEXT for large content via mysql variant.
    content_json = db.Column(db.Text)
    # Plain text representation for search / AI ingestion
    plain_text = db.Column(db.Text)

    sort_order = db.Column(db.Integer, default=0, nullable=False)
    is_deleted = db.Column(db.Boolean, default=False, nullable=False, index=True)

    author_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), index=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    kb = db.relationship("KnowledgeBase", backref=db.backref("documents", lazy="dynamic"))
    author = db.relationship("User", backref=db.backref("authored_docs", lazy="dynamic"))
    parent = db.relationship("Document", remote_side=[id], backref=db.backref("children", lazy="dynamic"))

    @property
    def can_be_shared(self) -> bool:
        return self.privacy == DocumentPrivacy.NORMAL.value

    def __repr__(self) -> str:
        return f"<Document {self.id} {self.title}>"


class DocumentShare(db.Model):
    __tablename__ = "document_shares"

    id = db.Column(db.Integer, primary_key=True)
    doc_id = db.Column(db.Integer, db.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    token = db.Column(db.String(64), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255))  # nullable: no password if NULL
    expires_at = db.Column(db.DateTime)
    is_revoked = db.Column(db.Boolean, default=False, nullable=False)
    view_count = db.Column(db.Integer, default=0, nullable=False)

    created_by = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    document = db.relationship("Document", backref=db.backref("shares", lazy="dynamic", cascade="all, delete-orphan"))
    creator = db.relationship("User")

    def set_password(self, password: str | None) -> None:
        if not password:
            self.password_hash = None
        else:
            self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        if not self.password_hash:
            return True
        return check_password_hash(self.password_hash, password or "")

    @property
    def has_password(self) -> bool:
        return bool(self.password_hash)

    @property
    def is_expired(self) -> bool:
        return bool(self.expires_at and self.expires_at < datetime.utcnow())

    @property
    def is_valid(self) -> bool:
        return not self.is_revoked and not self.is_expired

    def __repr__(self) -> str:
        return f"<DocumentShare {self.token}>"
