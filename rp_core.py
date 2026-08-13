from __future__ import annotations

import json
import random
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence


CHINA_TZ = timezone(timedelta(hours=8))
CONTENT_KEYS = ("fortune_texts", "colors", "advice_do", "advice_dont")


@dataclass(frozen=True)
class RankDefinition:
    id: str
    name: str
    min_rp: int
    max_rp: int
    icon: str
    result_icons: tuple[str, ...]
    color: str

    def contains(self, rp_value: int) -> bool:
        return self.min_rp <= rp_value <= self.max_rp


class RankCatalog:
    """评分等级目录。等级定义来自 JSON，避免在命令和渲染中重复写判断。"""

    def __init__(self, ranks: Sequence[RankDefinition]):
        if not ranks:
            raise ValueError("等级配置不能为空")
        self.ranks = tuple(sorted(ranks, key=lambda item: item.min_rp, reverse=True))
        self._validate_coverage()

    @classmethod
    def from_file(cls, path: str | Path) -> "RankCatalog":
        path = Path(path)
        raw = json.loads(path.read_text(encoding="utf-8"))
        ranks: list[RankDefinition] = []
        for index, item in enumerate(raw, start=1):
            try:
                icon = str(item["icon"])
                result_icons = tuple(str(value) for value in item.get("result_icons", [icon]))
                ranks.append(
                    RankDefinition(
                        id=str(item["id"]),
                        name=str(item["name"]),
                        min_rp=int(item["min"]),
                        max_rp=int(item["max"]),
                        icon=icon,
                        result_icons=result_icons or (icon,),
                        color=str(item.get("color", "#64748B")),
                    )
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(f"等级配置第 {index} 项无效：{exc}") from exc
        return cls(ranks)

    def _validate_coverage(self) -> None:
        ids: set[str] = set()
        for rank in self.ranks:
            if rank.id in ids:
                raise ValueError(f"等级 ID 重复：{rank.id}")
            ids.add(rank.id)
            if not (0 <= rank.min_rp <= rank.max_rp <= 100):
                raise ValueError(f"等级 {rank.id} 的范围必须位于 0~100")
        for rp_value in range(101):
            matched = [rank for rank in self.ranks if rank.contains(rp_value)]
            if len(matched) != 1:
                raise ValueError(f"RP={rp_value} 必须且只能匹配一个等级，当前匹配 {len(matched)} 个")

    def for_score(self, rp_value: int) -> RankDefinition:
        rp_value = clamp_rp(rp_value)
        return next(rank for rank in self.ranks if rank.contains(rp_value))

    def result_icon_for_score(self, rp_value: int, rng: random.Random | None = None) -> str:
        rank = self.for_score(rp_value)
        chooser = rng or random
        return chooser.choice(rank.result_icons)

    def empty_counts(self) -> dict[str, int]:
        return {rank.id: 0 for rank in self.ranks}


@dataclass(frozen=True)
class ContentItem:
    text: str
    min_rp: int | None = None
    max_rp: int | None = None
    note: str = ""

    def matches(self, rp_value: int) -> bool:
        return (self.min_rp is None or rp_value >= self.min_rp) and (
            self.max_rp is None or rp_value <= self.max_rp
        )

    def to_json(self) -> dict[str, Any]:
        item: dict[str, Any] = {
            "text": self.text,
            "min_rp": self.min_rp,
            "max_rp": self.max_rp,
        }
        if self.note:
            item["note"] = self.note
        return item


class ContentStore:
    """可按 RP 范围筛选的今日签、幸运色和宜忌内容库。"""

    def __init__(self, data: dict[str, Sequence[ContentItem]], source_path: Path | None = None):
        self.source_path = source_path
        self.data = {key: tuple(data.get(key, ())) for key in CONTENT_KEYS}
        missing = [key for key, values in self.data.items() if not values]
        if missing:
            raise ValueError(f"内容库分类不能为空：{', '.join(missing)}")

    @classmethod
    def from_file(cls, path: str | Path) -> "ContentStore":
        path = Path(path)
        raw = json.loads(path.read_text(encoding="utf-8"))
        parsed: dict[str, list[ContentItem]] = {}
        for key in CONTENT_KEYS:
            values = raw.get(key, [])
            parsed[key] = [parse_content_item(value, key, index) for index, value in enumerate(values, 1)]
        return cls(parsed, path)

    def eligible(self, category: str, rp_value: int) -> tuple[ContentItem, ...]:
        if category not in CONTENT_KEYS:
            raise KeyError(f"未知内容类型：{category}")
        rp_value = clamp_rp(rp_value)
        return tuple(item for item in self.data[category] if item.matches(rp_value))

    def choose(
        self, category: str, rp_value: int, rng: random.Random | None = None
    ) -> ContentItem:
        candidates = self.eligible(category, rp_value)
        if not candidates:
            source = f"（{self.source_path}）" if self.source_path else ""
            raise ValueError(f"内容库 {category} 在 RP={rp_value} 时没有可用内容{source}")
        chooser = rng or random
        return chooser.choice(candidates)

    def make_fortune(self, rp_value: int, rng: random.Random | None = None) -> dict[str, Any]:
        rp_value = clamp_rp(rp_value)
        return {
            "luck_value": rp_value,
            "fortune_text": self.choose("fortune_texts", rp_value, rng).text,
            "color": self.choose("colors", rp_value, rng).text,
            "advice_do": self.choose("advice_do", rp_value, rng).text,
            "advice_dont": self.choose("advice_dont", rp_value, rng).text,
        }


def parse_content_item(value: Any, category: str, index: int) -> ContentItem:
    if isinstance(value, str):
        text = value.strip()
        min_rp = max_rp = None
        note = ""
    elif isinstance(value, dict):
        text = str(value.get("text", "")).strip()
        min_rp = parse_optional_rp(value.get("min_rp"), f"{category}[{index}].min_rp")
        max_rp = parse_optional_rp(value.get("max_rp"), f"{category}[{index}].max_rp")
        note = str(value.get("note", "")).strip()
    else:
        raise ValueError(f"{category}[{index}] 必须是字符串或对象")
    if not text:
        raise ValueError(f"{category}[{index}] 的 text 不能为空")
    if min_rp is not None and max_rp is not None and min_rp > max_rp:
        raise ValueError(f"{category}[{index}] 的 RP 下限不能大于上限")
    return ContentItem(text=text, min_rp=min_rp, max_rp=max_rp, note=note)


def parse_optional_rp(value: Any, field_name: str = "RP 范围") -> int | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, bool):
        raise ValueError(f"{field_name} 必须是 0~100 的整数或留空")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} 必须是 0~100 的整数或留空") from exc
    if not number.is_integer() or not 0 <= number <= 100:
        raise ValueError(f"{field_name} 必须是 0~100 的整数或留空")
    return int(number)


