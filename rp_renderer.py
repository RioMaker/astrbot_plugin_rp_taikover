from __future__ import annotations

import colorsys
import math
import random
import tempfile
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping, Sequence

from PIL import Image as PILImage
from PIL import ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

if __package__:
    from .rp_core import RankCatalog, RankDefinition
else:  # 兼容 local_test/preview.py 和直接运行测试
    from rp_core import RankCatalog, RankDefinition


class RpImageRenderer:
    """与 AstrBot 解耦的 RP 图片渲染器，可被插件和本地预览程序共同调用。"""

    def __init__(
        self,
        resource_dir: str | Path,
        rank_catalog: RankCatalog,
        config: Mapping[str, Any] | None = None,
    ):
        self.resource_dir = Path(resource_dir)
        self.image_dir = self.resource_dir / "image"
        self.font_dir = self.resource_dir / "font"
        self.rank_catalog = rank_catalog
        config = config or {}
        self.canvas_width = int(config.get("CANVAS_WIDTH", 800))
        self.canvas_height = int(config.get("CANVAS_HEIGHT", 800))
        self.avatar_size = int(config.get("AVATAR_SIZE", 280))
        self.spacing_avatar_name = int(config.get("SPACING_AVATAR_NAME", 20))
        self.spacing_name_desc = int(config.get("SPACING_NAME_DESC", 25))
        self.spacing_desc_analysis = int(config.get("SPACING_DESC_ANALYSIS", 30))
        self.desc_font_size = int(config.get("DESC_FONT_SIZE", 32))
        self.analysis_font_size = int(config.get("ANALYSIS_FONT_SIZE", 28))
        self.analysis_line_height_factor = float(config.get("ANALYSIS_LINE_HEIGHT_FACTOR", 1.6))
        self.analysis_width_ratio = float(config.get("ANALYSIS_WIDTH_RATIO", 0.85))
        self.name_font_size = int(config.get("NAME_FONT_SIZE", 66))

    @lru_cache(maxsize=32)
    def font(self, size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
        names = (
            ("荆南麦圆体.otf", "SourceHanSansCN-Bold.otf")
            if bold
            else ("可爱字体.ttf", "SourceHanSansCN-Regular.otf")
        )
        system_candidates = (
            ["C:/Windows/Fonts/msyhbd.ttc", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]
            if bold
            else ["C:/Windows/Fonts/msyh.ttc", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]
        )
        candidates = [self.font_dir / name for name in names] + [Path(path) for path in system_candidates]
        for path in candidates:
            if path.exists():
                try:
                    return ImageFont.truetype(str(path), size)
                except OSError:
                    continue
        return ImageFont.load_default(size=size)

    def find_image_file(self, image_id: str) -> Path | None:
        for extension in ("png", "jpg", "jpeg", "webp", "gif"):
            path = self.image_dir / f"{image_id}.{extension}"
            if path.exists():
                return path
        return None

    @staticmethod
    def _temporary_png() -> Path:
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as temp_file:
            return Path(temp_file.name)

    @staticmethod
    def _save(canvas: PILImage.Image, output_path: str | Path | None) -> Path:
        path = Path(output_path) if output_path else RpImageRenderer._temporary_png()
        path.parent.mkdir(parents=True, exist_ok=True)
        canvas.convert("RGB").save(path, format="PNG", optimize=True)
        return path

    def _rainbow_background(self, size: tuple[int, int]) -> PILImage.Image:
        width, height = size
        stripe = PILImage.new("RGB", (width, 1))
        pixels = []
        for x in range(width):
            hue = (x / max(1, width - 1) * 0.92) % 1.0
            red, green, blue = colorsys.hsv_to_rgb(hue, 0.58, 1.0)
            pixels.append((int(red * 255), int(green * 255), int(blue * 255)))
        stripe.putdata(pixels)
        background = stripe.resize((width, height))
        overlay = PILImage.new("RGBA", size, (255, 255, 255, 0))
        overlay_draw = ImageDraw.Draw(overlay)
        for index, radius in enumerate((250, 190, 140)):
            cx = int(width * (0.2 + index * 0.3))
            cy = int(height * (0.25 + (index % 2) * 0.45))
            overlay_draw.ellipse(
                (cx - radius, cy - radius, cx + radius, cy + radius),
                fill=(255, 255, 255, 30),
            )
        return PILImage.alpha_composite(background.convert("RGBA"), overlay)

    def _static_background(self, size: tuple[int, int], seed: int = 0) -> PILImage.Image:
        width, height = size
        rng = random.Random(seed)
        noise = PILImage.frombytes("L", size, rng.randbytes(width * height))
        noise = ImageEnhance.Contrast(noise).enhance(1.8)
        background = ImageOps.colorize(noise, black="#070809", white="#A9ADB0").convert("RGBA")
        scanlines = PILImage.new("RGBA", size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(scanlines)
        for y in range(0, height, 4):
            draw.line((0, y, width, y), fill=(0, 0, 0, 72), width=1)
        for _ in range(max(8, height // 40)):
            y = rng.randrange(height)
            segment_width = rng.randrange(max(20, width // 10), max(21, width // 2))
            x = rng.randrange(max(1, width - segment_width))
            shade = rng.choice((20, 235))
            draw.rectangle((x, y, x + segment_width, y + rng.randrange(1, 5)), fill=(shade, shade, shade, 100))
        return PILImage.alpha_composite(background, scanlines)

    def _daily_background(self, rp_value: int) -> PILImage.Image:
        size = (self.canvas_width, self.canvas_height)
        if rp_value == 100:
            return self._rainbow_background(size)
        if rp_value == 0:
            return self._static_background(size, seed=20260813)
        return PILImage.new("RGBA", size, (255, 255, 255, 255))

    @staticmethod
    def _wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, width: int) -> list[str]:
        lines: list[str] = []
        for source_line in str(text).splitlines() or [""]:
            current = ""
            for char in source_line:
                candidate = current + char
                bbox = draw.textbbox((0, 0), candidate, font=font)
                if current and bbox[2] - bbox[0] > width:
                    lines.append(current)
                    current = char
                else:
                    current = candidate
            lines.append(current)
        return lines or [""]

    def _wrap_daily_description(
        self,
        draw: ImageDraw.ImageDraw,
        user_name: str,
        fortune_text: str,
        lucky_color: str,
        font: ImageFont.FreeTypeFont,
        width: int,
    ) -> str:
        """将每日信息分段并限制行宽，避免幸运色等长文本越出画布。"""
        sections = (
            f"Hi~ “{user_name}”",
            f"今日签：{fortune_text}",
            f"幸运色：{lucky_color}",
        )
        lines = [
            line
            for section in sections
            for line in self._wrap_text(draw, section, font, width)
        ]
        return "\n".join(lines)

    def _load_icon(self, image_id: str, size: tuple[int, int]) -> PILImage.Image | None:
        path = self.find_image_file(image_id)
        if not path:
            return None
        try:
            with PILImage.open(path) as source:
                image = source.convert("RGBA")
            return ImageOps.contain(image, size, method=PILImage.Resampling.LANCZOS)
        except OSError:
            return None

    def render_rp_image(self, rp_data: Mapping[str, Any], output_path: str | Path | None = None) -> Path:
        rp_value = int(rp_data["luck_value"])
        rank = self.rank_catalog.for_score(rp_value)
        icon_id = str(rp_data.get("rp_id") or rank.icon)
        user_name = str(rp_data.get("user_name", "???"))
        canvas = self._daily_background(rp_value)
        draw = ImageDraw.Draw(canvas)

        is_static = rp_value == 0
        panel_margin = max(24, int(self.canvas_width * 0.055))
        panel_box = (
            panel_margin,
            max(42, int(self.canvas_height * 0.055)),
            self.canvas_width - panel_margin,
            self.canvas_height - panel_margin,
        )
        if rp_value == 100:
            draw.rounded_rectangle(panel_box, radius=36, fill=(255, 255, 255, 218), outline=(255, 255, 255, 235), width=2)
        elif is_static:
            draw.rounded_rectangle(panel_box, radius=30, fill=(8, 10, 12, 218), outline=(220, 225, 230, 145), width=2)

        primary = (244, 246, 248, 255) if is_static else (18, 23, 31, 255)
        secondary = (205, 211, 217, 255) if is_static else (78, 85, 96, 255)
        date_font = self.font(16)
        current_date = datetime.now().strftime("%Y.%m.%d %H:%M:%S")
        draw.text((panel_margin + 18, panel_box[1] + 14), current_date, fill=secondary, font=date_font)

        avatar_size = min(self.avatar_size, int(self.canvas_width * 0.42), int(self.canvas_height * 0.38))
        avatar = self._load_icon(icon_id, (avatar_size, avatar_size))
        avatar_height = avatar.height if avatar else avatar_size
        name_font = self.font(self.name_font_size, bold=True)
        desc_font = self.font(self.desc_font_size)
        analysis_font = self.font(self.analysis_font_size)
        rp_name = f"【今日 RP 值：{rp_value}】"
        max_text_width = int(self.canvas_width * self.analysis_width_ratio)
        description = self._wrap_daily_description(
            draw,
            user_name,
            str(rp_data["fortune_text"]),
            str(rp_data["color"]),
            desc_font,
            max_text_width,
        )
        analysis = f"宜：{rp_data['advice_do']}\n忌：{rp_data['advice_dont']}"
        analysis_lines = self._wrap_text(draw, analysis, analysis_font, max_text_width)
        line_height = max(int(self.analysis_font_size * self.analysis_line_height_factor), self.analysis_font_size + 6)

        name_bbox = draw.textbbox((0, 0), rp_name, font=name_font)
        name_height = name_bbox[3] - name_bbox[1]
        desc_bbox = draw.multiline_textbbox((0, 0), description, font=desc_font, spacing=8, align="center")
        desc_height = desc_bbox[3] - desc_bbox[1]
        analysis_height = len(analysis_lines) * line_height
        total_height = (
            avatar_height
            + self.spacing_avatar_name
            + name_height
            + self.spacing_name_desc
            + desc_height
            + self.spacing_desc_analysis
            + analysis_height
        )
        start_y = max(panel_box[1] + 48, (self.canvas_height - total_height) // 2 + 12)

        if avatar:
            avatar_x = (self.canvas_width - avatar.width) // 2
            canvas.alpha_composite(avatar, (avatar_x, start_y))
        else:
            error_font = self.font(24)
            error_text = "等级图片加载失败"
            error_bbox = draw.textbbox((0, 0), error_text, font=error_font)
            draw.text(((self.canvas_width - (error_bbox[2] - error_bbox[0])) // 2, start_y + avatar_height // 2), error_text, fill=(230, 60, 60, 255), font=error_font)

        name_y = start_y + avatar_height + self.spacing_avatar_name
        name_bbox = draw.textbbox((0, 0), rp_name, font=name_font)
        name_x = (self.canvas_width - (name_bbox[2] - name_bbox[0])) // 2
        draw.text((name_x, name_y), rp_name, fill=primary, font=name_font, stroke_width=1)

        desc_y = name_y + name_height + self.spacing_name_desc
        desc_bbox = draw.multiline_textbbox((0, 0), description, font=desc_font, spacing=8, align="center")
        desc_x = (self.canvas_width - (desc_bbox[2] - desc_bbox[0])) // 2
        draw.multiline_text((desc_x, desc_y), description, fill=secondary, font=desc_font, spacing=8, align="center")

        analysis_y = desc_y + desc_height + self.spacing_desc_analysis
        for line in analysis_lines:
            bbox = draw.textbbox((0, 0), line, font=analysis_font)
            draw.text(((self.canvas_width - (bbox[2] - bbox[0])) // 2, analysis_y), line, fill=primary, font=analysis_font)
            analysis_y += line_height

        return self._save(canvas, output_path)

    def _prepare_leaderboard_avatar(
        self,
        source: Any,
        user_name: str,
        size: int,
    ) -> PILImage.Image:
        avatar: PILImage.Image | None = None
        try:
            if isinstance(source, PILImage.Image):
                avatar = source.convert("RGBA")
            elif source:
                with PILImage.open(Path(source)) as image:
                    avatar = image.convert("RGBA")
            if avatar is not None:
                avatar = ImageOps.fit(
                    avatar,
                    (size, size),
                    method=PILImage.Resampling.LANCZOS,
                )
        except (OSError, TypeError, ValueError):
            avatar = None

        if avatar is None:
            hue = sum(ord(char) for char in user_name) % 360 / 360
            red, green, blue = colorsys.hsv_to_rgb(hue, 0.45, 0.82)
            avatar = PILImage.new(
                "RGBA",
                (size, size),
                (int(red * 255), int(green * 255), int(blue * 255), 255),
            )
            placeholder_draw = ImageDraw.Draw(avatar)
            initial = (user_name.strip() or "?")[0].upper()
            initial_font = self.font(max(20, size // 2), bold=True)
            initial_box = placeholder_draw.textbbox((0, 0), initial, font=initial_font)
            placeholder_draw.text(
                (
                    (size - (initial_box[2] - initial_box[0])) // 2,
                    (size - (initial_box[3] - initial_box[1])) // 2 - initial_box[1],
                ),
                initial,
                fill=(255, 255, 255, 245),
                font=initial_font,
            )

        mask_scale = 4
        mask = PILImage.new("L", (size * mask_scale, size * mask_scale), 0)
        ImageDraw.Draw(mask).ellipse((0, 0, size * mask_scale - 1, size * mask_scale - 1), fill=255)
        mask = mask.resize((size, size), PILImage.Resampling.LANCZOS)
        avatar.putalpha(ImageChops.multiply(avatar.getchannel("A"), mask))
        return avatar

    @staticmethod
    def _truncate_text(
        draw: ImageDraw.ImageDraw,
        text: str,
        font: ImageFont.FreeTypeFont,
        max_width: int,
    ) -> str:
        text = str(text)
        if draw.textbbox((0, 0), text, font=font)[2] <= max_width:
            return text
        suffix = "…"
        shortened = text
        while shortened:
            shortened = shortened[:-1]
            candidate = shortened + suffix
            if draw.textbbox((0, 0), candidate, font=font)[2] <= max_width:
                return candidate
        return suffix

    def render_leaderboard_image(
        self,
        group_name: str,
        entries: Sequence[Mapping[str, Any]],
        output_path: str | Path | None = None,
    ) -> Path:
        """生成按成员数量自动增长的群 RP 排行榜长图。"""
        width = 960
        header_height = 176
        row_height = 112
        footer_height = 60
        height = header_height + len(entries) * row_height + footer_height
        canvas = PILImage.new("RGBA", (width, height), "#F2F5FA")
        draw = ImageDraw.Draw(canvas)

        draw.rectangle((0, 0, width, 150), fill="#111827")
        draw.ellipse((width - 230, -125, width + 55, 160), fill="#1D4ED8")
        draw.ellipse((width - 125, -50, width + 95, 170), fill="#7C3AED")
        title_font = self.font(44, bold=True)
        subtitle_font = self.font(20)
        draw.text((44, 35), "群 RP 排行榜", fill="#FFFFFF", font=title_font)
        subtitle = f"{group_name} · {datetime.now().strftime('%Y.%m.%d')} · {len(entries)} 人上榜"
        subtitle = self._truncate_text(draw, subtitle, subtitle_font, 790)
        draw.text((47, 96), subtitle, fill="#CBD5E1", font=subtitle_font)

        name_font = self.font(27, bold=True)
        detail_font = self.font(17)
        position_font = self.font(25, bold=True)
        score_font = self.font(38, bold=True)
        score_label_font = self.font(15, bold=True)
        crown_ids = ("hongguan", "jinguan", "yinguan")
        position_colors = ("#F97316", "#EAB308", "#94A3B8")
        top_card_colors = ("#FFF7ED", "#FFFBEB", "#F8FAFC")

        for index, entry in enumerate(entries):
            position = index + 1
            row_start = header_height + index * row_height
            card_top = row_start + 8
            card_bottom = card_top + 96
            card_fill = top_card_colors[index] if index < 3 else "#FFFFFF"
            draw.rounded_rectangle(
                (32, card_top, width - 32, card_bottom),
                radius=22,
                fill=card_fill,
                outline="#E5EAF1",
                width=1,
            )

            badge_color = position_colors[index] if index < 3 else "#E8EDF4"
            badge_text_color = "#FFFFFF" if index < 3 else "#526071"
            badge_box = (50, card_top + 29, 92, card_top + 71)
            draw.ellipse(badge_box, fill=badge_color)
            position_text = str(position)
            position_box = draw.textbbox((0, 0), position_text, font=position_font)
            draw.text(
                (
                    (badge_box[0] + badge_box[2] - (position_box[2] - position_box[0])) // 2,
                    (badge_box[1] + badge_box[3] - (position_box[3] - position_box[1])) // 2
                    - position_box[1],
                ),
                position_text,
                fill=badge_text_color,
                font=position_font,
            )

            avatar_size = 68
            avatar_x = 116
            avatar_y = card_top + 14
            ring_color = position_colors[index] if index < 3 else "#D6DEE9"
            draw.ellipse(
                (avatar_x - 3, avatar_y - 3, avatar_x + avatar_size + 3, avatar_y + avatar_size + 3),
                fill=ring_color,
            )
            avatar = self._prepare_leaderboard_avatar(
                entry.get("avatar_path") or entry.get("avatar"),
                str(entry.get("user_name") or entry.get("user_id") or "?"),
                avatar_size,
            )
            canvas.alpha_composite(avatar, (avatar_x, avatar_y))

            if index < 3:
                crown = self._load_icon(crown_ids[index], (52, 52))
                if crown:
                    # 王冠中心沿头像左上方 45° 方向外移，并保留部分重叠。
                    crown_x = avatar_x - crown.width // 2
                    crown_y = avatar_y - crown.height // 2
                    canvas.alpha_composite(crown, (crown_x, crown_y))

            user_name = str(entry.get("user_name") or entry.get("user_id") or "未知用户")
            user_name = self._truncate_text(draw, user_name, name_font, 470)
            text_x = 212
            draw.text((text_x, card_top + 20), user_name, fill="#172033", font=name_font)
            score = int(entry.get("luck_value", 0))
            rank = self.rank_catalog.for_score(score)
            detail = f"UID {entry.get('user_id', '')} · {rank.name}"
            detail = self._truncate_text(draw, detail, detail_font, 500)
            draw.text((text_x, card_top + 59), detail, fill="#7B8798", font=detail_font)

            score_text = str(score)
            score_box = draw.textbbox((0, 0), score_text, font=score_font)
            score_right = width - 62
            score_x = score_right - (score_box[2] - score_box[0])
            draw.text((score_x, card_top + 17), score_text, fill=rank.color, font=score_font)
            label_box = draw.textbbox((0, 0), "RP", font=score_label_font)
            draw.text(
                (score_right - (label_box[2] - label_box[0]), card_top + 65),
                "RP",
                fill="#9AA5B4",
                font=score_label_font,
            )

        footer_y = height - footer_height
        draw.text(
            (44, footer_y + 19),
            f"今日已抽取 RP 的群成员 · 当前显示 {len(entries)} 人",
            fill="#7C8797",
            font=detail_font,
        )
        return self._save(canvas, output_path)

    def render_statistics_image(
        self,
        user_name: str,
        records: Sequence[Mapping[str, Any]],
        rank_counts: Mapping[str, int],
        output_path: str | Path | None = None,
    ) -> Path:
        width, height = 1200, 1040
        canvas = PILImage.new("RGBA", (width, height), "#F3F6FA")
        draw = ImageDraw.Draw(canvas)
        title_font = self.font(44, bold=True)
        subtitle_font = self.font(22)
        metric_font = self.font(24, bold=True)
        body_font = self.font(20)
        small_font = self.font(16)

        draw.text((60, 36), f"{user_name} 的 RP 统计", fill="#18212F", font=title_font)
        total_count = sum(int(value) for value in rank_counts.values())
        draw.text((62, 94), f"折线展示近 {len(records)} 次记录 · 等级统计累计 {total_count} 次", fill="#667085", font=subtitle_font)

        scores = [int(record["luck_value"]) for record in records]
        if scores:
            metrics = (
                ("平均", f"{sum(scores) / len(scores):.1f}"),
                ("最高", str(max(scores))),
                ("最低", str(min(scores))),
            )
            metric_x = 728
            for label, value in metrics:
                draw.rounded_rectangle((metric_x, 44, metric_x + 126, 118), radius=18, fill="#FFFFFF")
                draw.text((metric_x + 16, 56), label, fill="#7A8493", font=small_font)
                draw.text((metric_x + 16, 78), value, fill="#1E293B", font=metric_font)
                metric_x += 142

        chart_box = (60, 150, 1140, 610)
        draw.rounded_rectangle(chart_box, radius=26, fill="#FFFFFF")
        plot_left, plot_top, plot_right, plot_bottom = 108, 190, 1110, 548
        for tick in (0, 25, 50, 75, 100):
            y = plot_bottom - int((plot_bottom - plot_top) * tick / 100)
            draw.line((plot_left, y, plot_right, y), fill="#E6EAF0", width=2)
            label = str(tick)
            label_box = draw.textbbox((0, 0), label, font=small_font)
            draw.text((plot_left - 16 - (label_box[2] - label_box[0]), y - 9), label, fill="#8791A1", font=small_font)

        if scores:
            denominator = max(1, len(scores) - 1)
            points = [
                (
                    plot_left + int((plot_right - plot_left) * index / denominator),
                    plot_bottom - int((plot_bottom - plot_top) * score / 100),
                )
                for index, score in enumerate(scores)
            ]
            if len(points) > 1:
                polygon = points + [(points[-1][0], plot_bottom), (points[0][0], plot_bottom)]
                fill_layer = PILImage.new("RGBA", canvas.size, (0, 0, 0, 0))
                ImageDraw.Draw(fill_layer).polygon(polygon, fill=(79, 128, 255, 30))
                canvas = PILImage.alpha_composite(canvas, fill_layer)
                draw = ImageDraw.Draw(canvas)
                draw.line(points, fill="#4F80FF", width=5, joint="curve")
            for point, score in zip(points, scores):
                rank = self.rank_catalog.for_score(score)
                draw.ellipse((point[0] - 7, point[1] - 7, point[0] + 7, point[1] + 7), fill=rank.color, outline="#FFFFFF", width=3)

            label_indexes = sorted({0, len(records) - 1, *range(4, len(records), 5)})
            for index in label_indexes:
                date_text = str(records[index].get("date", ""))[5:].replace("-", "/")
                bbox = draw.textbbox((0, 0), date_text, font=small_font)
                x = points[index][0] - (bbox[2] - bbox[0]) // 2
                draw.text((x, plot_bottom + 18), date_text, fill="#8791A1", font=small_font)
        else:
            empty_text = "暂无 RP 记录"
            bbox = draw.textbbox((0, 0), empty_text, font=metric_font)
            draw.text(((width - (bbox[2] - bbox[0])) // 2, 350), empty_text, fill="#98A2B3", font=metric_font)

        draw.text((62, 638), "等级累计", fill="#253044", font=self.font(28, bold=True))
        card_left, card_top = 60, 686
        card_width, card_height, gap_x, gap_y = 270, 142, 20, 20
        ordered_ranks = sorted(self.rank_catalog.ranks, key=lambda item: item.max_rp, reverse=True)
        for index, rank in enumerate(ordered_ranks):
            row, column = divmod(index, 4)
            x = card_left + column * (card_width + gap_x)
            y = card_top + row * (card_height + gap_y)
            draw.rounded_rectangle((x, y, x + card_width, y + card_height), radius=22, fill="#FFFFFF")
            icon = self._load_icon(rank.icon, (82, 72))
            if icon:
                icon_x = x + 18 + (82 - icon.width) // 2
                icon_y = y + 17 + (72 - icon.height) // 2
                canvas.alpha_composite(icon, (icon_x, icon_y))
            name_x = x + 112
            draw.text((name_x, y + 24), rank.name, fill="#374151", font=body_font)
            count_text = f"{int(rank_counts.get(rank.id, 0))} 次"
            draw.text((name_x, y + 57), count_text, fill=rank.color, font=self.font(30, bold=True))
            range_text = f"RP {rank.min_rp}" if rank.min_rp == rank.max_rp else f"RP {rank.min_rp}–{rank.max_rp}"
            draw.text((name_x, y + 101), range_text, fill="#98A2B3", font=small_font)

        return self._save(canvas, output_path)
