"""执行 ai_kb_sources 上传支持迁移（兼容 MySQL 5.7+ / 8.x）。

读取项目 .env 中的 DATABASE_URL，自动连接并执行：
1. doc_id 改为可空
2. 增加 kind / upload_filename / upload_path / upload_ext / upload_bytes 字段（已存在则跳过）
3. 创建 kind 索引（已存在则跳过）
4. 兜底回填 kind='document'

幂等可重复执行。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from urllib.parse import urlparse, unquote

# 让脚本能独立运行：把项目根加入 sys.path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# 加载 .env
try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv(ROOT / ".env")
except Exception:
    pass

import pymysql  # type: ignore


def _parse_db_url(url: str) -> dict:
    # mysql+pymysql://user:pass@host:port/db?charset=utf8mb4
    if "+" in url.split("://", 1)[0]:
        scheme_rest = url.split("://", 1)[1]
        url = "mysql://" + scheme_rest
    p = urlparse(url)
    return {
        "host": p.hostname,
        "port": p.port or 3306,
        "user": unquote(p.username or ""),
        "password": unquote(p.password or ""),
        "database": (p.path or "/").lstrip("/"),
        "charset": "utf8mb4",
        "autocommit": True,
    }


def _column_exists(cur, table: str, column: str) -> bool:
    cur.execute(
        "SELECT COUNT(*) FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=%s AND COLUMN_NAME=%s",
        (table, column),
    )
    return cur.fetchone()[0] > 0


def _index_exists(cur, table: str, index: str) -> bool:
    cur.execute(
        "SELECT COUNT(*) FROM information_schema.STATISTICS "
        "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=%s AND INDEX_NAME=%s",
        (table, index),
    )
    return cur.fetchone()[0] > 0


def main() -> int:
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("❌ 未读取到 DATABASE_URL，请确认 .env 存在", file=sys.stderr)
        return 2
    cfg = _parse_db_url(db_url)
    safe_cfg = {**cfg, "password": "***"}
    print(f"→ 连接数据库: {safe_cfg}")
    conn = pymysql.connect(**cfg)
    cur = conn.cursor()
    table = "ai_kb_sources"

    # 0. 先确认表存在
    cur.execute(
        "SELECT COUNT(*) FROM information_schema.TABLES "
        "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=%s",
        (table,),
    )
    if cur.fetchone()[0] == 0:
        print(f"❌ 表 {table} 不存在，请先初始化数据库（运行 init_db）", file=sys.stderr)
        return 3

    # 1. doc_id 可空
    cur.execute(
        "SELECT IS_NULLABLE FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=%s AND COLUMN_NAME='doc_id'",
        (table,),
    )
    row = cur.fetchone()
    if row and row[0] == "NO":
        print("→ ALTER doc_id NULL")
        cur.execute(f"ALTER TABLE {table} MODIFY COLUMN doc_id VARCHAR(12) NULL")
    else:
        print("✓ doc_id 已可空，跳过")

    # 2. 新增字段
    new_cols = [
        ("kind", "VARCHAR(16) NOT NULL DEFAULT 'document'"),
        ("upload_filename", "VARCHAR(255) NOT NULL DEFAULT ''"),
        ("upload_path", "VARCHAR(500) NOT NULL DEFAULT ''"),
        ("upload_ext", "VARCHAR(16) NOT NULL DEFAULT ''"),
        ("upload_bytes", "INT NOT NULL DEFAULT 0"),
    ]
    for col, ddl in new_cols:
        if _column_exists(cur, table, col):
            print(f"✓ 字段 {col} 已存在，跳过")
        else:
            print(f"→ ADD COLUMN {col}")
            cur.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")

    # 3. kind 索引
    idx = "ix_ai_kb_sources_kind"
    if _index_exists(cur, table, idx):
        print(f"✓ 索引 {idx} 已存在，跳过")
    else:
        print(f"→ CREATE INDEX {idx}")
        cur.execute(f"CREATE INDEX {idx} ON {table}(kind)")

    # 4. 兜底回填
    cur.execute(f"UPDATE {table} SET kind='document' WHERE kind IS NULL OR kind=''")
    print(f"✓ 兜底回填 kind='document' 完成（影响 {cur.rowcount} 行）")

    cur.close()
    conn.close()
    print("\n✅ 迁移完成。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
