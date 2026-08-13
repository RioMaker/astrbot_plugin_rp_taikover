from __future__ import annotations

import json
import random
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence


CHINA_TZ = timezone(timedelta(hours=8))
BASE_CONTENT_KEYS = ("fortune_texts", "colors", "advice_do", "advice_dont")
CONTENT_KEYS = BASE_CONTENT_KEYS
CONTENT2_KEYS = (
    *BASE_CONTENT_KEYS,
    "taiko_bpm",
    "taiko_stars",
    "taiko_advice",
    "today_events",
)
CONTENT_FIELD_ALIASES = {
    "fortune_texts": "fortune_text",
    "colors": "color",
}
DEFAULT_CONTENT_LABELS = {
    "fortune_texts": "今日签",
    "colors": "幸运色",
    "advice_do": "宜",
    "advice_dont": "忌",
    "taiko_bpm": "推荐 BPM",
    "taiko_stars": "推荐星级",
    "taiko_advice": "太鼓建议",
    "today_events": "今日事件",
}
SNAPSHOT_FORMAT_VERSION = 1


def content_field_name(category: str) -> str:
    return CONTENT_FIELD_ALIASES.get(category, category)


def select_content_path(resource_dir: str | Path) -> Path:
    """选择 schema_version 最高的内容库，当前 content2 会优先于旧版 content。"""
    resource_dir = Path(resource_dir)
    candidates = [
        path for path in (resource_dir / "content.json", resource_dir / "content2.json")
        if path.exists()
    ]
    if not candidates:
        raise FileNotFoundError(f"未找到内容库：{resource_dir}")
    scored: list[tuple[int, int, Path]] = []
    for path in candidates:
        raw = json.loads(path.read_text(encoding="utf-8"))
        version = int(raw.get("schema_version", 1))
        scored.append((version, 1 if path.name == "content2.json" else 0, path))
    return max(scored)[2]


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
    """可按 RP 范围筛选、字段可扩展且带版本号的内容库。"""

    def __init__(
        self,
        data: dict[str, Sequence[ContentItem]],
        source_path: Path | None = None,
        schema_version: int = 1,
        category_labels: dict[str, str] | None = None,
    ):
        if isinstance(schema_version, bool) or int(schema_version) < 1:
            raise ValueError("内容库 schema_version 必须是正整数")
        self.schema_version = int(schema_version)
        self.source_path = source_path
        self.data = {str(key): tuple(values) for key, values in data.items()}
        missing = [key for key in BASE_CONTENT_KEYS if not self.data.get(key)]
        empty = [key for key in BASE_CONTENT_KEYS if not self.data.get(key)]
        if missing or empty:
            invalid = tuple(dict.fromkeys((*missing, *empty)))
            raise ValueError(f"内容库分类不能为空：{', '.join(invalid)}")
        self.data = {key: values for key, values in self.data.items() if values}
        self.keys = tuple(self.data)

        raw_labels = category_labels or {}
        self.category_labels = {
            key: str(raw_labels.get(key) or DEFAULT_CONTENT_LABELS.get(key) or key)
            for key in self.keys
        }
        self.field_keys = tuple(content_field_name(key) for key in self.keys)
        if len(set(self.field_keys)) != len(self.field_keys):
            raise ValueError("内容库字段别名发生冲突")
        self.field_labels = {
            content_field_name(key): self.category_labels[key] for key in self.keys
        }

    @classmethod
    def from_file(cls, path: str | Path) -> "ContentStore":
        path = Path(path)
        raw = json.loads(path.read_text(encoding="utf-8"))
        parsed: dict[str, list[ContentItem]] = {}
        for key, values in raw.items():
            if not isinstance(values, list):
                continue
            parsed[key] = [
                parse_content_item(value, key, index)
                for index, value in enumerate(values, 1)
            ]
        labels = raw.get("categories") if isinstance(raw.get("categories"), dict) else {}
        return cls(
            parsed,
            path,
            schema_version=raw.get("schema_version", 1),
            category_labels={str(key): str(value) for key, value in labels.items()},
        )

    def eligible(self, category: str, rp_value: int) -> tuple[ContentItem, ...]:
        if category not in self.data:
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
        chooser = rng or random
        fields = {
            content_field_name(category): self.choose(category, rp_value, chooser).text
            for category in self.keys
        }
        return {
            "luck_value": rp_value,
            "content_schema_version": self.schema_version,
            "content_fields": fields,
            "content_labels": dict(self.field_labels),
            **fields,
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
    """每日 RP 仓库：兼容旧列，并以带版本的 JSON 快照承载可变字段。"""

    RECORD_COLUMNS = """
        id, date, luck_value, fortune_text, color, advice_do, advice_dont,
        content_schema_version, content_json
    """

    def __init__(self, path: str | Path, content_store: ContentStore):
        self.path = Path(path)
        self.content_store = content_store
        self._schema_labels_cache: dict[int, dict[str, str]] = {}

    def connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=15)
        connection.row_factory = sqlite3.Row
        return connection

    def _schema_definition_json(self) -> str:
        payload = {
            "format_version": SNAPSHOT_FORMAT_VERSION,
            "field_labels": dict(self.content_store.field_labels),
        }
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

    @staticmethod
    def _decode_schema_labels(raw_definition: str) -> dict[str, str]:
        try:
            payload = json.loads(raw_definition)
        except (TypeError, ValueError, json.JSONDecodeError):
            return {}
        if not isinstance(payload, dict):
            return {}
        raw_labels = payload.get("field_labels", {})
        if not isinstance(raw_labels, dict):
            return {}
        return {
            str(key): str(value)
            for key, value in raw_labels.items()
            if value is not None
        }

    def _register_content_schema(self, connection: sqlite3.Connection) -> None:
        version = int(self.content_store.schema_version)
        definition_json = self._schema_definition_json()
        connection.execute(
            """
            INSERT OR IGNORE INTO content_schemas
                (schema_version, definition_json, created_at)
            VALUES (?, ?, ?)
            """,
            (
                version,
                definition_json,
                datetime.now(CHINA_TZ).isoformat(timespec="seconds"),
            ),
        )
        row = connection.execute(
            "SELECT definition_json FROM content_schemas WHERE schema_version = ?",
            (version,),
        ).fetchone()
        stored_labels = self._decode_schema_labels(str(row["definition_json"] or ""))
        expected_labels = dict(self.content_store.field_labels)
        if stored_labels != expected_labels:
            raise ValueError(
                f"内容库 schema_version={version} 已对应其他字段结构，"
                "字段发生变化时必须递增 schema_version"
            )
        self._schema_labels_cache[version] = stored_labels

    def register_content_schema(self) -> None:
        with self.connect() as connection:
            self._register_content_schema(connection)

    def _schema_labels_for_version(self, version: int) -> dict[str, str]:
        version = int(version)
        if version in self._schema_labels_cache:
            return self._schema_labels_cache[version]
        with self.connect() as connection:
            row = connection.execute(
                "SELECT definition_json FROM content_schemas WHERE schema_version = ?",
                (version,),
            ).fetchone()
        labels = (
            self._decode_schema_labels(str(row["definition_json"] or ""))
            if row else {}
        )
        self._schema_labels_cache[version] = labels
        return labels

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
                    advice_dont TEXT NOT NULL,
                    content_schema_version INTEGER NOT NULL DEFAULT 1,
                    content_json TEXT NOT NULL DEFAULT ''
                )
                """
            )
            columns = {
                str(row["name"])
                for row in connection.execute("PRAGMA table_info(luck_records)").fetchall()
            }
            if "content_schema_version" not in columns:
                connection.execute(
                    "ALTER TABLE luck_records "
                    "ADD COLUMN content_schema_version INTEGER NOT NULL DEFAULT 1"
                )
            if "content_json" not in columns:
                connection.execute(
                    "ALTER TABLE luck_records "
                    "ADD COLUMN content_json TEXT NOT NULL DEFAULT ''"
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
                CREATE TABLE IF NOT EXISTS group_rp_members (
                    group_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    user_name TEXT NOT NULL,
                    avatar_url TEXT NOT NULL DEFAULT '',
                    last_rp_date TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (group_id, user_id)
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS content_schemas (
                    schema_version INTEGER PRIMARY KEY,
                    definition_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_luck_records_user_date
                ON luck_records (user_id, date, id)
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_group_rp_members_date
                ON group_rp_members (group_id, last_rp_date)
                """
            )
            self._register_content_schema(connection)

    @staticmethod
    def today_string() -> str:
        return datetime.now(CHINA_TZ).strftime("%Y-%m-%d")

    def _row_to_record(self, row: sqlite3.Row) -> dict[str, Any]:
        legacy_fields = {
            "fortune_text": str(row["fortune_text"] or ""),
            "color": str(row["color"] or ""),
            "advice_do": str(row["advice_do"] or ""),
            "advice_dont": str(row["advice_dont"] or ""),
        }
        fields: dict[str, str] = {}
        raw_snapshot = str(row["content_json"] or "")
        if raw_snapshot:
            try:
                payload = json.loads(raw_snapshot)
                raw_fields = payload.get("fields", payload) if isinstance(payload, dict) else {}
                if isinstance(raw_fields, dict):
                    fields = {
                        str(key): str(value)
                        for key, value in raw_fields.items()
                        if value is not None
                    }
            except (TypeError, ValueError, json.JSONDecodeError):
                fields = {}
        for key, value in legacy_fields.items():
            if value and key not in fields:
                fields[key] = value
        schema_version = int(row["content_schema_version"] or 1)
        stored_labels = self._schema_labels_for_version(schema_version)
        labels = {
            key: stored_labels.get(
                key,
                self.content_store.field_labels.get(key, key.replace("_", " ")),
            )
            for key in fields
        }
        return {
            "id": int(row["id"]),
            "date": str(row["date"]),
            "luck_value": int(row["luck_value"]),
            "content_schema_version": schema_version,
            "content_fields": fields,
            "content_labels": labels,
            **legacy_fields,
            **fields,
        }

    def _snapshot_json(self, record: dict[str, Any]) -> str:
        raw_fields = record.get("content_fields")
        if not isinstance(raw_fields, dict):
            raw_fields = {
                key: record[key]
                for key in self.content_store.field_keys
                if key in record
            }
        fields = {
            str(key): str(value)
            for key, value in raw_fields.items()
            if value is not None
        }
        payload = {"format_version": SNAPSHOT_FORMAT_VERSION, "fields": fields}
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

    def _insert_record(
        self,
        connection: sqlite3.Connection,
        user_id: str,
        date_string: str,
        record: dict[str, Any],
    ) -> int:
        cursor = connection.execute(
            """
            INSERT INTO luck_records
                (
                    user_id, date, luck_value,
                    fortune_text, color, advice_do, advice_dont,
                    content_schema_version, content_json
                )
            VALUES (?, ?, ?, '', '', '', '', ?, ?)
            """,
            (
                str(user_id),
                date_string,
                int(record["luck_value"]),
                int(record.get("content_schema_version", self.content_store.schema_version)),
                self._snapshot_json(record),
            ),
        )
        return int(cursor.lastrowid)

    def get_today_record(self, user_id: str) -> dict[str, Any] | None:
        return self.get_record(user_id, self.today_string())

    def get_record(self, user_id: str, date_string: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                f"""
                SELECT {self.RECORD_COLUMNS}
                FROM luck_records
                WHERE user_id = ? AND date = ?
                ORDER BY id ASC
                LIMIT 1
                """,
                (str(user_id), date_string),
            ).fetchone()
        return self._row_to_record(row) if row else None

    def build_record(
        self, rp_value: int | None = None, rng: random.Random | None = None
    ) -> dict[str, Any]:
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
                f"""
                SELECT {self.RECORD_COLUMNS}
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
            record_id = self._insert_record(connection, str(user_id), date_string, record)
            record.update({"id": record_id, "date": date_string})
            return record

    def get_recent_records(self, user_id: str, limit: int = 30) -> list[dict[str, Any]]:
        limit = max(1, min(365, int(limit)))
        with self.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT {self.RECORD_COLUMNS}
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

    def track_group_member(
        self,
        group_id: str,
        user_id: str,
        user_name: str,
        avatar_url: str = "",
        date_string: str | None = None,
    ) -> None:
        date_string = date_string or self.today_string()
        updated_at = datetime.now(CHINA_TZ).isoformat(timespec="seconds")
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO group_rp_members
                    (group_id, user_id, user_name, avatar_url, last_rp_date, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(group_id, user_id) DO UPDATE SET
                    user_name = excluded.user_name,
                    avatar_url = CASE
                        WHEN excluded.avatar_url <> '' THEN excluded.avatar_url
                        ELSE group_rp_members.avatar_url
                    END,
                    last_rp_date = excluded.last_rp_date,
                    updated_at = excluded.updated_at
                """,
                (
                    str(group_id),
                    str(user_id),
                    str(user_name).strip() or str(user_id),
                    str(avatar_url).strip(),
                    date_string,
                    updated_at,
                ),
            )

    def get_group_leaderboard(
        self,
        group_id: str,
        limit: int = 50,
        date_string: str | None = None,
    ) -> list[dict[str, Any]]:
        limit = max(1, min(200, int(limit)))
        date_string = date_string or self.today_string()
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    members.user_id,
                    members.user_name,
                    members.avatar_url,
                    records.luck_value,
                    records.date
                FROM group_rp_members AS members
                JOIN luck_records AS records
                    ON records.id = (
                        SELECT candidate.id
                        FROM luck_records AS candidate
                        WHERE candidate.user_id = members.user_id
                          AND candidate.date = ?
                        ORDER BY candidate.id ASC
                        LIMIT 1
                    )
                WHERE members.group_id = ?
                  AND members.last_rp_date = ?
                ORDER BY records.luck_value DESC, records.id ASC, members.user_id ASC
                LIMIT ?
                """,
                (date_string, str(group_id), date_string, limit),
            ).fetchall()
        return [
            {
                "user_id": str(row["user_id"]),
                "user_name": str(row["user_name"]),
                "avatar_url": str(row["avatar_url"] or ""),
                "luck_value": int(row["luck_value"]),
                "date": str(row["date"]),
            }
            for row in rows
        ]

    def storage_stats(self) -> dict[str, Any]:
        with self.connect() as connection:
            summary = connection.execute(
                """
                SELECT
                    COUNT(*) AS record_count,
                    MIN(date) AS oldest_date,
                    MAX(date) AS newest_date,
                    SUM(CASE WHEN content_json <> '' THEN 1 ELSE 0 END) AS snapshot_count,
                    COALESCE(SUM(length(CAST(content_json AS BLOB))), 0) AS snapshot_bytes,
                    COALESCE(SUM(
                        length(CAST(fortune_text AS BLOB)) +
                        length(CAST(color AS BLOB)) +
                        length(CAST(advice_do AS BLOB)) +
                        length(CAST(advice_dont AS BLOB))
                    ), 0) AS legacy_content_bytes
                FROM luck_records
                """
            ).fetchone()
            group_member_count = int(
                connection.execute("SELECT COUNT(*) FROM group_rp_members").fetchone()[0]
            )
            schema_versions = {
                int(row["content_schema_version"]): int(row["amount"])
                for row in connection.execute(
                    """
                    SELECT content_schema_version, COUNT(*) AS amount
                    FROM luck_records
                    GROUP BY content_schema_version
                    ORDER BY content_schema_version
                    """
                ).fetchall()
            }
            schema_summary = connection.execute(
                """
                SELECT
                    COUNT(*) AS definition_count,
                    COALESCE(SUM(length(CAST(definition_json AS BLOB))), 0)
                        AS definition_bytes
                FROM content_schemas
                """
            ).fetchone()
            page_size = int(connection.execute("PRAGMA page_size").fetchone()[0])
            free_pages = int(connection.execute("PRAGMA freelist_count").fetchone()[0])

        file_paths = [
            self.path,
            Path(f"{self.path}-wal"),
            Path(f"{self.path}-shm"),
            Path(f"{self.path}-journal"),
        ]
        database_files_bytes = sum(
            path.stat().st_size for path in file_paths if path.exists() and path.is_file()
        )
        record_count = int(summary["record_count"] or 0)
        snapshot_count = int(summary["snapshot_count"] or 0)
        snapshot_bytes = int(summary["snapshot_bytes"] or 0)
        return {
            "database_files_bytes": database_files_bytes,
            "reclaimable_bytes": free_pages * page_size,
            "record_count": record_count,
            "group_member_count": group_member_count,
            "oldest_date": summary["oldest_date"],
            "newest_date": summary["newest_date"],
            "snapshot_count": snapshot_count,
            "snapshot_bytes": snapshot_bytes,
            "average_snapshot_bytes": snapshot_bytes / snapshot_count if snapshot_count else 0,
            "legacy_content_bytes": int(summary["legacy_content_bytes"] or 0),
            "schema_versions": schema_versions,
            "schema_definition_count": int(schema_summary["definition_count"] or 0),
            "schema_definition_bytes": int(schema_summary["definition_bytes"] or 0),
        }

    def purge_older_than(self, days: int) -> dict[str, Any]:
        days = int(days)
        if not 0 <= days <= 36500:
            raise ValueError("保留天数必须位于 0~36500")
        cutoff_date = (datetime.now(CHINA_TZ) - timedelta(days=days)).strftime("%Y-%m-%d")
        before_bytes = int(self.storage_stats()["database_files_bytes"])
        with self.connect() as connection:
            records_deleted = connection.execute(
                "DELETE FROM luck_records WHERE date < ?", (cutoff_date,)
            ).rowcount
            steals_deleted = connection.execute(
                "DELETE FROM luck_steals WHERE date < ?", (cutoff_date,)
            ).rowcount
            members_deleted = connection.execute(
                "DELETE FROM group_rp_members WHERE last_rp_date < ?", (cutoff_date,)
            ).rowcount
        with self.connect() as connection:
            connection.execute("VACUUM")
        after_bytes = int(self.storage_stats()["database_files_bytes"])
        return {
            "cutoff_date": cutoff_date,
            "records_deleted": max(0, int(records_deleted)),
            "steals_deleted": max(0, int(steals_deleted)),
            "members_deleted": max(0, int(members_deleted)),
            "before_bytes": before_bytes,
            "after_bytes": after_bytes,
            "reclaimed_bytes": max(0, before_bytes - after_bytes),
        }

    def insert_record_for_test(
        self,
        user_id: str,
        date_string: str,
        rp_value: int,
        rng: random.Random | None = None,
    ) -> dict[str, Any]:
        record = self.build_record(rp_value, rng)
        with self.connect() as connection:
            record_id = self._insert_record(connection, str(user_id), date_string, record)
        record.update({"id": record_id, "date": date_string})
        return record


def count_scores_by_rank(
    scores: Iterable[int], rank_catalog: RankCatalog
) -> dict[str, int]:
    counts = rank_catalog.empty_counts()
    for score in scores:
        counts[rank_catalog.for_score(score).id] += 1
    return counts
