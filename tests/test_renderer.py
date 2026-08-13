import random
from datetime import date, timedelta
from pathlib import Path

from PIL import Image

from rp_core import ContentStore, RankCatalog, count_scores_by_rank
from rp_renderer_effects import RpImageRenderer


ROOT = Path(__file__).resolve().parents[1]


def renderer_and_data():
    resource = ROOT / "resource"
    ranks = RankCatalog.from_file(resource / "ranks.json")
    content = ContentStore.from_file(resource / "content.json")
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
        assert image_zero.size == (800, 800)
        samples = [image_zero.getpixel((x, 20)) for x in range(20, 780, 40)]
        assert all(max(red, green, blue) - min(red, green, blue) <= 12 for red, green, blue in samples)
        assert len(set(samples)) > 10
    with Image.open(paths[100]).convert("RGB") as image_hundred:
        samples = [image_hundred.getpixel((x, 20)) for x in range(20, 780, 40)]
        assert len(set(samples)) > 10
        assert any(max(pixel) - min(pixel) > 35 for pixel in samples)
    with Image.open(paths[50]) as image_normal:
        assert image_normal.size == (800, 800)


def test_low_score_never_loads_gray_rank_icon(tmp_path):
    renderer, _, content = renderer_and_data()

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("RP<50 不应加载评价 Logo")

    renderer._load_icon = fail_if_called
    record = content.make_fortune(25, random.Random(25))
    record.update({"user_name": "低分测试", "rp_id": "none-ji"})
    output = renderer.render_rp_image(record, tmp_path / "rp_25.png")
    with Image.open(output) as image:
        assert image.size == (800, 800)


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