def clamp_rp(value: int) -> int:
    return max(0, min(100, int(value)))


class LuckDatabase:
    """每日 RP 记录仓库，兼容旧版 luck_records 表结构。"""

    def __init__(self, path: str | Path, content_store: ContentStore):
        self.path = Path(path)
        self.content_store = content_store

    def connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=15)
        connection.row_factory = sqlite3.Row
        return connection

    def init(self) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS luck_records (
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
                CREATE TABLE IF NOT EXISTS luck_steals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    stealer_id TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    date TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_luck_records_user_date
                ON luck_records (user_id, date, id)
                """
            )

    @staticmethod
    def today_string() -> str:
        return datetime.now(CHINA_TZ).strftime("%Y-%m-%d")

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "date": row["date"],
            "luck_value": row["luck_value"],
            "fortune_text": row["fortune_text"],
            "color": row["color"],
            "advice_do": row["advice_do"],
            "advice_dont": row["advice_dont"],
        }

    def get_today_record(self, user_id: str) -> dict[str, Any] | None:
        return self.get_record(user_id, self.today_string())

    def get_record(self, user_id: str, date_string: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT id, date, luck_value, fortune_text, color, advice_do, advice_dont
                FROM luck_records
                WHERE user_id = ? AND date = ?
                ORDER BY id ASC
                LIMIT 1
                """,
                (str(user_id), date_string),
            ).fetchone()
        return self._row_to_record(row) if row else None

    def build_record(self, rp_value: int | None = None, rng: random.Random | None = None) -> dict[str, Any]:
        chooser = rng or random
        value = chooser.randint(0, 100) if rp_value is None else clamp_rp(rp_value)
        return self.content_store.make_fortune(value, chooser)

    def get_or_create_today(
        self, user_id: str, rng: random.Random | None = None
    ) -> dict[str, Any]:
        """在写锁中再次检查当天记录，避免并发消息生成两条记录。"""
        date_string = self.today_string()
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT id, date, luck_value, fortune_text, color, advice_do, advice_dont
                FROM luck_records
                WHERE user_id = ? AND date = ?
                ORDER BY id ASC
                LIMIT 1
                """,
                (str(user_id), date_string),
            ).fetchone()
            if row:
                return self._row_to_record(row)
            record = self.build_record(rng=rng)
            cursor = connection.execute(
                """
                INSERT INTO luck_records
                    (user_id, date, luck_value, fortune_text, color, advice_do, advice_dont)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(user_id),
                    date_string,
                    record["luck_value"],
                    record["fortune_text"],
                    record["color"],
                    record["advice_do"],
                    record["advice_dont"],
                ),
            )
            record.update({"id": cursor.lastrowid, "date": date_string})
            return record

    def get_recent_records(self, user_id: str, limit: int = 30) -> list[dict[str, Any]]:
        limit = max(1, min(365, int(limit)))
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT id, date, luck_value, fortune_text, color, advice_do, advice_dont
                FROM luck_records
                WHERE user_id = ?
                ORDER BY date DESC, id DESC
                LIMIT ?
                """,
                (str(user_id), limit),
            ).fetchall()
        return [self._row_to_record(row) for row in reversed(rows)]

    def get_all_scores(self, user_id: str) -> list[int]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT luck_value FROM luck_records WHERE user_id = ?",
                (str(user_id),),
            ).fetchall()
        return [int(row["luck_value"]) for row in rows]

    def count_ranks(self, user_id: str, rank_catalog: RankCatalog) -> dict[str, int]:
        counts = rank_catalog.empty_counts()
        for score in self.get_all_scores(user_id):
            counts[rank_catalog.for_score(score).id] += 1
        return counts

    def insert_record_for_test(
        self,
        user_id: str,
        date_string: str,
        rp_value: int,
        rng: random.Random | None = None,
    ) -> dict[str, Any]:
        """供自动化测试造历史数据；插件命令不会调用。"""
        record = self.build_record(rp_value, rng)
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO luck_records
                    (user_id, date, luck_value, fortune_text, color, advice_do, advice_dont)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(user_id),
                    date_string,
                    record["luck_value"],
                    record["fortune_text"],
                    record["color"],
                    record["advice_do"],
                    record["advice_dont"],
                ),
            )
        record.update({"id": cursor.lastrowid, "date": date_string})
        return record


def count_scores_by_rank(
    scores: Iterable[int], rank_catalog: RankCatalog
) -> dict[str, int]:
    counts = rank_catalog.empty_counts()
    for score in scores:
        counts[rank_catalog.for_score(score).id] += 1
    return counts
