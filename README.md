# astrbot_plugin_taiko_rp

为 AstrBot 提供每日 Taiko RP 运势、历史波动统计、群排行榜和可维护内容库。

## 命令

- `/rp`：生成或查看当天 RP。同一用户同一天始终返回同一条数据库记录；
- `/rp 统计`：绘制最近 30 条 RP 折线图，并统计该用户全部历史记录中各等级的数量；
- `/rp 历史 [日期/条数]`：用文字查看已保存的历史 RP 及完整签文、幸运色、宜忌等内容，默认最近 30 条，最多 365 条。例如 `/rp 历史 2026-08-01` 或 `/rp 历史 7`；
- `/rp 排行榜 [人数]`：绘制本群今日 RP 排行榜，默认 50 人、最多 200 人；
- `/rp 存储`：管理员查看数据库、内容快照与头像缓存的实际占用；
- `/rp 清理 <天数>`：管理员删除指定天数以前的数据并压缩数据库；
- `/rp help`：显示帮助；
- `/rp_test 0~100`：管理员本地指定分数预览，不修改真实记录；
- `/rp_init`：管理员重新初始化数据库并重载内容库。插件启动时也会自动初始化。

RP=100 使用全画布彩虹背景，RP=0 使用粗颗粒灰黑雪花屏背景；特殊背景只在文字处添加局部可读性底板。RP<50 不显示灰色评价 Logo，中心区域留空。统计图中的等级名称旁直接使用对应等级小图标。

雪花颗粒可在 AstrBot 插件配置中调整：`STATIC_BLOCK_SIZE` 越大颗粒越粗，`STATIC_GLITCH_BANDS` 控制横向故障带数量。

## LLM 工具调用（v0.7.0）

