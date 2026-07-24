from pathlib import Path

import imageio.v3 as iio
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from scipy import ndimage


ROOT = Path(__file__).resolve().parents[1]
VIDEO = Path('/Users/shenchen/Downloads/Video 8.mp4')
OUT = ROOT / 'images' / 'pine-sprite'
# The hero renders each cell around 650px tall. Keep the source cell larger
# than its rendered size so the sprite stays crisp on Retina displays too.
CELL = 768
MOTION_STEP = 2
ATLAS_COLS = 10
FIT_SCALE = 0.80   # 人物在画幅内的缩放，留出四周余量防止竖显示框裁切
BOTTOM_PAD = 36    # 底部留白，避免鞋底贴边被裁 / 被接触影削到

# 校准自 contact sheet：帧号来自实际姿态，不由角度线性推导。
ANGLE_KEYS = {
    'right-up': 28,
    'right': 52,
    'right-down': 60,
    'down': 72,
    'center': 16,
    'left-down': 112,
    'left': 132,
    'left-up': 156,
    'up': 20,
}

# 九向检查图的版式。
SPRITE_LAYOUT = [
    'right-up', 'right', 'right-down',
    'down', 'center', 'left-down',
    'left', 'left-up', 'up',
]


def green_background_alpha(rgb: np.ndarray) -> Image.Image:
    """Key the green screen while protecting low-saturation shoes and clothing.

    A single threshold cannot handle this footage: a loose key removes green
    spill from the background but also eats the pale rubber soles, while a
    strict key leaves enclosed green areas between the body, arms and legs.
    The matte therefore combines:
      1. a loose, border-connected background key;
      2. a stricter global key for enclosed green-screen holes;
      3. a foreground guard grown from the largest non-border subject region.
    """
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

    greenish = (hue > 72) & (hue < 182)

    # Loose key: catches the dim floor and contact shadow, but only when it is
    # connected to the image border.
    candidate = (
        greenish &
        (saturation > 0.055) &
        (g > r * 1.025) & (g > b * 0.985)
    )
    seed = np.zeros_like(candidate)
    seed[0, :] = seed[-1, :] = seed[:, 0] = seed[:, -1] = True
    seed &= candidate
    border_background = ndimage.binary_propagation(seed, mask=candidate)

    # Strict key: removes green-screen islands enclosed by the pose.
    enclosed_background = (
        greenish &
        (saturation > 0.275) &
        (g > np.maximum(r, b) * 1.09)
    )
    background = ndimage.binary_dilation(
        border_background | enclosed_background,
        iterations=1,
    )

    # Build a conservative foreground seed. The largest component that does
    # not touch the image border is the character; expanding it by three pixels
    # protects shoe soles, laces and anti-aliased clothing edges from the loose
    # green key without restoring detached floor shadows.
    definite_foreground = (
        (~greenish) |
        (saturation < 0.15) |
        (g <= np.maximum(r, b) * 1.045)
    )
    labels, _ = ndimage.label(definite_foreground)
    border_labels = np.unique(np.concatenate((
        labels[0, :],
        labels[-1, :],
        labels[:, 0],
        labels[:, -1],
    )))
    component_sizes = np.bincount(labels.ravel())
    component_sizes[border_labels] = 0
    component_sizes[0] = 0
    subject_label = int(component_sizes.argmax())
    subject_guard = ndimage.binary_dilation(
        labels == subject_label,
        iterations=1,
    )
    background &= ~subject_guard

    alpha = np.where(background, 0, 255).astype(np.uint8)
    alpha = np.asarray(
        Image.fromarray(alpha, 'L').filter(ImageFilter.GaussianBlur(0.35)),
        dtype=np.float32,
    )
    # Compress the feather into a narrow anti-aliased edge. This removes the
    # soft cyan outline caused by semi-transparent green-screen pixels while
    # retaining a clean one-pixel transition at the rendered size.
    alpha = np.clip((alpha - 32.0) * (255.0 / 191.0), 0, 255)
    return Image.fromarray(alpha.astype(np.uint8), 'L')


def despill(rgb: np.ndarray, alpha: Image.Image) -> Image.Image:
    """Neutralise green spill on the kept foreground (green never exceeds
    max(red, blue)). The character has no genuinely green surface, so this is
    lossless for it and kills any residual green tint on soles / edges."""
    a = rgb.astype(np.float32)
    a[..., 1] = np.minimum(a[..., 1], np.maximum(a[..., 0], a[..., 2]))
    edge = np.asarray(alpha) < 250
    # The source also carries a blue-green rim from the screen lighting.
    # Neutralise both channels only inside the one-pixel matte transition.
    a[..., 1] = np.where(
        edge,
        np.minimum(a[..., 1], np.maximum(a[..., 0], a[..., 2]) * 0.92),
        a[..., 1],
    )
    a[..., 2] = np.where(
        edge,
        np.minimum(a[..., 2], np.maximum(a[..., 0], a[..., 1])),
        a[..., 2],
    )
    return Image.fromarray(a.clip(0, 255).astype(np.uint8), 'RGB')


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
        farr = np.asarray(frame)
        alpha = green_background_alpha(farr)
        rgba = despill(farr, alpha).convert('RGBA')
        rgba.putalpha(alpha)

        # 盘腿坐姿较宽，竖向显示框会裁掉两侧的鞋：整帧缩至 83% 居中、底部对齐，
        # 让人物完整落在露出区内，并保持"坐在页面上"的贴地感。
        sw = int(CELL * FIT_SCALE)
        placed = Image.new('RGBA', (CELL, CELL), (0, 0, 0, 0))
        placed.alpha_composite(rgba.resize((sw, sw), Image.Resampling.LANCZOS),
                               ((CELL - sw) // 2, CELL - sw - BOTTOM_PAD))

        if source_frame % MOTION_STEP == 0:
            motion_frames.append(placed)
        key = key_by_frame.get(source_frame)
        if key:
            raw_frames[key] = raw
            transparent_frames[key] = placed

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
