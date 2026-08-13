"""测试专用 RP 布局试验场，不会修改正式渲染逻辑。

用法：
    python local_test/layout_lab.py
    python local_test/layout_lab.py --score 88 --variants D3A D3B D3C
"""

from __future__ import annotations

import argparse
import random
import sys
from datetime import datetime
from pathlib import Path
from typing import Mapping

from PIL import Image, ImageDraw, ImageFilter


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from rp_core import ContentStore, RankCatalog, select_content_path  # noqa: E402
from rp_renderer_effects import RpImageRenderer  # noqa: E402


VARIANTS = {
    "D3A": "平衡横幅",
    "D3B": "宽屏横幅",
    "D3C": "舒展横幅",
}
VARIANT_SIZES = {
    "D3A": (1000, 650),
    "D3B": (1080, 610),
    "D3C": (960, 680),
}
FIELD_COLORS = {
    "fortune_text": (221, 143, 24),
    "color": (129, 92, 222),
    "advice_do": (27, 151, 94),
    "advice_dont": (220, 70, 76),
    "taiko_bpm": (15, 143, 171),
    "taiko_stars": (230, 109, 42),
    "taiko_advice": (52, 108, 220),
    "today_events": (126, 78, 202),
}


class LayoutLab(RpImageRenderer):
    WIDTH = 800
    HEIGHT = 960

    def background(self, score: int) -> Image.Image:
        size = (self.WIDTH, self.HEIGHT)
        if score == 0:
            return self._static_background(size, seed=20260813)
        if score == 100:
            return self._rainbow_background(size)
        return self._soft_background(size)

    def center_text(self, draw, text: str, y: int, font, fill) -> None:
        box = draw.textbbox((0, 0), text, font=font)
        draw.text(((self.WIDTH - box[2] + box[0]) // 2, y), text, font=font, fill=fill)

    def adaptive_font(
        self, draw, text: str, width: int, max_size: int, min_size: int, max_lines: int
    ):
        """优先使用大字号，仅在内容超出指定行数时逐级缩小。"""
        for size in range(max_size, min_size - 1, -1):
            font = self.font(size)
            lines = self._wrap_text(draw, text, font, width)
            if len(lines) <= max_lines:
                return font, lines
        font = self.font(min_size)
        return font, self._wrap_text(draw, text, font, width)


    def pill(self, canvas, box, text: str, font, fill, text_fill, outline=None) -> None:
        layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(layer)
        draw.rounded_rectangle(
            box, radius=(box[3] - box[1]) // 2, fill=fill, outline=outline, width=1
        )
        text_box = draw.textbbox((0, 0), text, font=font)
        draw.text(
            (
                (box[0] + box[2] - text_box[2] + text_box[0]) // 2,
                box[1] + (box[3] - box[1] - text_box[3] + text_box[1]) // 2 - 1,
            ),
            text,
            font=font,
            fill=text_fill,
        )
        canvas.alpha_composite(layer)

    def logo_stage(self, canvas, icon_id: str, y: int, size: int, accent, style: str) -> None:
        cx = self.WIDTH // 2
        layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(layer)
        if style == "monument":
            for extra, alpha in ((42, 18), (20, 42)):
                draw.ellipse(
                    (cx - size // 2 - extra, y - size // 2 - extra,
                     cx + size // 2 + extra, y + size // 2 + extra),
                    fill=(*accent, alpha), outline=(*accent, alpha + 25), width=2,
                )
        elif style == "stage":
            draw.ellipse((cx - 260, y - 180, cx + 260, y + 175), fill=(*accent, 30))
            draw.rounded_rectangle(
                (cx - 286, y - 155, cx + 286, y + 155),
                radius=58, fill=(255, 255, 255, 204), outline=(255, 255, 255, 242),
            )
        elif style == "editorial":
            draw.rounded_rectangle(
                (cx - 205, y - 167, cx + 205, y + 167),
                radius=62, fill=(255, 255, 255, 224), outline=(*accent, 62), width=2,
            )
            draw.rectangle((cx - 205, y + 130, cx + 205, y + 167), fill=(*accent, 218))
        else:
            for radius, alpha in ((184, 38), (156, 58), (128, 30)):
                draw.ellipse(
                    (cx - radius, y - radius, cx + radius, y + radius),
                    outline=(*accent, alpha), width=2,
                )
            draw.ellipse((cx - 124, y - 124, cx + 124, y + 124), fill=(255, 255, 255, 214))
        if style in {"monument", "stage"}:
            layer = layer.filter(ImageFilter.GaussianBlur(0.35))
        canvas.alpha_composite(layer)
        icon = self._load_icon(icon_id, (size, size))
        if icon:
            canvas.alpha_composite(icon, (cx - size // 2, y - size // 2))

    def card(self, canvas, box, field: str, text: str, label: str, dark=False, compact=False):
        accent = FIELD_COLORS.get(field, (100, 116, 139))
        fill = (5, 9, 14, 222) if dark else (255, 255, 255, 230)
        outline = (238, 242, 246, 65) if dark else (*accent, 42)
        primary = (246, 248, 250, 255) if dark else (27, 35, 48, 255)
        self._draw_surface(
            canvas, box, 18 if compact else 22, fill, outline,
            shadow=None if dark else (39, 52, 72, 19), accent=(*accent, 225),
        )
        draw = ImageDraw.Draw(canvas)
        label_font = self.font(14 if compact else 15, bold=True)
        value_font = self.font(18 if compact else 20)
        draw.ellipse((box[0] + 16, box[1] + 18, box[0] + 24, box[1] + 26), fill=(*accent, 255))
        draw.text((box[0] + 31, box[1] + 13), label, font=label_font, fill=(*accent, 255))
        lines = self._wrap_text(draw, text, value_font, box[2] - box[0] - 36)
        y = box[1] + 43
        for line in lines[:2]:
            draw.text((box[0] + 18, y), line, font=value_font, fill=primary)
            y += value_font.size + 6

    def grid(self, canvas, fields, labels, top: int, left=34, width=732, compact=False, dark=False):
        gap, y = 12, top
        for row in self._daily_field_rows(fields):
            card_width = width if len(row) == 1 else (width - gap) // 2
            row_height = 82 if compact else (92 if len(row) == 2 else 98)
            for column, field in enumerate(row):
                x = left + column * (card_width + gap)
                self.card(
                    canvas, (x, y, x + card_width, y + row_height),
                    field, fields[field], labels[field], dark, compact,
                )
            y += row_height + gap
        return y

    def meta(self, canvas, code: str, dark=False):
        draw = ImageDraw.Draw(canvas)
        font = self.font(13, bold=True)
        fill = (210, 218, 227, 255) if dark else (83, 95, 112, 255)
        draw.text((30, 25), f"{code} · {VARIANTS[code]}", font=font, fill=fill)
        date_text = datetime.now().strftime("%Y.%m.%d")
        date_box = draw.textbbox((0, 0), date_text, font=font)
        draw.text((self.WIDTH - 30 - date_box[2] + date_box[0], 25), date_text, font=font, fill=fill)

    def footer(self, canvas, code: str, dark=False):
        draw = ImageDraw.Draw(canvas)
        font = self.font(12, bold=True)
        fill = (194, 203, 213, 255) if dark else (112, 124, 141, 255)
        draw.text((32, self.HEIGHT - 35), "LAYOUT LAB · NOT PRODUCTION", font=font, fill=fill)
        text = f"{code} / CONTENT V2"
        box = draw.textbbox((0, 0), text, font=font)
        draw.text((self.WIDTH - 32 - box[2] + box[0], self.HEIGHT - 35), text, font=font, fill=fill)

    def radial_item(
        self,
        canvas,
        field: str,
        text: str,
        label: str,
        x: int,
        y: int,
        width: int,
        side: str,
        dark: bool,
    ) -> None:
        """环绕 Logo 的无框字段，字号随内容长度自适应。"""
        draw = ImageDraw.Draw(canvas)
        accent = FIELD_COLORS.get(field, (100, 116, 139))
        primary = (246, 248, 250, 255) if dark else (27, 35, 48, 255)
        label_font = self.font(15, bold=True)
        value_font, lines = self.adaptive_font(draw, text, width, 26, 18, 2)
        label_box = draw.textbbox((0, 0), label, font=label_font)
        label_x = x if side == "left" else x + width - label_box[2] + label_box[0]
        draw.text((label_x, y), label, font=label_font, fill=(*accent, 255))
        value_y = y + 27
        for line in lines[:2]:
            line_box = draw.textbbox((0, 0), line, font=value_font)
            line_x = x if side == "left" else x + width - line_box[2] + line_box[0]
            draw.text((line_x, value_y), line, font=value_font, fill=primary)
            value_y += value_font.size + 5


    def long_item(
        self,
        canvas,
        field: str,
        text: str,
        label: str,
        x: int,
        y: int,
        width: int,
        dark: bool,
    ) -> None:
        """底部长字段：无容器，字号随内容长度自适应，最多三行。"""
        draw = ImageDraw.Draw(canvas)
        accent = FIELD_COLORS.get(field, (100, 116, 139))
        primary = (246, 248, 250, 255) if dark else (27, 35, 48, 255)
        label_font = self.font(16, bold=True)
        value_font, lines = self.adaptive_font(draw, text, width, 27, 18, 3)
        title = f"●  {label}"
        title_box = draw.textbbox((0, 0), title, font=label_font)
        title_x = (
            x + width - title_box[2] + title_box[0]
            if field == "today_events"
            else x
        )
        draw.text((title_x, y), title, font=label_font, fill=(*accent, 255))
        value_y = y + 31
        for line in lines[:3]:
            draw.text((x, value_y), line, font=value_font, fill=primary)
            value_y += value_font.size + 7


    def logo_focus(self, canvas, icon_id: str, center_y: int, size: int, accent, dark=False):
        cx = self.WIDTH // 2
        layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(layer)
        draw.ellipse(
            (cx - size // 2 - 58, center_y - size // 2 - 58,
             cx + size // 2 + 58, center_y + size // 2 + 58),
            fill=(255, 255, 255, 20 if dark else 112),
        )
        draw.ellipse(
            (cx - size // 2 - 28, center_y - size // 2 - 28,
             cx + size // 2 + 28, center_y + size // 2 + 28),
            fill=(*accent, 25),
        )
        layer = layer.filter(ImageFilter.GaussianBlur(20))
        canvas.alpha_composite(layer)
        icon = self._load_icon(icon_id, (size, size))
        if icon:
            canvas.alpha_composite(icon, (cx - size // 2, center_y - size // 2))

    def content_height(self, code: str, fields: Mapping[str, str]) -> int:
        """根据底部长字段的实际行数收紧画布，同时保留页脚安全距离。"""
        center_y = {"D3A": 246, "D3B": 224, "D3C": 260}[code]
        logo_size = {"D3A": 230, "D3B": 220, "D3C": 238}[code]
        long_top = center_y + logo_size // 2 + 48
        long_width = (self.WIDTH - 38 * 2 - 44) // 2
        today_x = self.WIDTH // 2 + logo_size // 2 + 18
        today_width = self.WIDTH - 38 - today_x
        measure = ImageDraw.Draw(Image.new("RGB", (1, 1)))
        bottoms = []
        for field, width in (("taiko_advice", long_width), ("today_events", today_width)):
            font, lines = self.adaptive_font(
                measure, fields[field], width, 27, 18, 3
            )
            line_count = min(len(lines), 3)
            bottoms.append(long_top + 31 + (font.size + 7) * line_count)
        return min(self.HEIGHT, max(bottoms) + 75)


    def render_variant(self, code: str, rp_data: Mapping, output_path: Path) -> Path:
        code = code.upper()
        self.WIDTH, self.HEIGHT = VARIANT_SIZES[code]
        score = int(rp_data["luck_value"])
        rank = self.rank_catalog.for_score(score)
        accent = self._rank_rgb(rank.color)
        icon_id = str(rp_data.get("rp_id") or rank.icon)
        user_name = str(rp_data.get("user_name") or "布局试验用户")
        fields, labels = self._daily_fields(rp_data)
        self.HEIGHT = self.content_height(code, fields)
        canvas = self.background(score)
        dark = score == 0
        primary = (246, 248, 250, 255) if dark else (24, 32, 45, 255)
        secondary = (202, 211, 221, 255) if dark else (88, 101, 120, 255)
        self.meta(canvas, code, dark)
        draw = ImageDraw.Draw(canvas)

        cx = self.WIDTH // 2
        center_y = {"D3A": 246, "D3B": 224, "D3C": 260}[code]
        logo_size = {"D3A": 230, "D3B": 220, "D3C": 238}[code]
        self.logo_focus(canvas, icon_id, center_y, logo_size, accent, dark)
        draw = ImageDraw.Draw(canvas)

        score_font = self.font(30, bold=True)
        logo_top = center_y - logo_size // 2
        self.center_text(draw, f"RP {score}", logo_top - 45, score_font, (*accent, 255))
        self.center_text(draw, f"Hi，{user_name}", center_y + logo_size // 2 + 12, self.font(18), secondary)

        side_margin = 38
        center_gap = logo_size // 2 + 70
        side_width = cx - center_gap - side_margin
        row_offsets = (-116, -12, 92)
        pairs = (
            ("fortune_text", "color"),
            ("advice_do", "advice_dont"),
            ("taiko_bpm", "taiko_stars"),
        )
        for row_offset, (left_field, right_field) in zip(row_offsets, pairs):
            item_y = center_y + row_offset - 24
            self.radial_item(
                canvas, left_field, fields[left_field], labels[left_field],
                side_margin, item_y, side_width, "left", dark,
            )
            self.radial_item(
                canvas, right_field, fields[right_field], labels[right_field],
                cx + center_gap, item_y, side_width, "right", dark,
            )

        long_top = center_y + logo_size // 2 + 48
        long_gap = 44
        long_width = (self.WIDTH - side_margin * 2 - long_gap) // 2
        today_x = self.WIDTH // 2 + logo_size // 2 + 18
        today_width = self.WIDTH - side_margin - today_x
        self.long_item(
            canvas, "taiko_advice", fields["taiko_advice"], labels["taiko_advice"],
            side_margin, long_top, long_width, dark,
        )
        self.long_item(
            canvas, "today_events", fields["today_events"], labels["today_events"],
            today_x, long_top, today_width, dark,
        )

        self.footer(canvas, code, dark)
        return self._save(canvas, output_path)

def contact_sheet(items: list[tuple[str, Path]], destination: Path) -> Path:
    cell_width, cell_height = 520, 370
    margin, gap, label_height = 20, 16, 42
    sheet = Image.new(
        "RGB",
        (margin * 2 + cell_width * 2 + gap, margin * 2 + (cell_height + label_height) * 2 + gap),
        "#E9EEF5",
    )
    draw = ImageDraw.Draw(sheet)
    for index, (code, path) in enumerate(items):
        row, column = divmod(index, 2)
        x = margin + column * (cell_width + gap)
        y = margin + row * (cell_height + label_height + gap)
        with Image.open(path) as source:
            actual_size = source.size
            source.thumbnail((cell_width, cell_height), Image.Resampling.LANCZOS)
            thumb = source.convert("RGB")
        paste_x = x + (cell_width - thumb.width) // 2
        paste_y = y + label_height + (cell_height - thumb.height) // 2
        sheet.paste(thumb, (paste_x, paste_y))
        draw.rounded_rectangle((x, y, x + cell_width, y + 35), radius=14, fill="#172033")
        draw.text((x + 15, y + 8), f"{code}  {VARIANTS[code]}  {actual_size[0]}×{actual_size[1]}", fill="white")
    destination.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(destination, format="PNG", optimize=True)
    return destination

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="生成带代号的 RP 布局试验图")
    parser.add_argument("--score", type=int, default=88, help="RP 值，默认 88")
    parser.add_argument("--user-name", default="布局试验用户", help="预览用户名")
    parser.add_argument(
        "--variants", nargs="+", default=list(VARIANTS), choices=list(VARIANTS)
    )
    parser.add_argument("--seed", type=int, default=20260813)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parent / "layout_lab_output",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if not 0 <= args.score <= 100:
        raise SystemExit("RP 值必须位于 0~100")
    resource = PROJECT_ROOT / "resource"
    ranks = RankCatalog.from_file(resource / "ranks.json")
    content = ContentStore.from_file(select_content_path(resource))
    renderer = LayoutLab(resource, ranks)
    rng = random.Random(args.seed)
    record = content.make_fortune(args.score, rng)
    record.update(
        {
            "user_name": args.user_name,
            "rp_id": ranks.result_icon_for_score(args.score, rng),
        }
    )
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    generated = []
    for code in args.variants:
        path = renderer.render_variant(
            code, record, output_dir / f"layout_{code}_rp_{args.score:03d}.png"
        )
        generated.append((code, path))
    overview = contact_sheet(
        generated, output_dir / f"layout_overview_rp_{args.score:03d}.png"
    )
    print(f"布局试验生成完成（RP={args.score}，同一组抽取内容）：")
    for code, path in generated:
        print(f"  {code} {VARIANTS[code]}：{path}")
    print(f"  总览：{overview}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
