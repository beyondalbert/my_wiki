"""System-level key-value configuration table.

Stores runtime-editable settings (e.g. AI model params) that can be
managed via the admin panel without restarting the server.
"""
from ..extensions import db


class SystemConfig(db.Model):
    __tablename__ = "system_configs"

    key = db.Column(db.String(64), primary_key=True)
    value = db.Column(db.Text, default="")
    description = db.Column(db.String(200), default="")

    def __repr__(self) -> str:
        return f"<SystemConfig {self.key}>"
