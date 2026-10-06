import asyncio
import importlib
import inspect
import random
import sys
import types
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import AsyncMock

import docstring_parser
import pytest

ROOT = Path(__file__).resolve().parents[1]


class FakeEvent:
    def __init__(self, user_id="user-1", group_id="group-a", platform="test"):
        self.user_id = user_id
        self.group_id = group_id
        self.platform = platform
        self.messages = []
        self.stopped = False
        self.message_obj = None

    def get_sender_id(self):
        return self.user_id

    def get_sender_name(self):
        return f"昵称-{self.user_id}"

    def get_group_id(self):
        return self.group_id

    def get_platform_name(self):
        return self.platform

    def plain_result(self, text):
        return text

    async def send(self, message):
        self.messages.append(message)

    def stop_event(self):
        self.stopped = True


@pytest.fixture
def plugin(tmp_path, monkeypatch):
    """仅替换 AstrBot 宿主，使用真实 RP 数据库和内容快照。"""

    def module(name, package=False):
        result = types.ModuleType(name)
        if package:
            result.__path__ = []
        monkeypatch.setitem(sys.modules, name, result)
        return result

    def identity(*_args, **_kwargs):
        return lambda target: target

    def llm_tool(name):
        def decorate(target):
            target.llm_tool_name = name
            return target

        return decorate

    astrbot = module("astrbot", True)
    api = module("astrbot.api", True)
    components = module("astrbot.api.message_components")
    event = module("astrbot.api.event", True)
    event_filter = module("astrbot.api.event.filter")
    star = module("astrbot.api.star")
    core = module("astrbot.core")
    astrbot.api = api
    api.message_components = components
    api.logger = types.SimpleNamespace(
        **{
            name: lambda *_a, **_kw: None
            for name in ("debug", "info", "warning", "error", "exception")
        }
    )
    event.AstrMessageEvent = FakeEvent
    event.filter = types.SimpleNamespace(
        command=identity, permission_type=identity, llm_tool=llm_tool
    )
    event_filter.PermissionType = types.SimpleNamespace(ADMIN="ADMIN")
    star.Context = type("Context", (), {})
    star.Star = type("Star", (), {})
    star.StarTools = type("StarTools", (), {})
    star.register = identity
    core.AstrBotConfig = dict
    package_name = "rp_llm_test_package"
    package = module(package_name, True)
    package.__path__ = [str(ROOT)]
    package.__package__ = package_name
    try:
        main = importlib.import_module(f"{package_name}.main")
        instance = main.taikoRP.__new__(main.taikoRP)
        instance.rank_catalog = main.RankCatalog.from_file(ROOT / "resource/ranks.json")
        instance.content_store = main.ContentStore.from_file(
            main.select_content_path(ROOT / "resource")
        )
        instance.database = main.LuckDatabase(
            tmp_path / "rp.db", instance.content_store
        )
        instance.database.init()
        instance.send_rendered_rp = AsyncMock()
        yield instance
    finally:
        for name in list(sys.modules):
            if name.startswith(f"{package_name}."):
                sys.modules.pop(name, None)


def test_tool_docstrings_match_astrbot_parameter_contract(plugin):
    expected = {
        "get_today_rp": {"show_image": "boolean"},
        "get_rp_history": {
            "start_date": "string",
            "end_date": "string",
            "limit": "number",
        },
        "get_rp_statistics": {},
        "get_rp_leaderboard": {"limit": "number"},
    }
    tools = {
        method.llm_tool_name: method
        for _, method in inspect.getmembers(plugin, inspect.ismethod)
        if hasattr(method, "llm_tool_name")
    }
    assert set(tools) == set(expected)
    for name, method in tools.items():
        parsed = docstring_parser.parse(method.__doc__)
        assert {param.arg_name: param.type_name for param in parsed.params} == expected[
            name
        ]
        assert set(inspect.signature(method).parameters) - {"event"} == set(
            expected[name]
        )
        assert parsed.description


