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


def test_group_leaderboard_only_contains_today_members_and_sorts_scores(tmp_path):
    _, content = load_catalogs()
    database = LuckDatabase(tmp_path / "leaderboard.db", content)
    database.init()
    today = database.today_string()
    scores = {"user-low": 23, "user-high": 98, "user-mid": 66}
    for user_id, score in scores.items():
        database.insert_record_for_test(user_id, today, score, random.Random(score))
        database.track_group_member(
            "qq:test-group",
            user_id,
            f"昵称-{user_id}",
            f"https://example.com/{user_id}.png",
            today,
        )

    database.insert_record_for_test("other-group", today, 100, random.Random(100))
    database.track_group_member("qq:other", "other-group", "其他群", date_string=today)
    database.insert_record_for_test("yesterday-member", today, 99, random.Random(99))
    database.track_group_member(
        "qq:test-group", "yesterday-member", "昨日成员", date_string="2026-08-12"
    )

    leaderboard = database.get_group_leaderboard("qq:test-group", limit=2, date_string=today)
    assert [entry["user_id"] for entry in leaderboard] == ["user-high", "user-mid"]
    assert [entry["luck_value"] for entry in leaderboard] == [98, 66]
    assert leaderboard[0]["avatar_url"].endswith("user-high.png")


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
