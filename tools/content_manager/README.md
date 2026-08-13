# 内容表导入工具

支持 `.xlsx`、`.xlsm` 和 UTF-8 `.csv`。表格使用一张名为“内容库”的工作表，列为：

| 类型 | 内容 | RP下限 | RP上限 | 启用 | 备注 |
|---|---|---:|---:|---|---|
| 今日签 | 大吉 | 80 | 100 | 是 | 高 RP 签文 |
| 幸运色 | 彩虹色 | 100 | 100 | 是 | 仅 100 |
| 宜 | 练习高难度谱面 | 70 |  | 是 | 上限留空 |
| 忌 | 冲动消费 |  |  | 是 | 范围均留空，任意 RP 可抽中 |

规则：

- 类型可填 `今日签`、`幸运色`、`宜`、`忌`；
- `RP下限`/`RP上限` 留空代表该方向不限制，填写时必须是 0–100 整数；
- 上下限都包含边界；
- `启用` 留空默认启用，也可填 是/否、1/0、true/false；
- 每个分类必须覆盖 0–100 的每一个 RP，否则拒绝导入，避免插件运行时无内容可抽；
- 正式写入前会完整校验；覆盖现有 JSON 时自动生成带时间戳的备份。

先校验：

```powershell
python tools/content_manager/import_content.py outputs/content_template/content_template.xlsx --dry-run
```

确认后导入：

```powershell
python tools/content_manager/import_content.py outputs/content_template/content_template.xlsx
```
