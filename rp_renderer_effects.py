from __future__ import annotations

import math
import random
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from PIL import Image as PILImage
from PIL import ImageDraw, ImageEnhance, ImageFilter, ImageOps

if __package__:
    from .rp_renderer import RpImageRenderer as BaseRpImageRenderer
else:  # 兼容 local_test/preview.py 和直接运行测试
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
    def _daily_fields(rp_data: Mapping[str, Any]) -> tuple[dict[str, str], dict[str, str]]:
        raw_fields = rp_data.get("content_fields")
        if isinstance(raw_fields, Mapping):
            fields = {
                str(key): str(value)
                for key, value in raw_fields.items()
                if value not in (None, "")
            }
        else:
            known = (
                "fortune_text", "color", "advice_do", "advice_dont",
                "taiko_bpm", "taiko_stars", "taiko_advice", "today_events",
            )
            fields = {key: str(rp_data[key]) for key in known if rp_data.get(key)}
        default_labels = {
            "fortune_text": "今日签",
            "color": "幸运色",
            "advice_do": "宜",
            "advice_dont": "忌",
            "taiko_bpm": "推荐 BPM",
            "taiko_stars": "推荐星级",
            "taiko_advice": "太鼓建议",
            "today_events": "今日事件",
        }
        raw_labels = rp_data.get("content_labels")
        labels = {
            key: str(raw_labels.get(key) if isinstance(raw_labels, Mapping) else "")
            or default_labels.get(key)
            or key.replace("_", " ")
            for key in fields
        }
        return fields, labels

    @staticmethod
    def _daily_field_rows(fields: Mapping[str, str]) -> list[list[str]]:
        rows: list[list[str]] = []
        used: set[str] = set()
        for group in (
            ("fortune_text", "color"),
            ("advice_do", "advice_dont"),
            ("taiko_bpm", "taiko_stars"),
            ("taiko_advice",),
            ("today_events",),
        ):
            present = [key for key in group if key in fields]
            if present:
                rows.append(present)
                used.update(present)
        remaining = [key for key in fields if key not in used]
        rows.extend(remaining[index:index + 2] for index in range(0, len(remaining), 2))
        return rows

    @staticmethod
    def _rank_rgb(color: str) -> tuple[int, int, int]:
        color = str(color).strip().lstrip("#")
        if len(color) != 6:
            return 100, 116, 139
        try:
            return tuple(int(color[index:index + 2], 16) for index in (0, 2, 4))
        except ValueError:
            return 100, 116, 139

    @staticmethod
    def _soft_background(size: tuple[int, int]) -> PILImage.Image:
        """普通分数使用柔和渐变和虚化色块，避免大面积纯白。"""
        width, height = size
        background = PILImage.new("RGBA", size, (246, 248, 252, 255))
        draw = ImageDraw.Draw(background)
        start = (250, 251, 253)
        end = (237, 242, 248)
        for y in range(height):
            ratio = y / max(1, height - 1)
            color = tuple(
                round(start[channel] * (1 - ratio) + end[channel] * ratio)
                for channel in range(3)
            )
            draw.line((0, y, width, y), fill=(*color, 255))

        glow = PILImage.new("RGBA", size, (0, 0, 0, 0))
        glow_draw = ImageDraw.Draw(glow)
        glow_draw.ellipse(
            (width - 360, -150, width + 170, 350),
            fill=(124, 109, 250, 58),
        )
        glow_draw.ellipse(
            (-210, height - 380, 300, height + 100),
            fill=(14, 165, 233, 42),
        )
        glow_draw.ellipse(
            (width // 2 - 170, 155, width // 2 + 260, 540),
            fill=(251, 146, 60, 25),
        )
        glow = glow.filter(ImageFilter.GaussianBlur(72))
        return PILImage.alpha_composite(background, glow)

    @staticmethod
    def _draw_surface(
        canvas: PILImage.Image,
        box: tuple[int, int, int, int],
        radius: int,
        fill: tuple[int, int, int, int],
        outline: tuple[int, int, int, int],
        shadow: tuple[int, int, int, int] | None = None,
        accent: tuple[int, int, int, int] | None = None,
    ) -> None:
        overlay = PILImage.new("RGBA", canvas.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        left, top, right, bottom = box
        if shadow:
            draw.rounded_rectangle(
                (left, top + 7, right, bottom + 7),
                radius=radius,
                fill=shadow,
            )
        draw.rounded_rectangle(
            box,
            radius=radius,
            fill=fill,
            outline=outline,
            width=1,
        )
        if accent:
            draw.rounded_rectangle(
                (left + 1, top + 18, left + 7, bottom - 18),
                radius=3,
                fill=accent,
            )
        canvas.alpha_composite(overlay)

    def _draw_compact_signal(
        self,
        canvas: PILImage.Image,
        rp_value: int,
        box: tuple[int, int, int, int],
        is_static: bool,
    ) -> None:
        """低分不显示灰色评价 Logo，改为紧凑的信号仪表。"""
        left, top, right, bottom = box
        center_x = (left + right) // 2
        center_y = (top + bottom) // 2
        overlay = PILImage.new("RGBA", canvas.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        if is_static:
            draw.rounded_rectangle(
                box,
                radius=28,
                fill=(3, 5, 7, 202),
                outline=(244, 247, 250, 90),
                width=1,
            )
            label_font = self.font(29, bold=True)
            sub_font = self.font(12, bold=True)
            label = "NO SIGNAL"
            label_box = draw.textbbox((0, 0), label, font=label_font)
            x = center_x - (label_box[2] - label_box[0]) // 2
            y = center_y - 31
            draw.text((x - 3, y), label, font=label_font, fill=(0, 210, 220, 195))
            draw.text((x + 3, y), label, font=label_font, fill=(235, 45, 65, 195))
            draw.text((x, y), label, font=label_font, fill=(249, 250, 251, 255))
            sub_text = "RP CHANNEL / LOST"
            sub_box = draw.textbbox((0, 0), sub_text, font=sub_font)
            draw.text(
                (center_x - (sub_box[2] - sub_box[0]) // 2, center_y + 19),
                sub_text,
                font=sub_font,
                fill=(218, 224, 229, 255),
            )
            for offset in (-55, 49):
                draw.rectangle(
                    (left + 20, center_y + offset, right - 20, center_y + offset + 3),
                    fill=(235, 239, 242, 125),
                )
            for scan_y in range(top + 12, bottom - 10, 8):
                draw.line((left + 10, scan_y, right - 10, scan_y), fill=(0, 0, 0, 50))
            canvas.alpha_composite(overlay)
            return

        draw.rounded_rectangle(
            box,
            radius=28,
            fill=(241, 244, 248, 238),
            outline=(203, 211, 220, 220),
            width=1,
        )
        score_font = self.font(62, bold=True)
        score_text = f"{rp_value:02d}"
        score_box = draw.textbbox((0, 0), score_text, font=score_font)
        draw.text(
            (center_x - (score_box[2] - score_box[0]) // 2, top + 15),
            score_text,
            fill=(39, 48, 61, 255),
            font=score_font,
        )
        signal_font = self.font(12, bold=True)
        signal = "LOW RP SIGNAL"
        signal_box = draw.textbbox((0, 0), signal, font=signal_font)
        draw.text(
            (center_x - (signal_box[2] - signal_box[0]) // 2, top + 92),
            signal,
            fill=(100, 112, 128, 255),
            font=signal_font,
        )
        bar_count = 6
        active_count = max(1, math.ceil(rp_value / 50 * bar_count))
        bar_width = 14
        gap = 8
        start_x = center_x - (bar_count * bar_width + (bar_count - 1) * gap) // 2
        base_y = bottom - 20
        for index in range(bar_count):
            bar_height = 8 + index * 5
            color = (71, 85, 105, 255) if index < active_count else (199, 207, 217, 255)
            draw.rounded_rectangle(
                (
                    start_x + index * (bar_width + gap),
                    base_y - bar_height,
                    start_x + index * (bar_width + gap) + bar_width,
                    base_y,
                ),
                radius=4,
                fill=color,
            )
        canvas.alpha_composite(overlay)

    def render_rp_image(
        self, rp_data: Mapping[str, Any], output_path: str | Path | None = None
    ) -> Path:
        rp_value = int(rp_data["luck_value"])
        rank = self.rank_catalog.for_score(rp_value)
        icon_id = str(rp_data.get("rp_id") or rank.icon)
        user_name = str(rp_data.get("user_name", "???"))
        fields, labels = self._daily_fields(rp_data)

        is_static = rp_value == 0
        is_rainbow = rp_value == 100
        is_low = rp_value < 50
        is_special = is_static or is_rainbow
        width = self.canvas_width
        panel_margin = max(34, int(width * 0.055))
        content_width = width - panel_margin * 2
        card_gap = 14

        measurement = PILImage.new("RGB", (width, 8), "white")
        measure_draw = ImageDraw.Draw(measurement)
        meta_font = self.font(15, bold=True)
        kicker_font = self.font(18, bold=True)
        score_font = self.font(88, bold=True)
        rank_font = self.font(18, bold=True)
        greeting_font = self.font(min(self.desc_font_size, 25))
        section_font = self.font(22, bold=True)
        count_font = self.font(14, bold=True)
        label_font = self.font(16, bold=True)
        value_font = self.font(min(self.analysis_font_size, 23))
        value_line_height = max(value_font.size + 8, 30)
        label_height = max(20, label_font.size + 3)

        hero_top = 70
        hero_left = panel_margin
        hero_right = width - panel_margin
        visual_size = min(174, self.avatar_size)
        right_text_x = hero_left + 26 + visual_size + 32
        right_text_width = hero_right - right_text_x - 28
        greeting = f"Hi，{user_name}"
        greeting_lines = self._wrap_text(
            measure_draw,
            greeting,
            greeting_font,
            right_text_width,
        )
        hero_height = max(224, 180 + len(greeting_lines) * (greeting_font.size + 6))
        hero_bottom = hero_top + hero_height

        section_y = hero_bottom + 27
        cards_y = section_y + 39
        card_specs: list[dict[str, Any]] = []
        current_y = cards_y
        for row in self._daily_field_rows(fields):
            columns = len(row)
            card_width = content_width if columns == 1 else (content_width - card_gap) // 2
            measured_cards: list[tuple[str, list[str], int]] = []
            row_height = 0
            for field in row:
                lines = self._wrap_text(
                    measure_draw,
                    fields[field],
                    value_font,
                    card_width - 42,
                )
                card_height = 17 + label_height + 8 + len(lines) * value_line_height + 17
                measured_cards.append((field, lines, card_height))
                row_height = max(row_height, card_height)
            for column, (field, lines, _) in enumerate(measured_cards):
                left = panel_margin + column * (card_width + card_gap)
                card_specs.append(
                    {
                        "field": field,
                        "lines": lines,
                        "box": (left, current_y, left + card_width, current_y + row_height),
                    }
                )
            current_y += row_height + card_gap

        calculated_height = current_y - card_gap + 73
        height = max(self.canvas_height, calculated_height)
        size = (width, height)
        if is_rainbow:
            canvas = self._rainbow_background(size)
        elif is_static:
            canvas = self._static_background(size, seed=20260813)
        else:
            canvas = self._soft_background(size)

        rank_rgb = self._rank_rgb(rank.color)
        if is_static:
            primary = (246, 248, 250, 255)
            secondary = (205, 213, 222, 255)
            hero_fill = (3, 6, 9, 224)
            hero_outline = (240, 244, 248, 82)
            score_color = (248, 250, 252, 255)
        elif is_rainbow:
            primary = (20, 27, 39, 255)
            secondary = (62, 72, 89, 255)
            hero_fill = (255, 255, 255, 218)
            hero_outline = (255, 255, 255, 238)
            score_color = (18, 24, 35, 255)
        else:
            primary = (24, 32, 45, 255)
            secondary = (91, 104, 122, 255)
            hero_fill = (255, 255, 255, 238)
            hero_outline = (255, 255, 255, 255)
            score_color = (*rank_rgb, 255)

        draw = ImageDraw.Draw(canvas)
        brand = "TAIKO DAILY"
        current_date = datetime.now().strftime("%Y.%m.%d  %H:%M")
        date_box = draw.textbbox((0, 0), current_date, font=meta_font)
        if is_special:
            self._draw_surface(
                canvas,
                (panel_margin, 20, panel_margin + 145, 54),
                17,
                hero_fill,
                hero_outline,
            )
            self._draw_surface(
                canvas,
                (width - panel_margin - (date_box[2] - date_box[0]) - 24, 20, width - panel_margin, 54),
                17,
                hero_fill,
                hero_outline,
            )
            draw = ImageDraw.Draw(canvas)
        draw.text((panel_margin + (12 if is_special else 0), 29), brand, fill=secondary, font=meta_font)
        draw.text(
            (width - panel_margin - (date_box[2] - date_box[0]) - (12 if is_special else 0), 29),
            current_date,
            fill=secondary,
            font=meta_font,
        )

        self._draw_surface(
            canvas,
            (hero_left, hero_top, hero_right, hero_bottom),
            34,
            hero_fill,
            hero_outline,
            shadow=None if is_special else (43, 58, 78, 28),
            accent=(*rank_rgb, 235),
        )
        visual_top = hero_top + (hero_height - visual_size) // 2
        visual_box = (
            hero_left + 25,
            visual_top,
            hero_left + 25 + visual_size,
            visual_top + visual_size,
        )
        if is_low:
            self._draw_compact_signal(canvas, rp_value, visual_box, is_static)
        else:
            halo = PILImage.new("RGBA", canvas.size, (0, 0, 0, 0))
            halo_draw = ImageDraw.Draw(halo)
            halo_draw.ellipse(
                (
                    visual_box[0] - 7,
                    visual_box[1] - 7,
                    visual_box[2] + 7,
                    visual_box[3] + 7,
                ),
                fill=(*rank_rgb, 26 if not is_rainbow else 38),
                outline=(*rank_rgb, 58),
                width=2,
            )
            canvas.alpha_composite(halo)
            avatar = self._load_icon(icon_id, (visual_size, visual_size))
            if avatar:
                canvas.alpha_composite(avatar, (visual_box[0], visual_box[1]))
            else:
                error_font = self.font(18)
                error_text = "等级图加载失败"
                draw = ImageDraw.Draw(canvas)
                error_box = draw.textbbox((0, 0), error_text, font=error_font)
                draw.text(
                    (
                        (visual_box[0] + visual_box[2] - (error_box[2] - error_box[0])) // 2,
                        (visual_box[1] + visual_box[3]) // 2,
                    ),
                    error_text,
                    fill=(220, 70, 70, 255),
                    font=error_font,
                )

        draw = ImageDraw.Draw(canvas)
        draw.text((right_text_x, hero_top + 29), "今日 RP", fill=secondary, font=kicker_font)
        score_text = str(rp_value)
        score_box = draw.textbbox((0, 0), score_text, font=score_font)
        score_y = hero_top + 50
        if is_static:
            draw.text(
                (right_text_x - 3, score_y),
                score_text,
                fill=(0, 210, 220, 125),
                font=score_font,
            )
            draw.text(
                (right_text_x + 3, score_y),
                score_text,
                fill=(235, 45, 65, 125),
                font=score_font,
            )
        draw.text((right_text_x, score_y), score_text, fill=score_color, font=score_font)

        badge_text = "信号偏弱" if is_low else rank.name
        badge_box = draw.textbbox((0, 0), badge_text, font=rank_font)
        badge_left = min(
            right_text_x + (score_box[2] - score_box[0]) + 20,
            hero_right - (badge_box[2] - badge_box[0]) - 50,
        )
        badge_top = score_y + 40
        badge_overlay = PILImage.new("RGBA", canvas.size, (0, 0, 0, 0))
        badge_draw = ImageDraw.Draw(badge_overlay)
        badge_draw.rounded_rectangle(
            (
                badge_left,
                badge_top,
                badge_left + (badge_box[2] - badge_box[0]) + 26,
                badge_top + 34,
            ),
            radius=17,
            fill=(*rank_rgb, 32 if not is_static else 72),
            outline=(*rank_rgb, 95),
            width=1,
        )
        badge_draw.text(
            (badge_left + 13, badge_top + 6),
            badge_text,
            fill=(*rank_rgb, 255) if not is_static else primary,
            font=rank_font,
        )
        canvas.alpha_composite(badge_overlay)

        draw = ImageDraw.Draw(canvas)
        greeting_y = hero_bottom - 47 - max(0, len(greeting_lines) - 1) * (greeting_font.size + 6)
        line_y = greeting_y
        for line in greeting_lines:
            draw.text((right_text_x, line_y), line, fill=primary, font=greeting_font)
            line_y += greeting_font.size + 6

        section_label = "今日指引"
        draw.text((panel_margin, section_y), section_label, fill=primary, font=section_font)
        count_text = f"{len(fields)} 项"
        count_box = draw.textbbox((0, 0), count_text, font=count_font)
        count_left = width - panel_margin - (count_box[2] - count_box[0]) - 23
        count_overlay = PILImage.new("RGBA", canvas.size, (0, 0, 0, 0))
        count_draw = ImageDraw.Draw(count_overlay)
        count_draw.rounded_rectangle(
            (count_left, section_y - 2, width - panel_margin, section_y + 28),
            radius=15,
            fill=hero_fill if is_special else (255, 255, 255, 184),
            outline=hero_outline if is_special else (214, 222, 232, 190),
            width=1,
        )
        count_draw.text(
            (count_left + 11, section_y + 4),
            count_text,
            fill=secondary,
            font=count_font,
        )
        canvas.alpha_composite(count_overlay)

        themes = {
            "fortune_text": ((217, 134, 18), (255, 249, 235, 246)),
            "color": ((124, 83, 215), (249, 246, 255, 246)),
            "advice_do": ((22, 143, 86), (240, 252, 246, 246)),
            "advice_dont": ((211, 62, 67), (255, 245, 245, 246)),
            "taiko_bpm": ((14, 137, 165), (239, 251, 253, 246)),
            "taiko_stars": ((225, 100, 34), (255, 247, 239, 246)),
            "taiko_advice": ((45, 101, 214), (242, 247, 255, 246)),
            "today_events": ((119, 73, 194), (248, 244, 255, 246)),
        }
        for spec in card_specs:
            field = spec["field"]
            left, top, right, bottom = spec["box"]
            accent_rgb, tint = themes.get(
                field,
                ((100, 116, 139), (248, 250, 252, 246)),
            )
            if is_static:
                card_fill = (3, 6, 9, 224)
                card_outline = (238, 242, 246, 68)
                card_shadow = None
            elif is_rainbow:
                card_fill = (255, 255, 255, 222)
                card_outline = (255, 255, 255, 244)
                card_shadow = None
            else:
                card_fill = tint
                card_outline = (*accent_rgb, 35)
                card_shadow = (42, 56, 76, 20)
            self._draw_surface(
                canvas,
                (left, top, right, bottom),
                21,
                card_fill,
                card_outline,
                shadow=card_shadow,
                accent=(*accent_rgb, 220),
            )
            draw = ImageDraw.Draw(canvas)
            dot_y = top + 18 + label_font.size // 2
            draw.ellipse(
                (left + 19, dot_y - 4, left + 27, dot_y + 4),
                fill=(*accent_rgb, 255),
            )
            draw.text(
                (left + 35, top + 16),
                labels[field],
                fill=(*accent_rgb, 255),
                font=label_font,
            )
            value_y = top + 17 + label_height + 8
            for line in spec["lines"]:
                draw.text((left + 20, value_y), line, fill=primary, font=value_font)
                value_y += value_line_height

        footer_y = height - 34
        if is_special:
            self._draw_surface(
                canvas,
                (panel_margin, footer_y - 8, width - panel_margin, footer_y + 22),
                15,
                hero_fill,
                hero_outline,
            )
        draw = ImageDraw.Draw(canvas)
        footer_font = self.font(13, bold=True)
        footer_left = "TAIKO RP · DAILY FORTUNE"
        version_text = f"CONTENT V{int(rp_data.get('content_schema_version', 1))}"
        version_box = draw.textbbox((0, 0), version_text, font=footer_font)
        draw.text(
            (panel_margin + (12 if is_special else 0), footer_y),
            footer_left,
            fill=secondary,
            font=footer_font,
        )
        draw.text(
            (
                width - panel_margin - (version_box[2] - version_box[0]) - (12 if is_special else 0),
                footer_y,
            ),
            version_text,
            fill=secondary,
            font=footer_font,
        )
        return self._save(canvas, output_path)
