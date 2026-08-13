# 本地图片预览

本目录不依赖 AstrBot。Windows 可双击 `run_preview.bat`，或在项目根目录运行：

```powershell
python local_test/preview.py
```

默认生成：

- `rp_000.png`：RP=0 的粗颗粒灰黑雪花屏背景；
- `rp_025.png`：低分信号仪表，不使用灰色评价 Logo；
- `rp_050.png`：普通背景示例；
- `rp_100.png`：RP=100 的全画布彩虹背景；
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
