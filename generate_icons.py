"""Генерация иконок для Трудник PWA + TWA (Android)"""
from PIL import Image, ImageDraw
import os
import math

SIZES = [48, 72, 96, 144, 168, 192, 512]
ICON_DIR = os.path.join('static', 'icons')

# Цвета как в web-манифесте и twa-config
THEME_COLOR = (217, 119, 6)   # #d97706 — янтарный
BG_COLOR = (255, 255, 255)     # белый фон
BG_CIRCLE = (255, 248, 240)    # светлый фон для круга

def draw_trudnik_icon(size):
    """Рисует иконку «Трудник»: крест-буква Т с руками"""
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    margin = size * 0.1
    cx, cy = size / 2, size / 2
    r = (size - 2 * margin) / 2
    
    # Фоновый круг
    draw.rounded_rectangle(
        [margin, margin, size - margin, size - margin],
        radius=r, fill=BG_CIRCLE
    )
    draw.rounded_rectangle(
        [margin, margin, size - margin, size - margin],
        radius=r, outline=THEME_COLOR, width=max(2, int(size * 0.04))
    )
    
    # Крест / буква Т
    lw = max(2, int(size * 0.07))
    top = size * 0.25
    bottom = size * 0.72
    mid_y = size * 0.40
    cross_left = size * 0.30
    cross_right = size * 0.70
    center_x = size / 2
    
    # Вертикальная линия (ствол Т)
    draw.line([center_x, top, center_x, bottom], fill=THEME_COLOR, width=lw)
    # Горизонтальная линия (перекладина Т)
    draw.line([cross_left, mid_y, cross_right, mid_y], fill=THEME_COLOR, width=lw)
    # Нижняя перекладина
    bar_y = size * 0.68
    draw.line([size * 0.32, bar_y, center_x, bar_y], fill=THEME_COLOR, width=max(1, int(lw * 0.75)))
    # Маленький элемент справа сверху
    short_x = size * 0.58
    draw.line([short_x, top, short_x, size * 0.32], fill=THEME_COLOR, width=max(1, int(lw * 0.8)))
    
    # Руки (стилизованные ладони внизу)
    palm_y = size * 0.80
    palm_r = size * 0.06
    draw.ellipse([center_x - palm_r*2.5, palm_y - palm_r, center_x - palm_r*0.5, palm_y + palm_r], fill=THEME_COLOR)
    draw.ellipse([center_x + palm_r*0.5, palm_y - palm_r, center_x + palm_r*2.5, palm_y + palm_r], fill=THEME_COLOR)
    
    return img

def main():
    os.makedirs(ICON_DIR, exist_ok=True)
    for s in SIZES:
        img = draw_trudnik_icon(s)
        path = os.path.join(ICON_DIR, f'icon-{s}x{s}.png')
        img.save(path, 'PNG')
        print(f'  [OK] {path} ({os.path.getsize(path)} bytes)')
    
    # Копируем 512px в twa-project для store_icon
    import shutil
    src = os.path.join(ICON_DIR, 'icon-512x512.png')
    dst = os.path.join('twa-project', 'store_icon.png')
    shutil.copy(src, dst)
    print(f'  [OK] store_icon: {dst}')

if __name__ == '__main__':
    main()
