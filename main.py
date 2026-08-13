import asyncio
import hashlib
import random
import time
import urllib.request
from pathlib import Path

import astrbot.api.message_components as Comp
from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.event.filter import PermissionType
from astrbot.api.star import Context, Star, StarTools, register
from astrbot.core import AstrBotConfig

if __package__:
    from .rp_core import ContentStore, LuckDatabase, RankCatalog, select_content_path
    from .rp_renderer_effects import RpImageRenderer
else:  # 兼容直接运行源码进行本地调试
    from rp_core import ContentStore, LuckDatabase, RankCatalog, select_content_path
    from rp_renderer_effects import RpImageRenderer


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "luck_records_advanced.db"

INTRO_INFO = [
    "小咚祈祷中...",
    "小咔祈祷中...",
    "通关祈祷中...",
    "全连祈祷中...",
    "全良祈祷中...",
    "超级 combo 祈祷中...别断了...",
    "满分之梦祈祷中...求个好运气...",
    "太鼓之魂祈祷中...请给我好运...",
    "音符流畅祈祷中...求个完美音符...",
    "鼓声低语中...命运的回响已起...",
    "节奏涌动中...无尽的波动在召唤...",
    "灵魂共振中...节奏与我同在...",
]


@register("taiko_rp", "Rio", "测一下 taiko 人品", "0.6.0")
class taikoRP(Star):
    """每日 RP、历史统计与可扩展宜忌内容库。"""

    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self.admins_id = {str(value) for value in context.get_config().get("admins_id", [])}

        self.plugin_dir = Path(__file__).resolve().parent
        self.plugin_data_dir = StarTools.get_data_dir("astrbot_plugin_rollpig")
        self.resource_dir = self.plugin_dir / "resource"
        self.image_dir = self.resource_dir / "image"
        self.plugin_data_dir.mkdir(parents=True, exist_ok=True)

        self.rank_catalog = RankCatalog.from_file(self.resource_dir / "ranks.json")
        self.content_path = select_content_path(self.resource_dir)
        self.content_store = ContentStore.from_file(self.content_path)
        # 保持旧版数据库位置不变，升级后可直接读取既有历史记录。
        self.database = LuckDatabase(DB_PATH, self.content_store)
        self.database.init()
        self.renderer = RpImageRenderer(self.resource_dir, self.rank_catalog, config)
        logger.info("taiko_rp：数据库、内容库与图片渲染器初始化完成")

    def _decorate_record(self, record: dict, user_name: str) -> dict:
        result = dict(record)
        result["rp_id"] = self.rank_catalog.result_icon_for_score(result["luck_value"])
        result["user_name"] = user_name
        return result

    @staticmethod
    def _object_value(source, key: str):
        if isinstance(source, dict):
            return source.get(key)
        return getattr(source, key, None)

    def _group_scope(self, event: AstrMessageEvent) -> str:
        group_id = str(event.get_group_id() or "")
        if not group_id:
            return ""
        try:
            platform_name = str(event.get_platform_name() or "")
        except Exception:
            platform_name = ""
        return f"{platform_name}:{group_id}" if platform_name else group_id

    def _sender_avatar_url(self, event: AstrMessageEvent) -> str:
        """尽量从适配器事件提取头像；QQ 缺失时使用公开头像地址。"""
        message_obj = getattr(event, "message_obj", None)
        sender = getattr(message_obj, "sender", None)
        raw_message = getattr(message_obj, "raw_message", None)
        containers = [sender, raw_message]
        if isinstance(raw_message, dict):
            containers.extend(
                raw_message.get(key)
                for key in ("sender", "user", "author", "member")
                if raw_message.get(key)
            )

        for container in containers:
            for key in ("avatar_url", "avatar", "icon_url", "icon", "face"):
                candidate = self._object_value(container, key)
                if isinstance(candidate, dict):
                    candidate = candidate.get("url") or candidate.get("src")
                candidate = str(candidate or "").strip()
                if candidate.startswith(("http://", "https://")):
                    return candidate

        user_id = str(event.get_sender_id())
        try:
            platform_name = str(event.get_platform_name() or "").lower()
        except Exception:
            platform_name = ""
        if user_id.isdigit() and ("qq" in platform_name or "aiocqhttp" in platform_name):
            return f"https://q1.qlogo.cn/g?b=qq&nk={user_id}&s=640"
        return ""

    def _download_avatar(self, user_id: str, avatar_url: str) -> Path | None:
        cache_dir = self.plugin_data_dir / "avatar_cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_key = hashlib.sha256(
            f"{user_id}\0{avatar_url}".encode("utf-8")
        ).hexdigest()[:24]
        cache_path = cache_dir / f"{cache_key}.img"
        try:
            if (
                cache_path.exists()
                and cache_path.stat().st_size > 0
                and time.time() - cache_path.stat().st_mtime < 24 * 60 * 60
            ):
                return cache_path
            request = urllib.request.Request(
                avatar_url,
                headers={"User-Agent": "AstrBot taiko_rp leaderboard/0.6"},
            )
            with urllib.request.urlopen(request, timeout=8) as response:
                content = response.read(5 * 1024 * 1024 + 1)
            if not content or len(content) > 5 * 1024 * 1024:
                raise ValueError("头像为空或超过 5 MiB")
            temporary_path = cache_path.with_suffix(".tmp")
            temporary_path.write_bytes(content)
            temporary_path.replace(cache_path)
            return cache_path
        except Exception as exc:
            logger.debug(f"排行榜头像获取失败 user_id={user_id}: {exc}")
            cache_path.with_suffix(".tmp").unlink(missing_ok=True)
            return cache_path if cache_path.exists() else None

    async def _prepare_leaderboard_entries(self, records: list[dict]) -> list[dict]:
        semaphore = asyncio.Semaphore(8)

        async def prepare(record: dict) -> dict:
            result = dict(record)
            avatar_url = str(record.get("avatar_url") or "")
            if not avatar_url:
                result["avatar_path"] = None
                return result
            async with semaphore:
                avatar_path = await asyncio.to_thread(
                    self._download_avatar,
                    str(record["user_id"]),
                    avatar_url,
                )
            result["avatar_path"] = avatar_path
            return result

        return list(await asyncio.gather(*(prepare(record) for record in records)))

    def _is_plugin_admin(self, event: AstrMessageEvent) -> bool:
        return str(event.get_sender_id()) in self.admins_id

    @staticmethod
    def _format_bytes(size: float | int) -> str:
        value = float(size)
        units = ("B", "KiB", "MiB", "GiB", "TiB")
        for unit in units:
            if value < 1024 or unit == units[-1]:
                return f"{value:.0f} {unit}" if unit == "B" else f"{value:.2f} {unit}"
            value /= 1024
        return f"{value:.2f} TiB"

    def _avatar_cache_stats(self) -> dict[str, int]:
        cache_dir = self.plugin_data_dir / "avatar_cache"
        files = [path for path in cache_dir.rglob("*") if path.is_file()] if cache_dir.exists() else []
        return {
            "file_count": len(files),
            "bytes": sum(path.stat().st_size for path in files),
        }

    def _purge_avatar_cache(self, days: int) -> dict[str, int]:
        cache_dir = self.plugin_data_dir / "avatar_cache"
        if not cache_dir.exists():
            return {"files_deleted": 0, "bytes_deleted": 0}
        cutoff_timestamp = time.time() - int(days) * 24 * 60 * 60
        files_deleted = 0
        bytes_deleted = 0
        resolved_cache = cache_dir.resolve()
        for path in cache_dir.rglob("*"):
            if not path.is_file() or path.stat().st_mtime >= cutoff_timestamp:
                continue
            try:
                path.resolve().relative_to(resolved_cache)
            except ValueError:
                continue
            size = path.stat().st_size
            path.unlink(missing_ok=True)
            files_deleted += 1
            bytes_deleted += size
        return {"files_deleted": files_deleted, "bytes_deleted": bytes_deleted}

    async def rp_storage(self, event: AstrMessageEvent):
        if not self._is_plugin_admin(event):
            await event.send(event.plain_result("无权限，请联系管理员。"))
            return
        stats, avatar_stats = await asyncio.gather(
            asyncio.to_thread(self.database.storage_stats),
            asyncio.to_thread(self._avatar_cache_stats),
        )
        versions = "、".join(
            f"v{version}: {amount} 条"
            for version, amount in stats["schema_versions"].items()
        ) or "无记录"
        total_bytes = stats["database_files_bytes"] + avatar_stats["bytes"]
        text = (
            "【RP 存储占用】\n"
            f"数据库文件：{self._format_bytes(stats['database_files_bytes'])}\n"
            f"可回收空页：{self._format_bytes(stats['reclaimable_bytes'])}\n"
            f"每日记录：{stats['record_count']} 条"
            f"（{stats['oldest_date'] or '无'} ～ {stats['newest_date'] or '无'}）\n"
            f"内容快照：{stats['snapshot_count']} 条 / "
            f"{self._format_bytes(stats['snapshot_bytes'])} / "
            f"平均 {self._format_bytes(stats['average_snapshot_bytes'])} 每条\n"
            f"旧版固定字段：{self._format_bytes(stats['legacy_content_bytes'])}\n"
            f"内容版本：{versions}\n"
            f"字段结构：{stats['schema_definition_count']} 个 / "
            f"{self._format_bytes(stats['schema_definition_bytes'])}\n"
            f"群成员索引：{stats['group_member_count']} 条\n"
            f"头像缓存：{avatar_stats['file_count']} 个 / "
            f"{self._format_bytes(avatar_stats['bytes'])}\n"
            f"合计占用：{self._format_bytes(total_bytes)}\n"
            "清理示例：/rp 清理 30（删除 30 天以前的数据）"
        )
        await event.send(event.plain_result(text))

    async def rp_cleanup(self, event: AstrMessageEvent, days_text: str):
        if not self._is_plugin_admin(event):
            await event.send(event.plain_result("无权限，请联系管理员。"))
            return
        try:
            days = int(days_text.strip())
        except ValueError:
            await event.send(event.plain_result("用法：/rp 清理 <保留天数>，例如 /rp 清理 30"))
            return
        if not 0 <= days <= 36500:
            await event.send(event.plain_result("保留天数必须位于 0~36500。"))
            return
        database_result, avatar_result = await asyncio.gather(
            asyncio.to_thread(self.database.purge_older_than, days),
            asyncio.to_thread(self._purge_avatar_cache, days),
        )
        total_reclaimed = database_result["reclaimed_bytes"] + avatar_result["bytes_deleted"]
        text = (
            "【RP 过期数据清理完成】\n"
            f"清理边界：早于 {database_result['cutoff_date']}\n"
            f"每日记录：{database_result['records_deleted']} 条\n"
            f"群成员索引：{database_result['members_deleted']} 条\n"
            f"旧操作记录：{database_result['steals_deleted']} 条\n"
            f"头像缓存：{avatar_result['files_deleted']} 个\n"
            f"实际释放：{self._format_bytes(total_reclaimed)}\n"
            f"数据库：{self._format_bytes(database_result['before_bytes'])} → "
            f"{self._format_bytes(database_result['after_bytes'])}"
        )
        await event.send(event.plain_result(text))

    @filter.permission_type(PermissionType.ADMIN)
    @filter.command("rp_init")
    async def rp_init(self, event: AstrMessageEvent):
        """兼容旧版初始化命令；新版加载插件时会自动初始化。"""
        user_id = str(event.get_sender_id())
        if user_id not in self.admins_id:
            await event.send(event.plain_result("无权限，请联系管理员。"))
            return
        try:
            self.database.init()
            # 重新加载内容库，便于管理员替换 JSON 后手动刷新。
            content_path = select_content_path(self.resource_dir)
            content_store = ContentStore.from_file(content_path)
            previous_store = self.database.content_store
            self.database.content_store = content_store
            try:
                self.database.register_content_schema()
            except Exception:
                self.database.content_store = previous_store
                raise
            self.content_path = content_path
            self.content_store = content_store
            await event.send(event.plain_result("数据库与内容库初始化成功！"))
        except Exception as exc:
            logger.exception("taiko_rp 初始化失败")
            await event.send(event.plain_result(f"初始化失败：{exc}"))

    async def help(self, event: AstrMessageEvent):
        help_text = (
            "【RP 命令帮助】\n"
            "/rp　　　　　　　　查看/生成今天的运势\n"
            "/rp 统计　　　　　 查看近 30 次波动与全部等级统计\n"
            "/rp 排行榜 [人数]　 查看本群今日排行，默认 50，最多 200\n"
            "/rp 存储　　　　　 管理员查看数据库与缓存占用\n"
            "/rp 清理 <天数>　　 管理员删除指定天数以前的数据\n"
            "/rp help　　　　　 查看本帮助"
        )
        await event.send(event.plain_result(help_text))
        event.stop_event()

    async def rp_statistics(self, event: AstrMessageEvent):
        """绘制近 30 次 RP 折线和全历史等级数量。"""
        user_id = str(event.get_sender_id())
        records = self.database.get_recent_records(user_id, limit=30)
        if not records:
            await event.send(event.plain_result("还没有 RP 记录，先发送 /rp 抽取今天的 RP 吧。"))
            return
        counts = self.database.count_ranks(user_id, self.rank_catalog)
        try:
            image_path = await asyncio.to_thread(
                self.renderer.render_statistics_image,
                event.get_sender_name(),
                records,
                counts,
            )
            sent = await self._send_generated_image(event, image_path, "RP 统计图")
            if not sent:
                await event.send(event.plain_result("RP 统计图发送失败，请稍后重试。"))
        except Exception:
            logger.exception("生成 RP 统计图失败")
            await event.send(event.plain_result("RP 统计图生成失败，请检查插件日志。"))

    async def rp_leaderboard(self, event: AstrMessageEvent, limit_text: str = ""):
        """绘制本群当天执行过 /rp 的成员排行榜。"""
        group_id = str(event.get_group_id() or "")
        if not group_id:
            await event.send(event.plain_result("RP 排行榜仅可在群聊中使用。"))
            return

        limit = 50
        if limit_text.strip():
            try:
                limit = int(limit_text.strip())
            except ValueError:
                await event.send(event.plain_result("排行榜人数必须是 1~200 的整数。"))
                return
            if not 1 <= limit <= 200:
                await event.send(event.plain_result("排行榜人数必须位于 1~200。"))
                return

        records = self.database.get_group_leaderboard(self._group_scope(event), limit=limit)
        if not records:
            await event.send(
                event.plain_result("本群今天还没有上榜成员，先让大家发送 /rp 吧。")
            )
            return

        try:
            entries = await self._prepare_leaderboard_entries(records)
            image_path = await asyncio.to_thread(
                self.renderer.render_leaderboard_image,
                f"群 {group_id}",
                entries,
            )
            sent = await self._send_generated_image(event, image_path, "群 RP 排行榜")
            if not sent:
                await event.send(event.plain_result("群 RP 排行榜发送失败，请稍后重试。"))
        except Exception:
            logger.exception("生成群 RP 排行榜失败")
            await event.send(event.plain_result("群 RP 排行榜生成失败，请检查插件日志。"))

    @filter.command("rp")
    async def rp(self, event: AstrMessageEvent, action: str = "", argument: str = ""):
        """统一处理 /rp 及其子命令，避免命令前缀重复触发。"""
        event.stop_event()
        normalized_action = action.strip().lower()
        if normalized_action in {"统计", "stats"}:
            await self.rp_statistics(event)
            return
        if normalized_action in {"排行榜", "排行", "rank", "ranking"}:
            await self.rp_leaderboard(event, argument)
            return
        if normalized_action in {"存储", "空间", "storage"}:
            await self.rp_storage(event)
            return
        if normalized_action in {"清理", "cleanup", "purge"}:
            await self.rp_cleanup(event, argument)
            return
        if normalized_action in {"help", "帮助"}:
            await self.help(event)
            return
        if normalized_action:
            unknown = " ".join(value for value in (action, argument) if value).strip()
            await event.send(
                event.plain_result(
                    f"未知的 RP 子命令：{unknown}\n发送 /rp help 查看可用命令。"
                )
            )
            return

        user_id = str(event.get_sender_id())
        logger.info(f"taiko_rp user_id: {user_id}")
        record = self.database.get_or_create_today(user_id)
        group_scope = self._group_scope(event)
        if group_scope:
            try:
                self.database.track_group_member(
                    group_scope,
                    user_id,
                    event.get_sender_name(),
                    self._sender_avatar_url(event),
                )
            except Exception:
                logger.exception("记录群 RP 排行榜成员失败")
        record = self._decorate_record(record, event.get_sender_name())
        await self.send_rendered_rp(event, record, user_id)

    @filter.permission_type(PermissionType.ADMIN)
    @filter.command("rp_test")
    async def rp_test(self, event: AstrMessageEvent, rp_score: int):
        """管理员指定 RP 值进行预览，不修改当天真实记录。"""
        user_id = str(event.get_sender_id())
        if user_id not in self.admins_id:
            await event.send(event.plain_result("无权限，请联系管理员。"))
            return
        if not 0 <= rp_score <= 100:
            await event.send(event.plain_result("RP 测试值必须位于 0~100。"))
            return
        record = self.database.build_record(rp_value=rp_score)
        record = self._decorate_record(record, event.get_sender_name())
        await self.send_rendered_rp(event, record, user_id)

    async def _send_generated_image(
        self, event: AstrMessageEvent, image_path: Path | None, description: str
    ) -> bool:
        if not image_path or not image_path.exists():
            return False
        try:
            await event.send(event.image_result(str(image_path.absolute())))
            logger.info(f"{description}发送成功")
            return True
        except Exception:
            logger.exception(f"{description}发送失败")
            return False
        finally:
            try:
                image_path.unlink(missing_ok=True)
            except OSError as cleanup_error:
                logger.warning(f"清理临时图片失败：{cleanup_error}")

    async def send_rendered_rp(
        self, event: AstrMessageEvent, rp_data: dict, user_id: str
    ):
        """在线程池中合成并发送今日 RP 图片。"""
        image_path = None
        try:
            image_path = await asyncio.to_thread(self.renderer.render_rp_image, rp_data)
            intro_chain = [Comp.Plain(random.choice(INTRO_INFO))]
            if event.get_group_id():
                intro_chain.insert(0, Comp.At(qq=user_id))
            await event.send(event.chain_result(intro_chain))
            if await self._send_generated_image(event, image_path, "今日 RP 图片"):
                return
            image_path = None  # 已在发送函数中清理
        except Exception:
            logger.exception("生成今日 RP 图片失败")
            if image_path and image_path.exists():
                image_path.unlink(missing_ok=True)
        await self.send_fallback_msg(event, rp_data)

    async def send_fallback_msg(self, event: AstrMessageEvent, rp_data: dict):
        """图片生成失败时发送等级图标和纯文本。"""
        rank = self.rank_catalog.for_score(rp_data["luck_value"])
        fields = rp_data.get("content_fields")
        if not isinstance(fields, dict):
            fields = {
                key: rp_data[key]
                for key in ("fortune_text", "color", "advice_do", "advice_dont")
                if rp_data.get(key)
            }
        labels = rp_data.get("content_labels") if isinstance(rp_data.get("content_labels"), dict) else {}
        content_lines = [
            f"{labels.get(key, key)}：{value}" for key, value in fields.items()
        ]
        text_msg = (
            "【今日运势】\n"
            f"《{rank.name}》\n"
            f"Hi~ “{event.get_sender_name()}”\n"
            f"今日人品（RP）值：{rp_data['luck_value']}\n"
            + "\n".join(content_lines)
        )
        message_chain = []
        image_path = None
        if int(rp_data["luck_value"]) >= 50:
            image_path = self.renderer.find_image_file(str(rp_data.get("rp_id", rank.icon)))
        if image_path and image_path.exists():
            try:
                message_chain.append(Comp.Image.fromFileSystem(str(image_path.absolute())))
            except Exception:
                logger.exception("发送原始等级图片失败")
        message_chain.append(Comp.Plain(text_msg))
        await event.send(event.chain_result(message_chain))

    async def terminate(self):
        logger.info("taiko_rp 插件已卸载")
