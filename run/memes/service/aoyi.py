from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps
import numpy as np
import imageio
import math
import os
import random
import argparse
import asyncio

DEFAULT_FONT = "./方正艺黑体.15.9.12.ttf"

def create_vignette_mask(size, strength=0.6):
    w, h = size
    x = np.linspace(-1, 1, w)[None, :]
    y = np.linspace(-1, 1, h)[:, None]
    d = np.sqrt(x**2 + y**2)
    mask = np.clip(1 - (d / np.max(d)) * (strength * 1.2), 0, 1)
    mask = (mask * 255).astype(np.uint8)
    return Image.fromarray(mask, mode='L')

def add_noise(img, amount=0.02, monochrome=True):
    arr = np.array(img).astype(np.float32) / 255.0
    noise = np.random.randn(*arr.shape)
    if arr.ndim == 3:
        if monochrome:
            noise = noise[..., 0:1]
            noise = np.repeat(noise, 3, axis=2)
    arr += noise * amount
    arr = np.clip(arr, 0, 1)
    arr = (arr * 255).astype(np.uint8)
    return Image.fromarray(arr)

def render_subtitle(text, font_path, base_width, padding=20, max_width_ratio=0.95, font_size=40, fill=(255,255,255)):
    lines = text.split('\n')
    font = ImageFont.truetype(font_path, font_size)
    img_dummy = Image.new('RGBA', (10,10), (0,0,0,0))
    draw = ImageDraw.Draw(img_dummy)
    def text_size(draw_obj, txt, fnt):
        bbox = draw_obj.textbbox((0, 0), txt, font=fnt)
        return bbox[2] - bbox[0], bbox[3] - bbox[1]
    def max_line_width(fs):
        f = ImageFont.truetype(font_path, fs)
        return max(text_size(draw, line, f)[0] for line in lines)
    while max_line_width(font_size) + padding*2 > base_width * max_width_ratio and font_size > 10:
        font_size -= 2
    font = ImageFont.truetype(font_path, font_size)
    line_heights = [text_size(draw, line, font)[1] for line in lines]
    text_width = max(text_size(draw, line, font)[0] for line in lines)
    text_height = sum(line_heights) + (len(lines)-1) * 6
    w = text_width + padding*2
    h = text_height + padding*2
    subtitle = Image.new('RGBA', (w, h), (0,0,0,0))
    d = ImageDraw.Draw(subtitle)
    y = padding
    for line in lines:
        tw, th = text_size(d, line, font)
        shadow_fill = (0, 0, 0, 140)
        d.text(((w - tw)//2 + 1, y + 1), line, font=font, fill=shadow_fill)
        d.text(((w - tw)//2, y), line, font=font, fill=fill)
        y += th + 6
    return subtitle

def feather_alpha(alpha_img, radius):
    return alpha_img.filter(ImageFilter.GaussianBlur(radius))

def apply_overlay(base_img, opacity=0.25):
    overlay = Image.new('RGBA', base_img.size, (0,0,0,int(255*opacity)))
    return Image.alpha_composite(base_img.convert('RGBA'), overlay)

def compose_frame(base_img, black_opacity, subtitle_img, subtitle_opacity, subtitle_y, vignette_strength, noise_amount):
    img = base_img.convert('RGBA')
    if black_opacity > 0:
        overlay = Image.new('RGBA', img.size, (0,0,0,int(255*black_opacity)))
        img = Image.alpha_composite(img, overlay)
    w, h = img.size
    if subtitle_img is not None:
        sx, sy = subtitle_img.size
        paste_x = (w - sx)//2
        paste_y = subtitle_y
        alpha = subtitle_img.split()[-1]
        alpha = feather_alpha(alpha, radius=8)
        s = subtitle_img.copy()
        s.putalpha(alpha)
        if subtitle_opacity < 1.0:
            a = np.array(s.split()[-1]).astype(np.float32)
            a = (a * subtitle_opacity).astype(np.uint8)
            s.putalpha(Image.fromarray(a))
        img.paste(s, (paste_x, paste_y), s)
    mask = create_vignette_mask(img.size, strength=vignette_strength)
    dark = Image.new('RGBA', img.size, (0,0,0,0))
    dark.putalpha(ImageOps.invert(mask))
    img = Image.alpha_composite(img, dark)
    if noise_amount > 0:
        img = add_noise(img.convert('RGB'), amount=noise_amount).convert('RGBA')
    return img


def create_static_background(base_img, black_opacity, subtitle_img, subtitle_opacity, subtitle_y, vignette_strength, blur_radius=None):
    w, h = base_img.size
    if blur_radius is None:
        blur_radius = max(6, int(min(w, h) / 40))
    bg = base_img.convert('RGBA').filter(ImageFilter.GaussianBlur(radius=blur_radius))
    if black_opacity > 0:
        overlay = Image.new('RGBA', bg.size, (0,0,0,int(255*black_opacity)))
        bg = Image.alpha_composite(bg, overlay)
    return bg

def compose_top_darkening(size, top_dark_opacity, vignette_strength, blur_radius=None):
    w, h = size
    if blur_radius is None:
        blur_radius = max(12, int(min(w, h) / 12))
    base_dark = Image.new('RGBA', (w, h), (0, 0, 0, int(255 * top_dark_opacity)))
    mask = create_vignette_mask((w, h), strength=vignette_strength)
    inv = ImageOps.invert(mask)
    inv = inv.filter(ImageFilter.GaussianBlur(radius=blur_radius))
    inv_arr = np.array(inv).astype(np.float32) / 255.0
    extra = np.clip(inv_arr * 1.0, 0.0, 1.0)
    alpha_extra = (extra * 255.0).astype(np.uint8)
    extra_layer = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    extra_layer.putalpha(Image.fromarray(alpha_extra))
    top = Image.alpha_composite(base_dark, extra_layer)
    return top

def draw_vertical_line_noise_layer(size, prob=0.12, count=6, width=1, jitter=2):
    w, h = size
    layer = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    if random.random() > prob:
        return layer
    draw = ImageDraw.Draw(layer)
    for i in range(count):
        x = random.randint(0, w-1)
        x += random.randint(-jitter, jitter)
        x = max(0, min(w-1, x))
        y0 = random.randint(0, h//6)
        y1 = random.randint(h*5//6, h-1)
        if random.random() < 0.6:
            col = (random.randint(200, 255), random.randint(200, 255), random.randint(200, 255), random.randint(20, 60))
        else:
            col = (random.randint(90, 160), random.randint(90, 160), random.randint(90, 160), random.randint(10, 40))
        for xx in range(-width//2, width//2 + 1):
            xi = max(0, min(w-1, x + xx))
            draw.line((xi, y0, xi, y1), fill=col)
    layer = layer.filter(ImageFilter.GaussianBlur(radius=1))
    return layer

def add_film_grain(img, amount=0.015):
    arr = np.array(img).astype(np.float32) / 255.0
    noise = np.random.randn(*arr.shape) * amount
    arr += noise
    arr = np.clip(arr, 0, 1)
    return Image.fromarray((arr * 255).astype(np.uint8))

def color_grade(img, contrast=1.05, saturation=0.9, brightness=1.0):
    from PIL import ImageEnhance
    out = img.convert('RGB')
    if contrast != 1.0:
        out = ImageEnhance.Contrast(out).enhance(contrast)
    if brightness != 1.0:
        out = ImageEnhance.Brightness(out).enhance(brightness)
    if saturation != 1.0:
        out = ImageEnhance.Color(out).enhance(saturation)
    return out

def create_subtitle_bg(subtitle_img, bg_color=(0,0,0,200), padding=12, radius=18, feather_radius=6):
    sx, sy = subtitle_img.size
    w = sx + padding*2
    h = sy + padding*2
    rect = Image.new('RGBA', (w, h), bg_color)
    mask = Image.new('L', (w, h), 0)
    d = ImageDraw.Draw(mask)
    d.rounded_rectangle((0,0,w,h), radius=radius, fill=255)
    mask_arr = np.array(mask).astype(np.float32) / 255.0
    xs = np.linspace(0, w-1, w)
    center_x = (w-1) / 2.0
    sigma_x = max(1.0, w * 0.28)
    hor = np.exp(-((xs - center_x) / sigma_x) ** 2)
    ys = np.linspace(0, h-1, h)[:, None]
    sigma_y = max(1.0, h * 0.6)
    vert = 0.6 + 0.4 * (1 - np.exp(-((ys) / sigma_y) ** 2))
    combined = mask_arr * hor[None, :] * vert
    alpha_new = (np.clip(combined, 0.0, 1.0) * 255.0).astype(np.uint8)
    rect.putalpha(Image.fromarray(alpha_new))
    rect = rect.filter(ImageFilter.GaussianBlur(radius=feather_radius))
    out = Image.new('RGBA', (w, h), (0,0,0,0))
    out = Image.alpha_composite(out, rect)
    out.paste(subtitle_img, (padding, padding), subtitle_img)
    return out

def is_cjk(text: str) -> bool:
    for ch in text:
        o = ord(ch)
        if (0x4E00 <= o <= 0x9FFF) or (0x3040 <= o <= 0x30FF) or (0xFF00 <= o <= 0xFFEF):
            return True
    return False

def choose_font_for_text(font_path, text):
    if font_path and os.path.exists(font_path):
        return font_path
    if is_cjk(text):
        import platform
        system = platform.system()
        if system == 'Windows':
            candidates = [
                r"C:\Windows\Fonts\msyh.ttc",
                r"C:\Windows\Fonts\msyhbd.ttc",
                r"C:\Windows\Fonts\simhei.ttf",
                r"C:\Windows\Fonts\simsun.ttc",
                r"C:\Windows\Fonts\meiryob.ttc",
                r"C:\Windows\Fonts\NotoSansCJK-Regular.ttc",
            ]
        elif system == 'Linux':
            candidates = [
                "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
                "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
                "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
                "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",  # fallback
            ]
        else:
            # macOS or others
            candidates = []
        for c in candidates:
            if os.path.exists(c):
                return c
    return DEFAULT_FONT

def draw_vertical_line_noise(img, prob=0.12, count=6, width=1, jitter=2):
    if random.random() > prob:
        return img
    w, h = img.size
    draw = ImageDraw.Draw(img)
    for i in range(count):
        x = random.randint(0, w-1)
        x += random.randint(-jitter, jitter)
        x = max(0, min(w-1, x))
        y0 = random.randint(0, h//6)
        y1 = random.randint(h*5//6, h-1)
        col = (random.randint(200,255), random.randint(200,255), random.randint(200,255)) if random.random() < 0.6 else (random.randint(90,160), random.randint(90,160), random.randint(90,160))
        for xx in range(-width//2, width//2 + 1):
            xi = max(0, min(w-1, x + xx))
            draw.line((xi, y0, xi, y1), fill=col)
    return img

async def generate_animation(input_path, output_path, text, duration=2.0, fps=20, black_opacity=0.5, subtitle_opacity=0.85, font_path=DEFAULT_FONT, feather_radius=8, vignette_strength=0.6, noise_amount=0.06, swing_amplitude=14.0, swing_overshoot=1.3, subject_scale=1.04, total_frames=None, min_cycles=2, max_cycles=4, top_dark_opacity=0.35, line_prob=0.12, line_count=6, line_width=1, line_jitter=2, subtitle_padding=12, subtitle_radius=18, subtitle_feather=6, subtitle_bg_alpha=255, font_size=26, fast_freq=10.0, jitter_amp=2.0):
    if not os.path.exists(input_path):
        raise FileNotFoundError(input_path)
    base = (await asyncio.to_thread(Image.open, input_path)).convert('RGBA')
    w, h = base.size
    subtitle_img = None
    if text and text.strip():
        text = text.replace('\\n', '\n')
        chosen_font = choose_font_for_text(font_path, text)
    fs = font_size if font_size is not None else max(18, w//36)
    subtitle_img = render_subtitle(text, chosen_font, base_width=w, padding=subtitle_padding, font_size=fs)
    if subtitle_img:
        sx, sy = subtitle_img.size
        subtitle_y = h - sy - int(h * 0.06)
    else:
        subtitle_y = h
    static_bg = create_static_background(base, black_opacity=max(black_opacity, 0.4), subtitle_img=subtitle_img, subtitle_opacity=subtitle_opacity, subtitle_y=subtitle_y, vignette_strength=vignette_strength)

    # 将帧生成移到线程中运行，避免阻塞事件循环
    def generate_frames():
        frames = []
        if total_frames is None:
            total_frames_inner = max(1, int(duration * fps))
        else:
            total_frames_inner = max(1, int(total_frames))
        cx = w // 2
        cy = h // 2
        num_cycles = random.randint(min_cycles, max_cycles)
        base_len = total_frames_inner // num_cycles
        cycle_lengths = [base_len] * num_cycles
        rem = total_frames_inner - base_len * num_cycles
        for i in range(rem):
            cycle_lengths[i % num_cycles] += 1
        cycles = []
        for cl in cycle_lengths:
            dir_choice = random.random()
            if dir_choice < 0.45:
                direction = (random.choice([-1, 1]), 0)
            elif dir_choice < 0.9:
                direction = (0, random.choice([-1, 1]))
            else:
                dxr = random.choice([-1, 1])
                dyr = random.choice([-1, 1])
                direction = (dxr/math.sqrt(2), dyr/math.sqrt(2))
            amp = swing_amplitude * (0.4 + random.random() * 0.6)
            damping_cycle = 3.0 + random.random() * 1.5
            cycles.append({'length': cl, 'dir': direction, 'amp': amp, 'damping': damping_cycle})
        frame_idx = 0
        for cycle in cycles:
            cl = cycle['length']
            direction = cycle['dir']
            amp = cycle['amp']
            damping_cycle = cycle['damping']
            for j in range(cl):
                t_cycle = j / (cl - 1) if cl > 1 else 0
                s = math.sin(math.pi * t_cycle)
                envelope = s * (1.0 - 0.5 * (t_cycle**1.2))
                overshoot_factor = 1.0 + 0.25 * (swing_overshoot - 1.0) * s
                disp_scalar = amp * math.exp(-damping_cycle * t_cycle) * envelope * overshoot_factor
                base_off_x = direction[0] * disp_scalar
                base_off_y = direction[1] * disp_scalar
                global_t = frame_idx / float(total_frames_inner) if total_frames_inner and total_frames_inner > 0 else t_cycle
                fast_scale = 0.25
                fast_x = fast_scale * amp * math.sin(2 * math.pi * fast_freq * global_t)
                fast_y = fast_scale * amp * math.cos(2 * math.pi * fast_freq * global_t)
                jitter_x = random.uniform(-jitter_amp * 0.8, jitter_amp * 0.8)
                jitter_y = random.uniform(-jitter_amp * 0.8, jitter_amp * 0.8)
                off_x = int(base_off_x + fast_x + jitter_x)
                off_y = int(base_off_y + fast_y + jitter_y)
                angle = 0
                subject = base.copy()
                if subject_scale != 1.0:
                    sw, sh = subject.size
                    new_sw = int(sw * subject_scale)
                    new_sh = int(sh * subject_scale)
                    subject = subject.resize((new_sw, new_sh), resample=Image.BICUBIC)
                pad = max(abs(off_x), abs(off_y)) + int(max(w, h) * 0.06)
                canvas_sub = Image.new('RGBA', (w + pad*2, h + pad*2), (0,0,0,0))
                paste_offset_x = pad + (w - subject.size[0]) // 2
                paste_offset_y = pad + (h - subject.size[1]) // 2
                canvas_sub.paste(subject, (paste_offset_x, paste_offset_y), subject if subject.mode == 'RGBA' else None)
                canvas_sub = canvas_sub.rotate(angle, resample=Image.BICUBIC, center=(canvas_sub.size[0]//2, canvas_sub.size[1]//2), expand=False)
                crop_x = (canvas_sub.size[0] - w)//2
                crop_y = (canvas_sub.size[1] - h)//2
                transformed_subject = canvas_sub.crop((crop_x, crop_y, crop_x + w, crop_y + h))
                frame = static_bg.copy()
                base_paste_x = (w - transformed_subject.size[0]) // 2
                base_paste_y = (h - transformed_subject.size[1]) // 2
                paste_x = base_paste_x + off_x
                paste_y = base_paste_y + off_y
                frame.paste(transformed_subject, (paste_x, paste_y), transformed_subject)
                if noise_amount > 0:
                    frame = add_noise(frame.convert('RGB'), amount=min(0.08, noise_amount)).convert('RGBA')
                top_dark = compose_top_darkening((w, h), top_dark_opacity=top_dark_opacity, vignette_strength=vignette_strength)
                frame = Image.alpha_composite(frame, top_dark)
                line_layer = draw_vertical_line_noise_layer((w, h), prob=line_prob, count=line_count, width=line_width, jitter=line_jitter)
                frame = Image.alpha_composite(frame, line_layer)
                if subtitle_img is not None:
                    s_bg = create_subtitle_bg(subtitle_img, bg_color=(10,10,10,subtitle_bg_alpha), padding=subtitle_padding, radius=subtitle_radius, feather_radius=subtitle_feather)
                    if subtitle_opacity < 1.0:
                        a = np.array(s_bg.split()[-1]).astype(np.float32)
                        a = (a * subtitle_opacity).astype(np.uint8)
                        s_bg.putalpha(Image.fromarray(a))
                    sbw, sbh = s_bg.size
                    paste_x = (w - sbw)//2
                    paste_y = subtitle_y - (sbh - subtitle_img.size[1])//2
                    frame.paste(s_bg, (paste_x, paste_y), s_bg)
                frame = color_grade(frame, contrast=1.05, saturation=0.9, brightness=0.98)
                frame = add_film_grain(frame, amount=0.03).convert('RGBA')
                frames.append(np.array(frame.convert('RGBA')))
                frame_idx += 1
        return frames

    frames = await asyncio.to_thread(generate_frames)
    await asyncio.to_thread(imageio.mimsave, output_path, frames, format='GIF', duration=1.0/fps)
    return output_path

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('input', help='输入图片路径')
    p.add_argument('output', default='奥义图.gif', help='输出 gif 路径')
    p.add_argument('--text', default='', help='字幕文本，支持\\n换行')
    p.add_argument('--duration', type=float, default=2.0)
    p.add_argument('--fps', type=int, default=20)
    p.add_argument('--black_opacity', type=float, default=0.5)
    p.add_argument('--subtitle_opacity', type=float, default=0.85)
    p.add_argument('--font', default=DEFAULT_FONT)
    p.add_argument('--vignette', type=float, default=0.6)
    p.add_argument('--noise', type=float, default=0.06, help='噪点强度')
    p.add_argument('--swing_amp', type=float, default=14.0, help='回弹/抖动幅度（像素）')
    p.add_argument('--swing_overshoot', type=float, default=1.3, help='回弹时的 overshoot 倍率，>1 会有更强张力')
    p.add_argument('--frames', type=int, default=None, help='总帧数（优先于 duration/fps）')
    p.add_argument('--subject_scale', type=float, default=1.04, help='主体略微放大比例以避免回弹出现黑框')
    p.add_argument('--top_dark_opacity', type=float, default=0.35, help='顶层全屏暗化不透明度（0..1）')
    p.add_argument('--line_prob', type=float, default=0.12, help='每帧出现竖线噪点的概率(0..1)')
    p.add_argument('--line_count', type=int, default=6, help='竖线噪点数量')
    p.add_argument('--line_width', type=int, default=1, help='竖线宽度')
    p.add_argument('--line_jitter', type=int, default=2, help='竖线水平抖动范围')
    p.add_argument('--subtitle_padding', type=int, default=12, help='字幕背景内边距')
    p.add_argument('--subtitle_radius', type=int, default=18, help='字幕背景圆角半径')
    p.add_argument('--subtitle_feather', type=int, default=6, help='字幕背景羽化半径')
    p.add_argument('--subtitle_bg_alpha', type=int, default=255, help='字幕背景 alpha (0-255)')
    p.add_argument('--font_size', type=int, default=26, help='显式指定字幕字体大小（覆盖自动计算）')
    p.add_argument('--fast_freq', type=float, default=10, help='快速抖动频率（Hz）')
    p.add_argument('--jitter_amp', type=float, default=2.0, help='每帧随机抖动幅度（像素）')
    args = p.parse_args()
    out = asyncio.run(generate_animation(
        args.input, args.output, args.text,
        duration=args.duration, fps=args.fps,
        black_opacity=args.black_opacity,
        subtitle_opacity=args.subtitle_opacity,
        font_path=args.font,
        vignette_strength=args.vignette,
        noise_amount=args.noise,
        swing_amplitude=args.swing_amp,
        subject_scale=args.subject_scale,
        total_frames=args.frames,
        top_dark_opacity=args.top_dark_opacity,
        line_prob=args.line_prob,
        line_count=args.line_count,
        line_width=args.line_width,
        line_jitter=args.line_jitter
        ,subtitle_padding=args.subtitle_padding
        ,subtitle_radius=args.subtitle_radius
        ,subtitle_feather=args.subtitle_feather
        ,subtitle_bg_alpha=args.subtitle_bg_alpha
        ,font_size=args.font_size
        ,fast_freq=args.fast_freq
        ,jitter_amp=args.jitter_amp
    ))
    print('已保存到:', out)
