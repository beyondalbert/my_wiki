"""AI Knowledge Base models (Karpathy LLM Wiki style)."""
from datetime import datetime
from enum import Enum

from ..extensions import db
from ..utils.ids import generate_id


class AIKBStatus(str, Enum):
    IDLE = "idle"
    BUILDING = "building"
    READY = "ready"
    FAILED = "failed"


class AIKBSourceStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"


class AIKnowledgeBase(db.Model):
    __tablename__ = "ai_knowledge_bases"

    id = db.Column(db.String(12), primary_key=True, default=generate_id)
    owner_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    name = db.Column(db.String(128), nullable=False)
    description = db.Column(db.String(500), default="")
    chat_model = db.Column(db.String(64), default="")  # if empty, fall back to config CHAT_MODEL
    enable_rag = db.Column(db.Boolean, default=False, nullable=False)

    status = db.Column(db.String(16), default=AIKBStatus.IDLE.value, nullable=False, index=True)
    last_built_at = db.Column(db.DateTime)
    error_msg = db.Column(db.String(500), default="")

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    owner = db.relationship("User", backref=db.backref("ai_kbs", lazy="dynamic"))

    def __repr__(self) -> str:
        return f"<AIKnowledgeBase {self.id} {self.name}>"


class AIKBSourceKind(str, Enum):
    DOCUMENT = "document"   # 关联现有知识库文档
    UPLOAD = "upload"       # 上传的外部文件（PDF/Word/文本/图片等）


class AIKBSource(db.Model):
    """已加入 AI 知识库的源文档（可为关联文档或外部上传件）。"""
    __tablename__ = "ai_kb_sources"
    __table_args__ = (
        db.UniqueConstraint("ai_kb_id", "doc_id", name="uq_aikb_doc"),
    )

    id = db.Column(db.String(12), primary_key=True, default=generate_id)
    ai_kb_id = db.Column(db.String(12), db.ForeignKey("ai_knowledge_bases.id", ondelete="CASCADE"), nullable=False, index=True)

    # 源类型：document | upload
    kind = db.Column(db.String(16), default=AIKBSourceKind.DOCUMENT.value, nullable=False, index=True)

    # kind=document 时使用
    doc_id = db.Column(db.String(12), db.ForeignKey("documents.id", ondelete="CASCADE"), nullable=True, index=True)

    # kind=upload 时使用
    upload_filename = db.Column(db.String(255), default="")  # 原始文件名
    upload_path = db.Column(db.String(500), default="")      # 服务器存储相对路径
    upload_ext = db.Column(db.String(16), default="")        # pdf/docx/png/...
    upload_bytes = db.Column(db.Integer, default=0)          # 字节大小

    status = db.Column(db.String(16), default=AIKBSourceStatus.PENDING.value, nullable=False, index=True)
    err_msg = db.Column(db.String(500), default="")
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    ai_kb = db.relationship("AIKnowledgeBase", backref=db.backref("sources", lazy="dynamic", cascade="all, delete-orphan"))
    document = db.relationship("Document")

    @property
    def display_title(self) -> str:
        if self.kind == AIKBSourceKind.UPLOAD.value:
            return self.upload_filename or "未命名上传件"
        if self.document:
            return self.document.title
        return "已删除文档"


class AIKBArticle(db.Model):
    """Karpathy 风格的 wiki 条目。每条对应 instance/ai_wiki/<ai_kb_id>/<slug>.md 一份文件。"""
    __tablename__ = "ai_kb_articles"
    __table_args__ = (
        db.UniqueConstraint("ai_kb_id", "slug", name="uq_aikb_slug"),
    )

    id = db.Column(db.String(12), primary_key=True, default=generate_id)
    ai_kb_id = db.Column(db.String(12), db.ForeignKey("ai_knowledge_bases.id", ondelete="CASCADE"), nullable=False, index=True)

    title = db.Column(db.String(255), nullable=False)
    slug = db.Column(db.String(255), nullable=False, index=True)
    summary = db.Column(db.String(500), default="")
    tags_json = db.Column(db.Text)            # JSON: ["tag1", ...]
    aliases_json = db.Column(db.Text)         # JSON: alternative titles for [[..]] resolution
    content_md = db.Column(db.Text)
    source_doc_ids_json = db.Column(db.Text)  # JSON: [doc_id, ...]

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    ai_kb = db.relationship("AIKnowledgeBase", backref=db.backref("articles", lazy="dynamic", cascade="all, delete-orphan"))

    def __repr__(self) -> str:
        return f"<AIKBArticle {self.ai_kb_id}/{self.slug}>"


class AIKBLink(db.Model):
    """条目之间的超链接（解析自 [[Title]] 占位）。"""
    __tablename__ = "ai_kb_links"

    id = db.Column(db.String(12), primary_key=True, default=generate_id)
    ai_kb_id = db.Column(db.String(12), db.ForeignKey("ai_knowledge_bases.id", ondelete="CASCADE"), nullable=False, index=True)
    from_article_id = db.Column(db.String(12), db.ForeignKey("ai_kb_articles.id", ondelete="CASCADE"), nullable=False, index=True)
    # to_article_id 可为空 -> 红链（占位但未命中任何条目）
    to_article_id = db.Column(db.String(12), db.ForeignKey("ai_kb_articles.id", ondelete="SET NULL"), index=True)
    anchor_text = db.Column(db.String(255), default="")

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    from_article = db.relationship("AIKBArticle", foreign_keys=[from_article_id], backref=db.backref("outgoing_links", lazy="dynamic", cascade="all, delete-orphan"))
    to_article = db.relationship("AIKBArticle", foreign_keys=[to_article_id], backref=db.backref("incoming_links", lazy="dynamic"))


class AIKBChunk(db.Model):
    """可选：仅当 enable_rag=true 时使用，存切分元数据；向量本体存 ChromaDB。"""
    __tablename__ = "ai_kb_chunks"

    id = db.Column(db.String(12), primary_key=True, default=generate_id)
    ai_kb_id = db.Column(db.String(12), db.ForeignKey("ai_knowledge_bases.id", ondelete="CASCADE"), nullable=False, index=True)
    article_id = db.Column(db.String(12), db.ForeignKey("ai_kb_articles.id", ondelete="CASCADE"), nullable=False, index=True)
    chunk_idx = db.Column(db.Integer, default=0, nullable=False)
    content = db.Column(db.Text)
    vector_id = db.Column(db.String(64), index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
