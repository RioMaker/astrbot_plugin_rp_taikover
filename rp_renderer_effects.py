from __future__ import annotations

import math
import random
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from PIL import Image as PILImage
from PIL import ImageDraw, ImageEnhance, ImageOps

from rp_renderer import RpImageRenderer as BaseRpImageRenderer


class RpImageRenderer(BaseRpImageRenderer):
    """全画布特殊效果与低分信号仪表版渲染器。"""

    def __init__(self, resource_dir, rank_catalog, config=None):
        super().__init__(resource_dir, rank_catalog, config)
        config = config or {}
        # 可在 AstrBot 插件配置中修改：值越大，RP=0 的雪花颗粒越粗。
        self.static_block_size = max(4, min(40, int(config.get("STATIC_BLOCK_SIZE", 12))))
        # 横向撕裂/故障块数量。
        self.static_glitch_bands = max(5, min(60, int(config.get("STATIC_GLITCH_BANDS", 24))))

    def _static_background(self, size: tuple[int, int], seed: int = 0) -> PILImage.Image:
        width, height = size
        rng = random.Random(seed)
        noise_width = math.ceil(width / self.static_block_size)
        noise_height = math.ceil(height / self.static_block_size)
        coarse_noise = PILImage.frombytes(
            "L", (noise_width, noise_height), rng.randbytes(noise_width * noise_height)
        )
        coarse_noise = ImageEnhance.Contrast(coarse_noise).enhance(2.35)
        coarse_noise = coarse_noise.resize(size, PILImage.Resampling.NEAREST)
        background = ImageOps.colorize(
            coarse_noise, black="#050607", white="#B8BDC2"
        ).convert("RGBA")

        effects = PILImage.new("RGBA", size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(effects)
        # 宽故障带横跨画布主体，避免特效只剩边缘可见。
        for _ in range(self.static_glitch_bands):
            y = rng.randrange(height)
            band_height = rng.randrange(5, 20)
            x = rng.randrange(-width // 5, width // 3)
            segment_width = rng.randrange(width // 3, width + width // 3)
            shade = rng.choice((8, 30, 215, 245))
            alpha = rng.randrange(75, 175)
            draw.rectangle(
                (x, y, x + segment_width, y + band_height),
                fill=(shade, shade, shade, alpha),
            )
        for y in range(0, height, 6):
            draw.line((0, y, width, y), fill=(0, 0, 0, 72), width=2)
        for _ in range(7):
            y = rng.randrange(height)
            draw.rectangle((0, y, width, y + rng.randrange(2, 7)), fill=(3, 4, 5, 175))
        return PILImage.alpha_composite(background, effects)

    @staticmethod
    def _rounded_overlay(
        canvas: PILImage.Image,
        box: tuple[int, int, int, int],
        radius: int,
        fill: tuple[int, int, int, int],
        outline: tuple[int, int, int, int] | None = None,
        width: int = 1,
    ) -> None:
        overlay = PILImage.new("RGBA", canvas.size, (0, 0, 0, 0))
        ImageDraw.Draw(overlay).rounded_rectangle(
            box, radius=radius, fill=fill, outline=outline, width=width
        )
        canvas.alpha_composite(overlay)

    def _draw_low_rp_signal(
        self,
        canvas: PILImage.Image,
        rp_value: int,
        top: int,
        height: int,
        is_static: bool,
    ) -> None:
        """RP<50 使用信号视觉，完全不加载灰色评价 Logo。"""
        center_x = self.canvas_width // 2
        center_y = top + height // 2
        if is_static:
            self._rounded_overlay(
                canvas,
                (center_x - 238, top + 5, center_x + 238, top + height - 5),
                radius=25,
                fill=(3, 5, 7, 150),
                outline=(230, 235, 240, 95),
            )
            draw = ImageDraw.Draw(canvas)
            label_font = self.font(54, bold=True)
            sub_font = self.font(19, bold=True)
            label = "NO SIGNAL"
            bbox = draw.textbbox((0, 0), label, font=label_font)
            x = center_x - (bbox[2] - bbox[0]) // 2
            # RGB 分离故障字，不依赖任何图片资源。
            draw.text((x - 5, center_y - 48), label, font=label_font, fill=(0, 210, 220, 185))
            draw.text((x + 5, center_y - 48), label, font=label_font, fill=(225, 35, 50, 185))
            draw.text((x, center_y - 48), label, font=label_font, fill=(246, 248, 250, 255))
            sub_text = "RP CHANNEL / LOST"
            sub_bbox = draw.textbbox((0, 0), sub_text, font=sub_font)
            draw.text(
                (center_x - (sub_bbox[2] - sub_bbox[0]) // 2, center_y + 28),
                sub_text,
                font=sub_font,
                fill=(218, 224, 229, 255),
            )
            for offset in (-70, 55):
                draw.rectangle(
                    (center_x - 190, center_y + offset, center_x + 190, center_y + offset + 5),
                    fill=(235, 239, 242, 155),
                )
            return

        card_box = (center_x - 192, top + 8, center_x + 192, top + height - 8)
        self._rounded_overlay(
            canvas,
            card_box,
            radius=30,
            fill=(238, 241, 244, 230),
            outline=(190, 197, 206, 175),
            width=2,
        )
        draw = ImageDraw.Draw(canvas)
        score_font = self.font(72, bold=True)
        small_font = self.font(18, bold=True)
        score_text = f"{rp_value:02d}"
        score_bbox = draw.textbbox((0, 0), score_text, font=score_font)
        draw.text(
            (center_x - (score_bbox[2] - score_bbox[0]) // 2, top + 20),
            score_text,
            fill=(42, 49, 58, 255),
            font=score_font,
        )
        signal_text = "LOW RP SIGNAL"
        signal_bbox = draw.textbbox((0, 0), signal_text, font=small_font)
        draw.text(
            (center_x - (signal_bbox[2] - signal_bbox[0]) // 2, top + 105),
            signal_text,
            fill=(91, 100, 112, 255),
            font=small_font,
        )
        bar_count = 7
        active_count = max(1, math.ceil(rp_value / 50 * bar_count))
        total_width = 202
        bar_width = 20
        gap = (total_width - bar_count * bar_width) // (bar_count - 1)
        start_x = center_x - total_width // 2
        base_y = top + height - 27
        for index in range(bar_count):
            bar_height = 12 + index * 6
            color = (62, 70, 80, 255) if index < active_count else (190, 197, 205, 255)
            draw.rounded_rectangle(
                (
                    start_x + index * (bar_width + gap),
                    base_y - bar_height,
                    start_x + index * (bar_width + gap) + bar_width,
                    base_y,
                ),
                radius=5,
                fill=color,
            )

    def render_rp_image(
        self, rp_data: Mapping[str, Any], output_path: str | Path | None = None
    ) -> Path:
        rp_value = int(rp_data["luck_value"])
        rank = self.rank_catalog.for_score(rp_value)
        icon_id = str(rp_data.get("rp_id") or rank.icon)
        user_name = str(rp_data.get("user_name", "???"))
        canvas = self._daily_background(rp_value)
        draw = ImageDraw.Draw(canvas)

        is_static = rp_value == 0
        is_rainbow = rp_value == 100
        is_low = rp_value < 50
        is_special = is_static or is_rainbow
        panel_margin = max(24, int(self.canvas_width * 0.055))
        primary = (244, 246, 248, 255) if is_static else (18, 23, 31, 255)
        secondary = (218, 224, 229, 255) if is_static else (70, 78, 90, 255)
        special_fill = (3, 5, 7, 188) if is_static else (255, 255, 255, 205)
        special_outline = (230, 235, 240, 95) if is_static else (255, 255, 255, 225)

        date_font = self.font(16)
        current_date = datetime.now().strftime("%Y.%m.%d %H:%M:%S")
        date_bbox = draw.textbbox((0, 0), current_date, font=date_font)
        date_pos = (panel_margin, 22)
        if is_special:
            self._rounded_overlay(
                canvas,
                (
                    date_pos[0] - 11,
                    date_pos[1] - 7,
                    date_pos[0] + (date_bbox[2] - date_bbox[0]) + 11,
                    date_pos[1] + (date_bbox[3] - date_bbox[1]) + 9,
                ),
                radius=12,
                fill=special_fill,
                outline=special_outline,
            )
            draw = ImageDraw.Draw(canvas)
        draw.text(date_pos, current_date, fill=secondary, font=date_font)

        avatar_size = min(
            self.avatar_size, int(self.canvas_width * 0.42), int(self.canvas_height * 0.38)
        )
        avatar = None if is_low else self._load_icon(icon_id, (avatar_size, avatar_size))
        hero_height = 190 if is_low else (avatar.height if avatar else avatar_size)
        name_font = self.font(self.name_font_size, bold=True)
        desc_font = self.font(self.desc_font_size)
        analysis_font = self.font(self.analysis_font_size)
        rp_name = f"【今日 RP 值：{rp_value}】"
        description = (
            f"Hi~ “{user_name}”\n"
            f"今日签：{rp_data['fortune_text']}　幸运色：{rp_data['color']}"
        )
        analysis = f"宜：{rp_data['advice_do']}\n忌：{rp_data['advice_dont']}"
        max_text_width = int(self.canvas_width * self.analysis_width_ratio)
        analysis_lines = self._wrap_text(draw, analysis, analysis_font, max_text_width)
        line_height = max(
            int(self.analysis_font_size * self.analysis_line_height_factor),
            self.analysis_font_size + 6,
        )

        name_bbox = draw.textbbox((0, 0), rp_name, font=name_font)
        name_width = name_bbox[2] - name_bbox[0]
        name_height = name_bbox[3] - name_bbox[1]
        desc_bbox = draw.multiline_textbbox(
            (0, 0), description, font=desc_font, spacing=8, align="center"
        )
        desc_width = desc_bbox[2] - desc_bbox[0]
        desc_height = desc_bbox[3] - desc_bbox[1]
        analysis_height = len(analysis_lines) * line_height
        total_height = (
            hero_height
            + self.spacing_avatar_name
            + name_height
            + self.spacing_name_desc
            + desc_height
            + self.spacing_desc_analysis
            + analysis_height
        )
        start_y = max(66, (self.canvas_height - total_height) // 2 + 18)

        if is_low:
            self._draw_low_rp_signal(canvas, rp_value, start_y, hero_height, is_static)
        elif avatar:
            avatar_x = (self.canvas_width - avatar.width) // 2
            canvas.alpha_composite(avatar, (avatar_x, start_y))
        else:
            error_font = self.font(24)
            error_text = "等级图片加载失败"
            error_bbox = draw.textbbox((0, 0), error_text, font=error_font)
            draw.text(
                (
                    (self.canvas_width - (error_bbox[2] - error_bbox[0])) // 2,
                    start_y + hero_height // 2,
                ),
                error_text,
                fill=(230, 60, 60, 255),
                font=error_font,
            )

        name_y = start_y + hero_height + self.spacing_avatar_name
        name_x = (self.canvas_width - name_width) // 2
        desc_y = name_y + name_height + self.spacing_name_desc
        desc_x = (self.canvas_width - desc_width) // 2
        analysis_y = desc_y + desc_height + self.spacing_desc_analysis

        # 特效背景完全保留，仅在文字附近放置局部可读性底板。
        if is_special:
            padding_x, padding_y = 24, 13
            self._rounded_overlay(
                canvas,
                (
                    name_x - padding_x,
                    name_y - padding_y,
                    name_x + name_width + padding_x,
                    name_y + name_height + padding_y,
                ),
                radius=18,
                fill=special_fill,
                outline=special_outline,
            )
            self._rounded_overlay(
                canvas,
                (
                    desc_x - padding_x,
                    desc_y - padding_y,
                    desc_x + desc_width + padding_x,
                    desc_y + desc_height + padding_y,
                ),
                radius=18,
                fill=special_fill,
                outline=special_outline,
            )
            widest_analysis = max(
                (draw.textbbox((0, 0), line, font=analysis_font)[2] for line in analysis_lines),
                default=0,
            )
            analysis_x = (self.canvas_width - widest_analysis) // 2
            self._rounded_overlay(
                canvas,
                (
                    analysis_x - padding_x,
                    analysis_y - padding_y,
                    analysis_x + widest_analysis + padding_x,
                    analysis_y + analysis_height + padding_y - 5,
                ),
                radius=18,
                fill=special_fill,
                outline=special_outline,
            )

        draw = ImageDraw.Draw(canvas)
        draw.text((name_x, name_y), rp_name, fill=primary, font=name_font, stroke_width=1)
        draw.multiline_text(
            (desc_x, desc_y),
            description,
            fill=secondary,
            font=desc_font,
            spacing=8,
            align="center",
        )
        for line in analysis_lines:
            bbox = draw.textbbox((0, 0), line, font=analysis_font)
            draw.text(
                ((self.canvas_width - (bbox[2] - bbox[0])) // 2, analysis_y),
                line,
                fill=primary,
                font=analysis_font,
            )
            analysis_y += line_height

        return self._save(canvas, output_path)
