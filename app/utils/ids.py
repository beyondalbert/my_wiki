"""Short URL-friendly random ID generator (nanoid 风格)。

无第三方依赖，使用 secrets 实现，base62 字符集（去掉 0/O/1/l 易混字符以提升可读性）。
默认 12 字符 → 碰撞空间 ≈ 56^12 ≈ 5.8e20，对个人 wiki 量级远超够用。
"""
from __future__ import annotations

import secrets

# 去掉 0/O / 1/l/I 等易混字符，剩 56 个
_ALPHABET = "23456789abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ"


def generate_id(size: int = 12) -> str:
    """生成短随机字符串 ID（用作主键）。

    用法：
        id = db.Column(db.String(12), primary_key=True, default=generate_id)
    """
    return "".join(secrets.choice(_ALPHABET) for _ in range(size))
