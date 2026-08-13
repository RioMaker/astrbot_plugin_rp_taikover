# astrbot_plugin_taiko_rp

为 AstrBot 提供每日 Taiko RP 运势、历史波动统计和可维护内容库。

## 命令

- `/rp`：生成或查看当天 RP。同一用户同一天始终返回同一条数据库记录；
- `/rp 统计`：绘制最近 30 条 RP 折线图，并统计该用户全部历史记录中各等级的数量；
- `/rp help`：显示帮助；
- `/rp_test 0~100`：管理员本地指定分数预览，不修改真实记录；
- `/rp_init`：管理员重新初始化数据库并重载内容库。插件启动时也会自动初始化。

RP=100 使用全画布彩虹背景，RP=0 使用粗颗粒灰黑雪花屏背景；特殊背景只在文字处添加局部可读性底板。RP<50 不显示灰色评价 Logo，改用低信号仪表。统计图中的等级名称旁直接使用对应等级小图标。

雪花颗粒可在 AstrBot 插件配置中调整：`STATIC_BLOCK_SIZE` 越大颗粒越粗，`STATIC_GLITCH_BANDS` 控制横向故障带数量。

## 本地预览（无需 AstrBot）

Windows 双击 `local_test/run_preview.bat`，或在项目根目录运行：

```powershell
python local_test/preview.py
```

图片输出到 `local_test/output/`。默认生成 RP=0、25、50、100 和一张统计图；也可以指定任意测试值：

```powershell
python local_test/preview.py --score 0 25 88 100 --user-name 小咚
```

## 宜忌、今日签与幸运色内容库

运行时内容位于 `resource/content.json`。每一项均支持：

```json
{
  "text": "彩虹色",
  "min_rp": 100,
  "max_rp": 100,
  "note": "仅在 RP=100 时出现"
}
```

`min_rp` 或 `max_rp` 为 `null` 时代表该方向不限制；上下限均包含边界值。

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
pip install -r requirements.txt
python -m pytest -q
```

测试覆盖数据库每日复用、近 30 条查询、等级总数、RP 范围筛选、表格校验、0/100 特殊背景、低分无 Logo 和统计图输出。
