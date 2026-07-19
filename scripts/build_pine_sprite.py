from pathlib import Path

import imageio.v3 as iio
import numpy as np
from PIL import Image, ImageDraw, ImageFilter


ROOT = Path(__file__).resolve().parents[1]
VIDEO = Path('/Users/shenchen/Downloads/Video 5 (1).mp4')
OUT = ROOT / 'images' / 'pine-sprite'
# The hero renders each cell around 650px tall. Keep the source cell larger
# than its rendered size so the sprite stays crisp on Retina displays too.
CELL = 768
MOTION_STEP = 2
ATLAS_COLS = 10

# 校准自 contact sheet：帧号来自实际姿态，不由角度线性推导。
ANGLE_KEYS = {
    'right-up': 0,
    'right': 20,
    'right-down': 44,
    'down': 98,
    'center': 186,
    'left-down': 118,
    'left': 144,
    'left-up': 164,
    'up': 178,
}

# 九向检查图的版式。
SPRITE_LAYOUT = [
    'right-up', 'right', 'right-down',
    'down', 'center', 'left-down',
    'left', 'left-up', 'up',
]


def green_background_alpha(rgb: np.ndarray) -> Image.Image:
    """Only key the green, border-connected backdrop; whites and greys stay opaque."""
    image = rgb.astype(np.float32) / 255.0
    mx = image.max(axis=2)
    mn = image.min(axis=2)
    delta = mx - mn
    hue = np.zeros_like(mx)
    nonzero = delta > 1e-5
    r, g, b = image[..., 0], image[..., 1], image[..., 2]
    rmax = nonzero & (mx == r)
    gmax = nonzero & (mx == g)
    bmax = nonzero & (mx == b)
    hue[rmax] = ((g[rmax] - b[rmax]) / delta[rmax]) % 6
    hue[gmax] = ((b[gmax] - r[gmax]) / delta[gmax]) + 2
    hue[bmax] = ((r[bmax] - g[bmax]) / delta[bmax]) + 4
    hue *= 60
    saturation = np.zeros_like(mx)
    saturation[mx > 1e-5] = delta[mx > 1e-5] / mx[mx > 1e-5]

    # The backdrop is a muted green (~140 degrees), including its darker floor
    # shadow. White/grey clothing, shoes and highlights are protected because
    # they do not have a clearly dominant green channel.
    candidate = (
        (hue > 78) & (hue < 178) &
        (saturation > 0.10) &
        (g > r * 1.08) & (g > b * 1.03)
    )
    alpha = np.where(candidate, 0, 255).astype(np.uint8)
    # A short feather removes hard green contours without eating light clothing.
    return Image.fromarray(alpha, 'L').filter(ImageFilter.GaussianBlur(0.75))


def make_contact_sheet(raw_frames: dict[str, Image.Image]):
    tile_w, tile_h = 320, 360
    sheet = Image.new('RGB', (tile_w * 3, tile_h * 3), '#101010')
    draw = ImageDraw.Draw(sheet)
    for index, key in enumerate(SPRITE_LAYOUT):
        thumb = raw_frames[key].copy()
        thumb.thumbnail((tile_w, tile_h - 34), Image.Resampling.LANCZOS)
        x = (index % 3) * tile_w + (tile_w - thumb.width) // 2
        y = (index // 3) * tile_h + 10
        sheet.paste(thumb, (x, y))
        label = f'{key.upper()}  ·  F{ANGLE_KEYS[key]}'
        draw.text(((index % 3) * tile_w + 12, (index // 3) * tile_h + tile_h - 24), label, fill='#ffffff')
    sheet.save(OUT / 'contact' / 'angle-keys-contact-sheet.png')


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'contact').mkdir(parents=True, exist_ok=True)
    raw_frames = {}
    transparent_frames = {}
    motion_frames = []
    key_by_frame = {frame: key for key, frame in ANGLE_KEYS.items()}

    # 顺序解码一次视频，每两帧取一帧；这组真实中间帧用于平滑追踪。
    for source_frame, source in enumerate(iio.imiter(VIDEO)):
        if source_frame % MOTION_STEP != 0 and source_frame not in key_by_frame:
            continue
        raw = Image.fromarray(source[:, :, :3], 'RGB')
        frame = raw.resize((CELL, CELL), Image.Resampling.LANCZOS)
        rgba = frame.convert('RGBA')
        rgba.putalpha(green_background_alpha(np.asarray(frame)))

        if source_frame % MOTION_STEP == 0:
            motion_frames.append(rgba)
        key = key_by_frame.get(source_frame)
        if key:
            raw_frames[key] = raw
            transparent_frames[key] = rgba

    for key, rgba in transparent_frames.items():
        rgba.save(OUT / f'frame-{key}.webp', 'WEBP', lossless=False, quality=94, method=4)

    make_contact_sheet(raw_frames)
    atlas_rows = int(np.ceil(len(motion_frames) / ATLAS_COLS))
    sprite = Image.new('RGBA', (CELL * ATLAS_COLS, CELL * atlas_rows), (0, 0, 0, 0))
    for index, frame in enumerate(motion_frames):
        sprite.alpha_composite(frame, ((index % ATLAS_COLS) * CELL, (index // ATLAS_COLS) * CELL))
    sprite.save(OUT / 'sprite.webp', 'WEBP', lossless=False, quality=96, method=5)
    transparent_frames['center'].save(OUT / 'frame-front.webp', 'WEBP', lossless=False, quality=96, method=5)
    transparent_frames['center'].save(OUT / 'front.webp', 'WEBP', lossless=False, quality=96, method=5)
    print('ANGLE_KEYS:', ANGLE_KEYS)
    print(f'MOTION_ATLAS: {len(motion_frames)} frames, {ATLAS_COLS}x{atlas_rows}, step={MOTION_STEP}')


if __name__ == '__main__':
    main()
