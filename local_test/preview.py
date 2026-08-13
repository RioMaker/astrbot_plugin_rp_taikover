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

from PIL import Image, ImageDraw


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
        "--leaderboard-count",
        type=int,
        default=50,
        help="模拟排行榜人数，默认 50，范围 1~200",
    )
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


def sample_leaderboard(count: int, rng: random.Random) -> list[dict]:
    """构造带本地模拟头像的排行榜数据。"""
    names = (
        "鼓面达人", "全连祈愿者", "不可达人", "节奏旅行者", "咚咔研究员",
        "虹冠收藏家", "今日手感很好", "夜猫鼓手", "街机巡礼者", "红蓝音符",
    )
    scores = sorted((rng.randint(0, 100) for _ in range(count)), reverse=True)
    entries: list[dict] = []
    for index, score in enumerate(scores, start=1):
        avatar = Image.new(
            "RGBA",
            (128, 128),
            (
                45 + index * 29 % 160,
                65 + index * 47 % 150,
                85 + index * 61 % 140,
                255,
            ),
        )
        avatar_draw = ImageDraw.Draw(avatar)
        avatar_draw.ellipse((36, 20, 92, 76), fill=(255, 229, 199, 255))
        avatar_draw.ellipse((22, 72, 106, 145), fill=(235, 241, 255, 255))
        avatar_draw.ellipse((50, 46, 56, 52), fill=(38, 45, 58, 255))
        avatar_draw.ellipse((72, 46, 78, 52), fill=(38, 45, 58, 255))
        entries.append(
            {
                "user_id": str(100000000 + index),
                "user_name": f"{names[(index - 1) % len(names)]} {index:02d}",
                "luck_value": score,
                "avatar": avatar,
            }
        )
    return entries


def main() -> int:
    args = build_parser().parse_args()
    invalid = [score for score in args.score if not 0 <= score <= 100]
    if invalid:
        print(f"错误：RP 值必须位于 0~100，当前无效值：{invalid}", file=sys.stderr)
        return 2
    if not 1 <= args.leaderboard_count <= 200:
        print("错误：排行榜人数必须位于 1~200", file=sys.stderr)
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
    generated.append(
        renderer.render_leaderboard_image(
            "本地测试群 · 987654321",
            sample_leaderboard(args.leaderboard_count, rng),
            output_dir / f"rp_leaderboard_{args.leaderboard_count}.png",
        )
    )

    print("预览生成完成：")
    for path in generated:
        print(f"  {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
