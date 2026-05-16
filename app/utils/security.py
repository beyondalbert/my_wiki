"""Misc security helpers."""
import secrets


def generate_token(nbytes: int = 16) -> str:
    """URL-safe token suitable for share links."""
    return secrets.token_urlsafe(nbytes)
