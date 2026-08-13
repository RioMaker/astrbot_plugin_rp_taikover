import json
import random
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from rp_core import (
    CHINA_TZ,
    ContentItem,
    ContentStore,
    LuckDatabase,
    RankCatalog,
    select_content_path,
)


ROOT = Path(__file__).resolve().parents[1]


def load_catalogs():
    ranks = RankCatalog.from_file(ROOT / "resource" / "ranks.json")
    content = ContentStore.from_file(select_content_path(ROOT / "resource"))
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
    assert first["content_schema_version"] == 2
    assert set(first["content_fields"]) == {
        "fortune_text",
        "color",
        "advice_do",
        "advice_dont",
        "taiko_bpm",
        "taiko_stars",
        "taiko_advice",
        "today_events",
    }
    with database.connect() as connection:
        row = connection.execute(
            "SELECT fortune_text, content_json FROM luck_records WHERE user_id = ?",
            ("user-1",),
        ).fetchone()
    assert row["fortune_text"] == ""
    assert json.loads(row["content_json"])["fields"] == first["content_fields"]


def test_legacy_database_is_migrated_without_losing_old_fields(tmp_path):
    _, content = load_catalogs()
    path = tmp_path / "legacy.db"
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE luck_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                date TEXT NOT NULL,
                luck_value INTEGER NOT NULL,
                fortune_text TEXT NOT NULL,
                color TEXT NOT NULL,
                advice_do TEXT NOT NULL,
                advice_dont TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            INSERT INTO luck_records
                (user_id, date, luck_value, fortune_text, color, advice_do, advice_dont)
            VALUES ('legacy-user', '2026-08-01', 66, '旧签', '旧色', '旧宜', '旧忌')
            """
        )
    database = LuckDatabase(path, content)
    database.init()
    record = database.get_record("legacy-user", "2026-08-01")
    assert record is not None
    assert record["content_schema_version"] == 1
    assert record["content_fields"] == {
        "fortune_text": "旧签",
        "color": "旧色",
        "advice_do": "旧宜",
        "advice_dont": "旧忌",
    }
    with database.connect() as connection:
        columns = {row["name"] for row in connection.execute("PRAGMA table_info(luck_records)")}
    assert {"content_schema_version", "content_json"} <= columns


def test_content_schema_labels_are_versioned_and_version_reuse_is_rejected(tmp_path):
    _, content = load_catalogs()
    path = tmp_path / "schema.db"
    database = LuckDatabase(path, content)
    database.init()
    database.insert_record_for_test("user", "2026-08-01", 66, random.Random(66))

    changed_labels = dict(content.category_labels)
    changed_labels["fortune_texts"] = "新版今日签"
    version_three = ContentStore(
        content.data,
        schema_version=3,
        category_labels=changed_labels,
    )
    upgraded = LuckDatabase(path, version_three)
    upgraded.init()
    old_record = upgraded.get_record("user", "2026-08-01")
    assert old_record is not None
    assert old_record["content_labels"]["fortune_text"] == "今日签"

    reused_version = ContentStore(
        content.data,
        schema_version=2,
        category_labels=changed_labels,
    )
    with pytest.raises(ValueError, match="必须递增 schema_version"):
        LuckDatabase(path, reused_version).init()


def test_storage_stats_and_purge_old_records(tmp_path):
    _, content = load_catalogs()
    database = LuckDatabase(tmp_path / "storage.db", content)
    database.init()
    today = datetime.now(CHINA_TZ)
    old_date = (today - timedelta(days=45)).strftime("%Y-%m-%d")
    recent_date = (today - timedelta(days=5)).strftime("%Y-%m-%d")
    database.insert_record_for_test("old-user", old_date, 10, random.Random(10))
    database.insert_record_for_test("recent-user", recent_date, 90, random.Random(90))
    database.track_group_member("qq:test", "old-user", "旧用户", date_string=old_date)
    stats = database.storage_stats()
    assert stats["record_count"] == 2
    assert stats["snapshot_count"] == 2
    assert stats["snapshot_bytes"] > 0
    assert stats["average_snapshot_bytes"] > 0
    assert stats["schema_definition_count"] == 1
    assert stats["schema_definition_bytes"] > 0

    result = database.purge_older_than(30)
    assert result["records_deleted"] == 1
    assert result["members_deleted"] == 1
    assert database.get_record("old-user", old_date) is None
    assert database.get_record("recent-user", recent_date) is not None


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