def test_command_and_tool_reuse_daily_record_and_track_new_group(plugin):
    event = FakeEvent()
    first = asyncio.run(plugin.get_today_rp(event, show_image=False))
    record = plugin.database.get_today_record(event.user_id)
    for key, value in record["content_fields"].items():
        assert f"{record['content_labels'][key]}：{value}" in first
    asyncio.run(plugin.rp(event))
    new_group = FakeEvent(group_id="group-b")
    second = asyncio.run(plugin.get_today_rp(new_group))
    assert first == second
    assert plugin.database.get_today_record(event.user_id) == record
    assert len(plugin.database.get_recent_records(event.user_id)) == 1
    assert plugin.send_rendered_rp.await_count == 2
    assert (
        plugin.database.get_group_leaderboard("test:group-b")[0]["user_id"]
        == event.user_id
    )
    assert not new_group.stopped
    assert new_group.messages == []


def test_concurrent_daily_requests_share_one_record(plugin):
    with ThreadPoolExecutor(max_workers=4) as executor:
        records = list(
            executor.map(
                lambda seed: plugin.database.get_or_create_today(
                    "parallel", random.Random(seed)
                ),
                range(8),
            )
        )
    assert all(record == records[0] for record in records)
    assert len(plugin.database.get_recent_records("parallel")) == 1


def test_today_tool_validates_image_option_and_reports_database_error(
    plugin, monkeypatch
):
    event = FakeEvent()
    assert "布尔值" in asyncio.run(plugin.get_today_rp(event, show_image="false"))
    assert plugin.database.get_recent_records(event.user_id) == []
    monkeypatch.setattr(plugin.database, "get_or_create_today", lambda *_a: 1 / 0)
    assert "获取失败" in asyncio.run(plugin.get_today_rp(event, show_image=False))
    assert not event.stopped


def test_history_returns_saved_snapshots_and_filters_user_dates_and_limit(plugin):
    database = plugin.database
    for index, score in enumerate((0, 50, 100), 1):
        database.insert_record_for_test("user-1", f"2026-08-0{index}", score)
    database.insert_record_for_test("other-user", "2026-08-02", 99)
    expected = database.get_record("user-1", "2026-08-02")
    # 替换内容库后仍须返回抽取时的历史字段与版本标签。
    database.content_store = types.SimpleNamespace(field_labels={})
    event = FakeEvent()
    text = asyncio.run(plugin.get_rp_history(event, "2026-08-01", "2026-08-03", 2))
    assert "2026-08-01：" not in text
    assert text.index("2026-08-02：RP 50") < text.index("2026-08-03：RP 100")
    assert "RP 99" not in text
    for key, value in expected["content_fields"].items():
        assert f"{expected['content_labels'][key]}：{value}" in text
    assert database.storage_stats()["record_count"] == 4
    assert not event.stopped
    assert event.messages == []


def test_empty_history_never_creates_today_or_missing_dates(plugin):
    event = FakeEvent()
    assert "没有已保存" in asyncio.run(plugin.get_rp_history(event))
    assert "没有已保存" in asyncio.run(
        plugin.get_rp_history(event, "2026-08-01", "2026-08-01")
    )
    assert plugin.database.get_today_record(event.user_id) is None
    assert plugin.database.storage_stats()["record_count"] == 0


@pytest.mark.parametrize(
    "arguments",
    [
        {"start_date": "2026-02-30"},
        {"start_date": "20260801"},
        {"start_date": "2026-08-03", "end_date": "2026-08-01"},
        {"end_date": "2026-08-01' OR 1=1 --"},
        {"start_date": None},
        {"limit": True},
        {"limit": 2.5},
        {"limit": 0},
        {"limit": 366},
        {"limit": float("inf")},
    ],
)
def test_history_rejects_invalid_arguments_without_writes(plugin, arguments):
    assert "参数无效" in asyncio.run(plugin.get_rp_history(FakeEvent(), **arguments))
    assert plugin.database.storage_stats()["record_count"] == 0


