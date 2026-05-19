"""SQLAlchemy models package."""
from .user import User, Role, Permission, RolePermission, UserRole
from .knowledge_base import KnowledgeBase, KBMember, KBVisibility, KBMemberRole
from .document import Document, DocGroup, DocumentShare, DocumentType, DocumentPrivacy
from .system_config import SystemConfig
from .ai_kb import (
    AIKnowledgeBase,
    AIKBSource,
    AIKBSourceKind,
    AIKBArticle,
    AIKBLink,
    AIKBChunk,
    AIKBStatus,
    AIKBSourceStatus,
)


__all__ = [
    "User",
    "Role",
    "Permission",
    "RolePermission",
    "UserRole",
    "KnowledgeBase",
    "KBMember",
    "KBVisibility",
    "KBMemberRole",
    "Document",
    "DocGroup",
    "DocumentShare",
    "DocumentType",
    "DocumentPrivacy",
    "SystemConfig",
    "AIKnowledgeBase",
    "AIKBSource",
    "AIKBSourceKind",
    "AIKBArticle",
    "AIKBLink",
    "AIKBChunk",
    "AIKBStatus",
    "AIKBSourceStatus",
]
