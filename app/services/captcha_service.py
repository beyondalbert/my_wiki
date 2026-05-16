"""Image captcha service using Pillow."""
from __future__ import annotations

import io
import random
import string
import time
from typing import Tuple

from flask import current_app, session
from PIL import Image, ImageDraw, ImageFilter, ImageFont


_ALPHABET = string.ascii_uppercase.replace("O", "").replace("I", "") + "23456789"
SESSION_KEY = "_captcha"


def _random_text(length: int = 4) -> str:
    return "".join(random.choice(_ALPHABET) for _ in range(length))


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    # Try a few common bundled fonts; fall back to default.
    for name in ("arial.ttf", "DejaVuSans-Bold.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def generate_captcha(width: int = 140, height: int = 48, length: int = 4) -> Tuple[bytes, str]:
    text = _random_text(length)
    image = Image.new("RGB", (width, height), color=(245, 246, 250))
    draw = ImageDraw.Draw(image)
    font = _load_font(28)

    # Decorative dots
    for _ in range(180):
        xy = (random.randint(0, width), random.randint(0, height))
        draw.point(xy, fill=(random.randint(180, 230), random.randint(180, 230), random.randint(180, 230)))

    # Decorative lines
    for _ in range(4):
        start = (random.randint(0, width), random.randint(0, height))
        end = (random.randint(0, width), random.randint(0, height))
        draw.line([start, end], fill=(random.randint(150, 200), random.randint(150, 200), random.randint(150, 200)), width=1)

    # Characters with slight rotation
    palette = [(99, 102, 241), (79, 70, 229), (236, 72, 153), (14, 165, 233), (16, 185, 129)]
    char_w = width // (length + 1)
    for i, ch in enumerate(text):
        ch_img = Image.new("RGBA", (char_w + 8, height), (255, 255, 255, 0))
        ch_draw = ImageDraw.Draw(ch_img)
        ch_draw.text((4, 4), ch, font=font, fill=random.choice(palette))
        ch_img = ch_img.rotate(random.uniform(-22, 22), resample=Image.BICUBIC, expand=False)
        image.paste(ch_img, (char_w * i + 8, 4), ch_img)

    image = image.filter(ImageFilter.SMOOTH)
    buf = io.BytesIO()
    image.save(buf, format="PNG", optimize=True)
    return buf.getvalue(), text


def issue_captcha() -> bytes:
    """Generate a captcha image and store the answer in session."""
    png_bytes, text = generate_captcha()
    session[SESSION_KEY] = {
        "code": text.lower(),
        "ts": int(time.time()),
    }
    return png_bytes


def verify_captcha(user_input: str | None) -> bool:
    if not user_input:
        return False
    payload = session.get(SESSION_KEY)
    if not payload:
        return False
    ttl = current_app.config.get("CAPTCHA_TTL_SECONDS", 300)
    if int(time.time()) - int(payload.get("ts", 0)) > ttl:
        session.pop(SESSION_KEY, None)
        return False
    expected = (payload.get("code") or "").lower()
    ok = (user_input or "").strip().lower() == expected
    # one-shot: drop after verification regardless
    session.pop(SESSION_KEY, None)
    return ok
