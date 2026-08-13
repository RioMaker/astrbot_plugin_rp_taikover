# 本地图片预览

本目录不依赖 AstrBot。Windows 可双击 `run_preview.bat`，或在项目根目录运行：

```powershell
python local_test/preview.py
```

默认生成：

- `rp_000.png`：RP=0 的粗颗粒灰黑雪花屏背景；
- `rp_025.png`：低分不使用灰色评价 Logo，中心区域留空；
- `rp_050.png`：普通背景示例；
- `rp_100.png`：RP=100 的全画布彩虹背景；
- 每张默认 RP 图都会展示 content2 的 8 个字段，并按内容高度自动增长；
- `rp_statistics.png`：30 次折线与所有等级的累计数量卡片；
- `rp_leaderboard_50.png`：50 人群 RP 排行榜长图，包含圆形模拟头像和前三王冠。

自定义分数示例：

```powershell
python local_test/preview.py --score 0 25 88 100 --user-name 小咚 --leaderboard-count 100
```

生成文件都放在 `local_test/output/`，该目录已设置为不纳入 Git。

雪花参数可在 AstrBot 插件配置中修改：`STATIC_BLOCK_SIZE` 越大颗粒越粗，
`STATIC_GLITCH_BANDS` 越大横向撕裂带越密。代码默认值位于
`rp_renderer_effects.py` 的 `RpImageRenderer.__init__()`。

## 布局试验场

正式布局定稿前，可以一次生成多个带代号的候选方案：

    python local_test/layout_lab.py --score 88 --variants D3A D3B D3C

输出位于 `local_test/layout_lab_output/`。D3A/D3B/D3C 分别是三种横向矩形比例：短字段环绕中心大 Logo，可能超长的太鼓建议和今日事件放在底部双栏。所有候选方案使用同一组抽取内容，便于只比较布局；该目录已被 Git 忽略，不会混入插件发布包。