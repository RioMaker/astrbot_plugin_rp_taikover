import pytest

from tools.content_manager.import_content import parse_rows, validate_coverage
from rp_core import ContentStore


def unrestricted_rows():
    return [
        {"类型": "今日签", "内容": "吉", "RP下限": "", "RP上限": "", "启用": "是"},
        {"类型": "幸运色", "内容": "蓝色", "RP下限": "", "RP上限": "", "启用": "是"},
        {"类型": "宜", "内容": "练习", "RP下限": "", "RP上限": "", "启用": "是"},
        {"类型": "忌", "内容": "熬夜", "RP下限": "", "RP上限": "", "启用": "是"},
    ]


def test_blank_ranges_mean_unrestricted():
    store = ContentStore(parse_rows(unrestricted_rows()))
    validate_coverage(store)
    assert store.choose("fortune_texts", 0).text == "吉"
    assert store.choose("fortune_texts", 100).text == "吉"


def test_invalid_range_is_rejected_with_row_number():
    rows = unrestricted_rows()
    rows[0]["RP下限"] = 90
    rows[0]["RP上限"] = 20
    with pytest.raises(ValueError, match="第 2 行"):
        parse_rows(rows)


def test_coverage_gap_is_rejected():
    rows = unrestricted_rows()
    rows[0]["RP下限"] = 50
    store = ContentStore(parse_rows(rows))
    with pytest.raises(ValueError, match="0-49"):
        validate_coverage(store)