def test_history_command_routes_single_date_and_recent_count(plugin):
    plugin.database.insert_record_for_test("user-1", "2026-08-01", 66)
    plugin.database.insert_record_for_test("user-1", "2026-08-02", 88)
    event = FakeEvent()
    asyncio.run(plugin.rp(event, "历史", "2026-08-01"))
    assert "2026-08-01：RP 66" in event.messages[-1]
    assert "2026-08-02：" not in event.messages[-1]
    asyncio.run(plugin.rp(event, "history", "1"))
    assert "2026-08-02：RP 88" in event.messages[-1]
    assert "2026-08-01：" not in event.messages[-1]
    assert event.stopped


def test_statistics_uses_recent_30_records_and_all_history_counts(plugin):
    for index in range(1, 32):
        plugin.database.insert_record_for_test("user-1", f"2026-08-{index:02d}", 50)
    plugin.database.insert_record_for_test("user-1", "2026-09-01", 100)
    text = asyncio.run(plugin.get_rp_statistics(FakeEvent()))
    assert "最近 30 条" in text
    assert "全部已保存历史：32 条" in text
    assert "2026-08-01：" not in text
    assert "2026-08-03：RP 50" in text
    assert "2026-09-01：RP 100" in text
    assert "白粋：31 次" in text


def test_history_one_sided_bounds_are_inclusive(plugin):
    database = plugin.database
    for index in range(1, 4):
        database.insert_record_for_test("user-1", f"2026-08-0{index}", 10 * index)
    assert [
        record["date"]
        for record in database.get_history_records("user-1", start_date="2026-08-02")
    ] == ["2026-08-02", "2026-08-03"]
    assert [
        record["date"]
        for record in database.get_history_records("user-1", end_date="2026-08-02")
    ] == ["2026-08-01", "2026-08-02"]


def test_history_tool_supports_legacy_columns(plugin):
    with plugin.database.connect() as connection:
        connection.execute(
            """
            INSERT INTO luck_records
                (user_id, date, luck_value, fortune_text, color, advice_do, advice_dont)
            VALUES ('user-1', '2026-07-01', 66, '旧签', '旧色', '旧宜', '旧忌')
            """
        )
    text = asyncio.run(plugin.get_rp_history(FakeEvent(), "2026-07-01", "2026-07-01"))
    assert "2026-07-01：RP 66" in text
    for value in ("旧签", "旧色", "旧宜", "旧忌"):
        assert value in text


def test_empty_statistics_does_not_create_rp(plugin):
    assert "还没有 RP 记录" in asyncio.run(plugin.get_rp_statistics(FakeEvent()))
    assert plugin.database.storage_stats()["record_count"] == 0


def test_leaderboard_is_scoped_and_syncs_existing_rp_without_reroll(plugin):
    database = plugin.database
    today = database.today_string()
    for user_id, group_scope, score in (
        ("user-1", "test:group-b", 88),
        ("member", "test:group-a", 99),
        ("outsider", "test:group-c", 100),
        ("other-platform", "other:group-a", 100),
    ):
        database.insert_record_for_test(user_id, today, score)
        database.track_group_member(group_scope, user_id, user_id)
    event = FakeEvent()
    text = asyncio.run(plugin.get_rp_leaderboard(event, 2.0))
    assert "1. member：RP 99" in text
    assert "2. 昵称-user-1：RP 88" in text
    assert "outsider" not in text
    assert "other-platform" not in text
    assert database.storage_stats()["record_count"] == 4
    assert not event.stopped
    assert event.messages == []


def test_leaderboard_private_empty_and_invalid_queries_do_not_generate_rp(plugin):
    assert "仅可在群聊" in asyncio.run(
        plugin.get_rp_leaderboard(FakeEvent(group_id=""))
    )
    assert "没有上榜" in asyncio.run(plugin.get_rp_leaderboard(FakeEvent()))
    for value in (0, 201, True, 1.5, "all"):
        assert "整数" in asyncio.run(plugin.get_rp_leaderboard(FakeEvent(), value))
    assert plugin.database.storage_stats()["record_count"] == 0
