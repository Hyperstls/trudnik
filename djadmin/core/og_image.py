"""Generated Open Graph preview for a job (J117).

1200x630 PNG with the brand, job title, payment and city. The image contains
only public job fields; it is generated on demand and cached for an hour.
"""
from io import BytesIO
from pathlib import Path

from django.conf import settings
from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT = 1200, 630
PRIMARY = (217, 119, 6)
INK = (23, 23, 23)
MUTED = (115, 115, 115)
BG = (250, 250, 250)
WHITE = (255, 255, 255)


def _font(name, size):
    path = Path(settings.REPO_ROOT) / "static" / "fonts" / name
    try:
        return ImageFont.truetype(str(path), size)
    except OSError:
        return ImageFont.load_default(size=size)


def _wrap(draw, text, font, max_width, max_lines=3):
    words = (text or "").split()
    lines = []
    current = ""
    for word in words:
        candidate = (current + " " + word).strip()
        if not current or draw.textlength(candidate, font=font) <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
            if len(lines) == max_lines:
                break
    if current and len(lines) < max_lines:
        lines.append(current)
    if lines and draw.textlength(lines[-1], font=font) > max_width:
        while lines[-1] and draw.textlength(lines[-1] + "…", font=font) > max_width:
            lines[-1] = lines[-1][:-1]
        lines[-1] += "…"
    return lines


def _money(value):
    if value is None:
        return ""
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return ""
    if amount <= 0:
        return ""
    if amount.is_integer():
        return "%.0f ₽" % amount
    return "%.2f ₽" % amount


def render_job_og(job) -> bytes:
    image = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(image)
    draw.rectangle([0, 0, WIDTH, 14], fill=PRIMARY)

    draw.rounded_rectangle([64, 64, 148, 148], radius=24, fill=PRIMARY)
    draw.text((106, 104), "Т", font=_font("DejaVuSans-Bold.ttf", 52), fill=WHITE, anchor="mm")
    draw.text((168, 74), "Трудник", font=_font("DejaVuSans-Bold.ttf", 34), fill=PRIMARY)

    title_font = _font("DejaVuSans-Bold.ttf", 64)
    y = 210
    for line in _wrap(draw, job.work_type or "Задание", title_font, WIDTH - 128):
        draw.text((64, y), line, font=title_font, fill=INK)
        y += 78

    y = max(y + 12, 430)
    payment = _money(job.payment_amount)
    if payment:
        draw.text((64, y), payment, font=_font("DejaVuSans-Bold.ttf", 56), fill=PRIMARY)
    else:
        draw.text((64, y), "Оплата по договорённости", font=_font("DejaVuSans.ttf", 38), fill=MUTED)

    meta = " · ".join(part for part in (
        job.city or "",
        job.date_time.strftime("%d.%m.%Y") if job.date_time else "",
    ) if part)
    if meta:
        draw.text((64, HEIGHT - 112), meta, font=_font("DejaVuSans.ttf", 30), fill=MUTED)
    draw.text((WIDTH - 64, HEIGHT - 112), "трудник.рф", font=_font("DejaVuSans.ttf", 28), fill=MUTED, anchor="ra")

    buffer = BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()
