import random
from datetime import date, timedelta
from pathlib import Path

from PIL import Image, ImageDraw

from rp_core import ContentStore, RankCatalog, count_scores_by_rank, select_content_path
from rp_renderer_effects import RpImageRenderer
from local_test.layout_lab import LayoutLab, VARIANTS, VARIANT_SIZES


ROOT = Path(__file__).resolve().parents[1]


def renderer_and_data():
    resource = ROOT / "resource"
    ranks = RankCatalog.from_file(resource / "ranks.json")
    content = ContentStore.from_file(select_content_path(resource))
    return RpImageRenderer(resource, ranks), ranks, content


def test_special_backgrounds_and_normal_image_render(tmp_path):
    renderer, ranks, content = renderer_and_data()
    paths = {}
    for score in (0, 50, 100):
        record = content.make_fortune(score, random.Random(score))
        record.update(
            {"user_name": "测试用户", "rp_id": ranks.result_icon_for_score(score, random.Random(score))}
        )
        paths[score] = renderer.render_rp_image(record, tmp_path / f"rp_{score}.png")

    with Image.open(paths[0]).convert("RGB") as image_zero:
        assert image_zero.width == 960
        assert 520 <= image_zero.height <= 900
        samples = [image_zero.getpixel((x, 20)) for x in range(20, 940, 40)]
        assert all(max(red, green, blue) - min(red, green, blue) <= 12 for red, green, blue in samples)
        assert len(set(samples)) > 10
        edge_samples = [
            image_zero.getpixel((x, y))
            for y in range(20, image_zero.height, 80)
            for x in (5, image_zero.width - 6)
        ]
        assert all(
            max(red, green, blue) - min(red, green, blue) <= 12
            for red, green, blue in edge_samples
        )
        assert len(set(edge_samples)) >= max(10, len(edge_samples) // 2)
    with Image.open(paths[100]).convert("RGB") as image_hundred:
        samples = [image_hundred.getpixel((x, 20)) for x in range(20, 940, 40)]
        assert len(set(samples)) > 10
        assert any(max(pixel) - min(pixel) > 35 for pixel in samples)
        horizontal_bands = [
            [
                image_hundred.getpixel((x, y))
                for x in range(5, image_hundred.width, 80)
            ]
            for y in range(20, image_hundred.height, 80)
        ]
        assert all(len(set(band)) > 6 for band in horizontal_bands)
        assert all(
            any(max(pixel) - min(pixel) > 35 for pixel in band)
            for band in horizontal_bands
        )
    with Image.open(paths[50]) as image_normal:
        assert image_normal.width == 960
        assert 520 <= image_normal.height <= 900


def test_low_score_never_loads_gray_rank_icon(tmp_path):
    renderer, _, content = renderer_and_data()

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("RP<50 不应加载评价 Logo")

    renderer._load_icon = fail_if_called
    record = content.make_fortune(25, random.Random(25))
    record.update({"user_name": "低分测试", "rp_id": "none-ji"})
    output = renderer.render_rp_image(record, tmp_path / "rp_25.png")
    with Image.open(output) as image:
        assert image.width == 960
        assert image.height >= 520


def test_long_lucky_color_wraps_within_canvas(tmp_path):
    renderer, ranks, content = renderer_and_data()
    long_color = "雨后群青与极光紫交织的渐变色" * 3
    record = content.make_fortune(50, random.Random(50))
    record.update(
        {
            "user_name": "测试用户",
            "rp_id": ranks.result_icon_for_score(50, random.Random(50)),
            "color": long_color,
        }
    )
    record["content_fields"] = dict(record["content_fields"])
    record["content_fields"]["color"] = long_color

    canvas = Image.new("RGB", (renderer.canvas_width, renderer.canvas_height))
    draw = ImageDraw.Draw(canvas)
    font = renderer.font(renderer.desc_font_size)
    max_width = int(renderer.canvas_width * renderer.analysis_width_ratio)
    description = renderer._wrap_daily_description(
        draw,
        record["user_name"],
        record["fortune_text"],
        record["color"],
        font,
        max_width,
    )

    assert description.replace("\n", "") == (
        f"Hi~ “{record['user_name']}”"
        f"今日签：{record['fortune_text']}"
        f"幸运色：{long_color}"
    )
    assert all(
        draw.textbbox((0, 0), line, font=font)[2] <= max_width
        for line in description.splitlines()
    )
    assert len(description.splitlines()) > 3

    output = renderer.render_rp_image(record, tmp_path / "rp_long_color.png")
    with Image.open(output) as image:
        assert image.width == 960
        assert image.height > 650


def test_leaderboard_renders_long_image_with_crowns_and_round_avatars(tmp_path):
    renderer, _, _ = renderer_and_data()
    entries = []
    for index, score in enumerate((100, 97, 92, 88, 75), start=1):
        avatar = Image.new("RGBA", (96, 96), (30 * index, 80, 160, 255))
        entries.append(
            {
                "user_id": f"1000{index}",
                "user_name": f"测试成员 {index}",
                "luck_value": score,
                "avatar": avatar,
            }
        )

    for crown_id in ("hongguan", "jinguan", "yinguan"):
        assert renderer.find_image_file(crown_id) is not None
    output = renderer.render_leaderboard_image(
        "本地测试群",
        entries,
        tmp_path / "leaderboard.png",
    )
    with Image.open(output) as image:
        assert image.size == (960, 176 + len(entries) * 112 + 60)
        assert image.height > image.width / 2


def test_statistics_image_contains_all_cards(tmp_path):
    renderer, ranks, _ = renderer_and_data()
    scores = [0, 12, 49, 50, 65, 75, 85, 92, 97, 100] * 3
    today = date.today()
    records = [
        {"date": (today - timedelta(days=29 - index)).isoformat(), "luck_value": score}
        for index, score in enumerate(scores)
    ]
    counts = count_scores_by_rank(scores, ranks)
    output = renderer.render_statistics_image("测试用户", records, counts, tmp_path / "stats.png")
    with Image.open(output) as image:
        assert image.size == (1200, 1040)
    assert sum(counts.values()) == 30
    assert set(counts) == {rank.id for rank in ranks.ranks}


def test_layout_lab_generates_every_coded_variant(tmp_path):
    _, ranks, content = renderer_and_data()
    lab = LayoutLab(ROOT / "resource", ranks)
    record = content.make_fortune(88, random.Random(88))
    record.update(
        {
            "user_name": "布局试验用户",
            "rp_id": ranks.result_icon_for_score(88, random.Random(88)),
        }
    )
    for code in VARIANTS:
        output = lab.render_variant(code, record, tmp_path / f"{code}.png")
        with Image.open(output) as image:
            assert image.size == (VARIANT_SIZES[code][0], lab.HEIGHT)
