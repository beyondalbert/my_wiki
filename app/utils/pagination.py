"""Pagination helpers."""
from flask import request


def get_page_args(default_size: int = 20, max_size: int = 100):
    page = max(int(request.args.get("page", 1) or 1), 1)
    size = int(request.args.get("size", default_size) or default_size)
    size = max(1, min(size, max_size))
    return page, size
