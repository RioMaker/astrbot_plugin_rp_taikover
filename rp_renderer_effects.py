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

    DAILY_FIELD_COLORS = {
        "fortune_text": (221, 143, 24),
        "color": (129, 92, 222),
        "advice_do": (27, 151, 94),
        "advice_dont": (220, 70, 76),
        "taiko_bpm": (15, 143, 171),
        "taiko_stars": (230, 109, 42),
        "taiko_advice": (52, 108, 220),
        "today_events": (126, 78, 202),
    }

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

    @staticmethod
    def _center_daily_text(draw, width: int, text: str, y: int, font, fill, stroke_fill=None) -> None:
        box = draw.textbbox((0, 0), text, font=font)
        draw.text(
            ((width - (box[2] - box[0])) // 2, y),
            text,
            font=font,
            fill=fill,
            stroke_width=2 if stroke_fill else 0,
            stroke_fill=stroke_fill,
        )

    def _adaptive_daily_font(
        self,
        draw,
        text: str,
        width: int,
        max_size: int,
        min_size: int,
        max_lines: int,
        bold: bool = False,
    ):
        """正常内容优先用大字号，只在超出目标行数时逐级缩小。"""
        for size in range(max_size, min_size - 1, -1):
            font = self.font(size, bold=bold)
            lines = self._wrap_text(draw, text, font, width)
            if len(lines) <= max_lines:
                return font, lines
        font = self.font(min_size, bold=bold)
        return font, self._wrap_text(draw, text, font, width)

    def _draw_daily_focus(
        self,
        canvas: PILImage.Image,
        icon_id: str,
        rp_value: int,
        center_y: int,
        size: int,
        accent: tuple[int, int, int],
        dark: bool,
    ) -> None:
        center_x = canvas.width // 2
        halo = PILImage.new("RGBA", canvas.size, (0, 0, 0, 0))
        halo_draw = ImageDraw.Draw(halo)
        halo_draw.ellipse(
            (
                center_x - size // 2 - 58,
                center_y - size // 2 - 58,
                center_x + size // 2 + 58,
                center_y + size // 2 + 58,
            ),
            fill=(255, 255, 255, 20 if dark else 112),
        )
        halo_draw.ellipse(
            (
                center_x - size // 2 - 28,
                center_y - size // 2 - 28,
                center_x + size // 2 + 28,
                center_y + size // 2 + 28,
            ),
            fill=(*accent, 25),
        )
        canvas.alpha_composite(halo.filter(ImageFilter.GaussianBlur(20)))

        if rp_value < 50:
            self._draw_compact_signal(
                canvas,
                rp_value,
                (
                    center_x - size // 2,
                    center_y - 74,
                    center_x + size // 2,
                    center_y + 74,
                ),
                rp_value == 0,
            )
            return

        icon = self._load_icon(icon_id, (size, size))
        if icon:
            canvas.alpha_composite(icon, (center_x - size // 2, center_y - size // 2))
            return
        draw = ImageDraw.Draw(canvas)
        error_font = self.font(16)
        self._center_daily_text(
            draw, canvas.width, "等级图加载失败", center_y - 9, error_font, (220, 70, 70, 255)
        )

    def _draw_daily_radial_item(
        self,
        canvas: PILImage.Image,
        field: str,
        text: str,
        label: str,
        x: int,
        y: int,
        width: int,
        side: str,
        font,
        lines: list[str],
        primary,
        stroke_fill=None,
    ) -> None:
        draw = ImageDraw.Draw(canvas)
        accent = self.DAILY_FIELD_COLORS.get(field, (100, 116, 139))
        label_font = self.font(15, bold=True)
        label_box = draw.textbbox((0, 0), label, font=label_font)
        label_x = x if side == "left" else x + width - (label_box[2] - label_box[0])
        draw.text(
            (label_x, y), label, font=label_font, fill=(*accent, 255),
            stroke_width=2 if stroke_fill else 0, stroke_fill=stroke_fill,
        )
        value_y = y + 27
        for line in lines:
            line_box = draw.textbbox((0, 0), line, font=font)
            line_x = x if side == "left" else x + width - (line_box[2] - line_box[0])
            draw.text(
                (line_x, value_y), line, font=font, fill=primary,
                stroke_width=2 if stroke_fill else 0, stroke_fill=stroke_fill,
            )
            value_y += font.size + 5

    def _draw_daily_long_item(
        self,
        canvas: PILImage.Image,
        field: str,
        text: str,
        label: str,
        x: int,
        y: int,
        width: int,
        font,
        lines: list[str],
        primary,
        title_right: bool = False,
        stroke_fill=None,
    ) -> None:
        draw = ImageDraw.Draw(canvas)
        accent = self.DAILY_FIELD_COLORS.get(field, (100, 116, 139))
        label_font = self.font(16, bold=True)
        title = f"●  {label}"
        title_box = draw.textbbox((0, 0), title, font=label_font)
        title_x = x + width - (title_box[2] - title_box[0]) if title_right else x
        draw.text(
            (title_x, y), title, font=label_font, fill=(*accent, 255),
            stroke_width=2 if stroke_fill else 0, stroke_fill=stroke_fill,
        )
        value_y = y + 31
        for line in lines:
            draw.text(
                (x, value_y), line, font=font, fill=primary,
                stroke_width=2 if stroke_fill else 0, stroke_fill=stroke_fill,
            )
            value_y += font.size + 7

    def render_rp_image(
        self, rp_data: Mapping[str, Any], output_path: str | Path | None = None
    ) -> Path:
        rp_value = int(rp_data["luck_value"])
        rank = self.rank_catalog.for_score(rp_value)
        icon_id = str(rp_data.get("rp_id") or rank.icon)
        user_name = str(rp_data.get("user_name") or "???")
        fields, labels = self._daily_fields(rp_data)

        width = max(960, self.canvas_width)
        center_x = width // 2
        center_y = 260
        logo_size = 238
        side_margin = 38
        center_gap = logo_size // 2 + 70
        side_width = center_x - center_gap - side_margin
        long_top = center_y + logo_size // 2 + 48
        long_gap = 44
        long_width = (width - side_margin * 2 - long_gap) // 2
        today_x = center_x + logo_size // 2 + 18
        today_width = width - side_margin - today_x

        measure = ImageDraw.Draw(PILImage.new("RGB", (width, 8), "white"))
        radial_pairs = (
            ("fortune_text", "color"),
            ("advice_do", "advice_dont"),
            ("taiko_bpm", "taiko_stars"),
        )
        row_offsets = (-116, -12, 92)
        radial_specs: list[dict[str, Any]] = []
        overflow_fields: list[str] = []
        radial_known = {field for pair in radial_pairs for field in pair}
        for row_offset, pair in zip(row_offsets, radial_pairs):
            for side, field in zip(("left", "right"), pair):
                if field not in fields:
                    continue
                font, lines = self._adaptive_daily_font(
                    measure, fields[field], side_width, 26, 18, 2
                )
                if len(lines) > 2:
                    overflow_fields.append(field)
                    continue
                radial_specs.append(
                    {
                        "field": field,
                        "side": side,
                        "x": side_margin if side == "left" else center_x + center_gap,
                        "y": center_y + row_offset - 24,
                        "font": font,
                        "lines": lines,
                    }
                )

        bottom_specs: list[dict[str, Any]] = []
        bottom_edges: list[int] = []
        for field, x, field_width, title_right in (
            ("taiko_advice", side_margin, long_width, False),
            ("today_events", today_x, today_width, True),
        ):
            if field not in fields:
                continue
            font, lines = self._adaptive_daily_font(
                measure, fields[field], field_width, 27, 18, 3
            )
            spec = {
                "field": field,
                "x": x,
                "y": long_top,
                "width": field_width,
                "font": font,
                "lines": lines,
                "title_right": title_right,
            }
            bottom_specs.append(spec)
            bottom_edges.append(long_top + 31 + len(lines) * (font.size + 7))

        handled = radial_known | {"taiko_advice", "today_events"}
        extra_fields = overflow_fields + [
            field for field in fields if field not in handled and field not in overflow_fields
        ]
        extra_y = max(bottom_edges, default=long_top) + (18 if bottom_edges else 0)
        extra_width = width - side_margin * 2
        for field in extra_fields:
            font, lines = self._adaptive_daily_font(
                measure, fields[field], extra_width, 27, 18, 3
            )
            bottom_specs.append(
                {
                    "field": field,
                    "x": side_margin,
                    "y": extra_y,
                    "width": extra_width,
                    "font": font,
                    "lines": lines,
                    "title_right": False,
                }
            )
            extra_y += 31 + len(lines) * (font.size + 7) + 18
            bottom_edges.append(extra_y - 18)

        content_bottom = max(bottom_edges, default=long_top)
        height = max(520, content_bottom + 75)
        size = (width, height)
        is_static = rp_value == 0
        is_rainbow = rp_value == 100
        if is_rainbow:
            canvas = self._rainbow_background(size)
        elif is_static:
            canvas = self._static_background(size, seed=20260813)
        else:
            canvas = self._soft_background(size)

        rank_rgb = self._rank_rgb(rank.color)
        if is_static:
            primary = (246, 248, 250, 255)
            secondary = (210, 218, 227, 255)
            score_color = (248, 250, 252, 255)
            stroke_fill = (0, 0, 0, 215)
        elif is_rainbow:
            primary = (20, 27, 39, 255)
            secondary = (62, 72, 89, 255)
            score_color = (18, 24, 35, 255)
            stroke_fill = (255, 255, 255, 205)
        else:
            primary = (24, 32, 45, 255)
            secondary = (88, 101, 120, 255)
            score_color = (*rank_rgb, 255)
            stroke_fill = None

        draw = ImageDraw.Draw(canvas)
        meta_font = self.font(13, bold=True)
        brand = "TAIKO DAILY"
        current_date = datetime.now().strftime("%Y.%m.%d")
        date_box = draw.textbbox((0, 0), current_date, font=meta_font)
        draw.text(
            (30, 25), brand, font=meta_font, fill=secondary,
            stroke_width=2 if stroke_fill else 0, stroke_fill=stroke_fill,
        )
        draw.text(
            (width - 30 - (date_box[2] - date_box[0]), 25),
            current_date,
            font=meta_font,
            fill=secondary,
            stroke_width=2 if stroke_fill else 0,
            stroke_fill=stroke_fill,
        )

        self._draw_daily_focus(
            canvas, icon_id, rp_value, center_y, logo_size, rank_rgb, is_static
        )
        draw = ImageDraw.Draw(canvas)
        score_font = self.font(30, bold=True)
        logo_top = center_y - logo_size // 2
        self._center_daily_text(
            draw, width, f"RP {rp_value}", logo_top - 45, score_font, score_color, stroke_fill
        )
        greeting_font, greeting_lines = self._adaptive_daily_font(
            draw, f"Hi，{user_name}", logo_size + 90, 18, 14, 2
        )
        greeting_y = center_y + logo_size // 2 + 12
        for line in greeting_lines[:2]:
            self._center_daily_text(
                draw, width, line, greeting_y, greeting_font, secondary, stroke_fill
            )
            greeting_y += greeting_font.size + 5

        for spec in radial_specs:
            field = spec["field"]
            self._draw_daily_radial_item(
                canvas,
                field,
                fields[field],
                labels[field],
                spec["x"],
                spec["y"],
                side_width,
                spec["side"],
                spec["font"],
                spec["lines"],
                primary,
                stroke_fill,
            )

        for spec in bottom_specs:
            field = spec["field"]
            self._draw_daily_long_item(
                canvas,
                field,
                fields[field],
                labels[field],
                spec["x"],
                spec["y"],
                spec["width"],
                spec["font"],
                spec["lines"],
                primary,
                spec["title_right"],
                stroke_fill,
            )

        draw = ImageDraw.Draw(canvas)
        footer_font = self.font(12, bold=True)
        footer_y = height - 35
        footer_left = "TAIKO RP · DAILY FORTUNE"
        version_text = f"CONTENT V{int(rp_data.get('content_schema_version', 1))}"
        version_box = draw.textbbox((0, 0), version_text, font=footer_font)
        draw.text(
            (32, footer_y), footer_left, font=footer_font, fill=secondary,
            stroke_width=2 if stroke_fill else 0, stroke_fill=stroke_fill,
        )
        draw.text(
            (width - 32 - (version_box[2] - version_box[0]), footer_y),
            version_text,
            font=footer_font,
            fill=secondary,
            stroke_width=2 if stroke_fill else 0,
            stroke_fill=stroke_fill,
        )
        return self._save(canvas, output_path)
