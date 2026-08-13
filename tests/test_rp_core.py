import random
from pathlib import Path

from rp_core import ContentItem, ContentStore, LuckDatabase, RankCatalog


ROOT = Path(__file__).resolve().parents[1]


def load_catalogs():
    ranks = RankCatalog.from_file(ROOT / "resource" / "ranks.json")
    content = ContentStore.from_file(ROOT / "resource" / "content.json")
    return ranks, content


def test_rank_catalog_covers_every_score_once():
    ranks, _ = load_catalogs()
    assert ranks.for_score(0).id == "unrated"
    assert ranks.for_score(49).id == "unrated"
    assert ranks.for_score(50).id == "baicui"
    assert ranks.for_score(99).id == "ziya"
    assert ranks.for_score(100).id == "ji"


def test_content_range_filtering():
    unrestricted = ContentItem("通用")
    store = ContentStore(
        {
            "fortune_texts": [unrestricted, ContentItem("高分", 80, 100)],
            "colors": [unrestricted],
            "advice_do": [unrestricted],
            "advice_dont": [unrestricted],
        }
    )
    assert [item.text for item in store.eligible("fortune_texts", 20)] == ["通用"]
    assert [item.text for item in store.eligible("fortune_texts", 80)] == ["通用", "高分"]


def test_same_day_returns_same_persisted_record(tmp_path):
    _, content = load_catalogs()
    database = LuckDatabase(tmp_path / "luck.db", content)
    database.init()
    first = database.get_or_create_today("user-1", random.Random(1))
    second = database.get_or_create_today("user-1", random.Random(999))
    assert first == second
    assert len(database.get_recent_records("user-1")) == 1


def test_recent_limit_and_total_rank_counts(tmp_path):
    ranks, content = load_catalogs()
    database = LuckDatabase(tmp_path / "history.db", content)
    database.init()
    for index in range(35):
        database.insert_record_for_test(
            "user-2",
            f"2026-07-{index + 1:02d}" if index < 31 else f"2026-08-{index - 30:02d}",
            index * 3 % 101,
            random.Random(index),
        )
    recent = database.get_recent_records("user-2", limit=30)
    counts = database.count_ranks("user-2", ranks)
    assert len(recent) == 30
    assert sum(counts.values()) == 35
    assert [row["date"] for row in recent] == sorted(row["date"] for row in recent)
