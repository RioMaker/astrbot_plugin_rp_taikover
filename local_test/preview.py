"""本地图片预览入口，不需要安装或启动 AstrBot。

用法：
    python local_test/preview.py
    python local_test/preview.py --score 0 25 50 100 --user-name 测试用户
"""

from __future__ import annotations

import argparse
import math
import random
import sys
from datetime import date, timedelta
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from rp_core import ContentStore, RankCatalog, count_scores_by_rank  # noqa: E402
from rp_renderer_effects import RpImageRenderer  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="生成 taiko_rp 本地预览图片")
    parser.add_argument(
        "--score",
        type=int,
        nargs="+",
        default=[0, 25, 50, 100],
        help="要预览的 RP 值，可输入多个；默认生成 0、25、50、100",
    )
    parser.add_argument("--user-name", default="本地测试用户", help="预览图中的用户名称")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parent / "output",
        help="输出目录",
    )
    parser.add_argument("--seed", type=int, default=20260813, help="随机种子，便于复现")
    return parser


def sample_history() -> tuple[list[dict], list[int]]:
    """构造 30 次折线数据和 120 次等级累计数据。"""
    end_date = date.today()
    recent_scores = [
        max(0, min(100, round(54 + 33 * math.sin(index * 0.73) + (index % 4) * 4)))
        for index in range(30)
    ]
    records = [
        {
            "date": (end_date - timedelta(days=29 - index)).isoformat(),
            "luck_value": score,
        }
        for index, score in enumerate(recent_scores)
    ]
    rng = random.Random(9917)
    all_scores = recent_scores + [rng.randint(0, 100) for _ in range(90)]
    return records, all_scores


def main() -> int:
    args = build_parser().parse_args()
    invalid = [score for score in args.score if not 0 <= score <= 100]
    if invalid:
        print(f"错误：RP 值必须位于 0~100，当前无效值：{invalid}", file=sys.stderr)
        return 2

    resource_dir = PROJECT_ROOT / "resource"
    rank_catalog = RankCatalog.from_file(resource_dir / "ranks.json")
    content_store = ContentStore.from_file(resource_dir / "content.json")
    renderer = RpImageRenderer(resource_dir, rank_catalog)
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    rng = random.Random(args.seed)

    generated: list[Path] = []
    for score in args.score:
        record = content_store.make_fortune(score, rng)
        record.update(
            {
                "user_name": args.user_name,
                "rp_id": rank_catalog.result_icon_for_score(score, rng),
            }
        )
        path = renderer.render_rp_image(record, output_dir / f"rp_{score:03d}.png")
        generated.append(path)

    records, all_scores = sample_history()
    counts = count_scores_by_rank(all_scores, rank_catalog)
    generated.append(
        renderer.render_statistics_image(
            args.user_name,
            records,
            counts,
            output_dir / "rp_statistics.png",
        )
    )

    print("预览生成完成：")
    for path in generated:
        print(f"  {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