插件通过 [AstrBot 官方 LLM 工具接口](https://docs.astrbot.app/dev/star/guides/ai.html) 注册以下工具。加载或重载插件后，在 AstrBot 的工具管理中确认它们已启用，并允许当前会话使用的人格调用这些工具；当前聊天模型也需要支持工具调用。

| 工具 | 功能与参数 |
| --- | --- |
| `get_today_rp` | 生成或复用当前发送者的今日 RP，返回完整文本数据；`show_image` 默认 `true`，发送原有 RP 图片，需要仅文字解读时传 `false`。 |
| `get_rp_history` | 查询当前发送者的历史完整快照；`start_date`、`end_date` 使用 `YYYY-MM-DD`，留空不限该侧日期，边界包含当天；`limit` 默认 30，范围 1–365。查单日时两个日期传相同值。 |
| `get_rp_statistics` | 返回当前发送者最近 30 条分数及全部已保存历史的等级计数，与 `/rp 统计` 的数据范围一致。 |
| `get_rp_leaderboard` | 返回当前群的今日排行榜；`limit` 默认 50，范围 1–200。沿用 `/rp 排行榜` 的群成员筛选与跨群登记规则。 |

可以直接对机器人说：“帮我测一下今天的人品”“查一下我 2026 年 8 月 1 日的 RP 和宜忌”“比较我 8 月 1 日到 8 月 7 日的 RP”“看看我最近的人品统计”或“本群今天 RP 谁最高”。模型会根据请求选择工具，再利用返回的真实记录回答。

日期按北京时间（UTC+8）理解；“最近 N 条”表示抽取记录数，并不保证连续 N 个日历日。历史、统计、排行榜查询不会补抽缺失日期。今日工具与 `/rp` 共用每日记录和群成员登记流程，同一天不会因 LLM 调用而重新抽取。历史查询自动使用消息发送者身份；排行榜仅包含插件已确认且有今日 RP 的本群成员。工具调用会保留 LLM 后续回复流程。

## 跨群排行榜

今日 RP 按平台用户 ID 全局保存，不因群聊不同而重新抽取。用户已在 A 群执行 `/rp` 后，在 B 群直接执行 `/rp 排行榜`，插件会先把该用户登记到 B 群排行榜，再复用 A 群的今日 RP；无需在 B 群重复 `/rp`。

排行榜仍然是“本群排行榜”。插件只会同步已经确认过群成员身份的用户，不会把其他群的全部 RP 用户直接暴露到当前群。

## 持久化数据与升级

数据库和头像缓存遵循 [AstrBot 官方插件存储规范](https://docs.astrbot.app/dev/star/guides/storage.html)，位于：

```text
data/plugin_data/astrbot_plugin_taiko_rp/
├─ luck_records_advanced.db
└─ avatar_cache/
```

该目录独立于 `data/plugins/<插件源码目录>`，普通插件更新、卸载后重新安装不会删除 RP 数据。卸载时如果管理员明确选择“同时删除插件数据”，AstrBot 仍会按用户意图清理持久层；重要数据建议另行备份。

从 v0.6.1 或更早版本首次升级时，旧数据库仍位于插件源码目录。AstrBot 的标准更新流程会先删除旧源码目录，因此请在首次更新前停止 AstrBot，并把：

```text
data/plugins/<旧插件目录>/luck_records_advanced.db
```

复制到：

```text
data/plugin_data/astrbot_plugin_taiko_rp/luck_records_advanced.db
```

也可以先原位覆盖新版源码并重载一次插件；新版启动时会使用 SQLite backup API 自动迁移旧库并执行完整性检查。目标持久库已经存在时绝不会被旧库覆盖。完成这次迁移后，后续即可正常使用 AstrBot 的插件更新功能。

## 本地预览（无需 AstrBot）

Windows 双击 `local_test/run_preview.bat`，或在项目根目录运行：

```powershell
python local_test/preview.py
```

图片输出到 `local_test/output/`。默认生成 RP=0、25、50、100、统计图和 50 人排行榜长图；也可以指定任意测试值与排行榜人数：

```powershell
python local_test/preview.py --score 0 25 88 100 --user-name 小咚 --leaderboard-count 100
```

## 宜忌、今日签与幸运色内容库

运行时会选择 `resource/content.json` 与 `resource/content2.json` 中 `schema_version` 最高的版本；当前默认使用 `content2.json`。每一项均支持：

```json
{
  "text": "彩虹色",
  "min_rp": 100,
  "max_rp": 100,
  "note": "仅在 RP=100 时出现"
}
```

`min_rp` 或 `max_rp` 为 `null` 时代表该方向不限制；上下限均包含边界值。当前 v2 还包含推荐 BPM、推荐星级、太鼓建议和今日事件。每日抽中的全部字段以“结构版本 + 紧凑 JSON 快照”保存；字段名称等结构信息按版本只保存一次，因此后续增删字段不会改变历史结果，也不会在每条记录中重复占用空间。

完整 Excel 模板位于 `outputs/content_template/content_template.xlsx`。编辑后先校验：

```powershell
python tools/content_manager/import_content.py outputs/content_template/content_template.xlsx --dry-run
```

确认后导入：

```powershell
python tools/content_manager/import_content.py outputs/content_template/content_template.xlsx
```

导入器也支持 UTF-8 CSV；正式覆盖前会校验字段、RP 范围和 0–100 内容覆盖，并自动备份旧 JSON。详细规则见 `tools/content_manager/README.md`。

## 依赖与测试

```powershell
pip install -r requirements.txt pytest docstring-parser
python -m pytest -q
```

测试覆盖数据库每日复用、旧库持久层迁移与防覆盖、跨群排行榜登记、群排行榜筛选与排序、近 30 条查询、等级总数、RP 范围筛选、表格校验、0/100 特殊背景、低分无 Logo、统计图和排行榜长图输出。

`pytest` 和 `docstring-parser` 是测试依赖，后者用于核对 AstrBot 工具参数注释。新增测试覆盖工具参数解析约定、命令和工具共用今日记录、并发每日复用、日期范围与数量校验、历史内容快照、当前用户隔离和本群排行榜范围。这里的测试使用真实 SQLite 数据库与模拟 AstrBot 消息事件；实际模型选用工具和平台发送仍需在 AstrBot 环境中验证。
