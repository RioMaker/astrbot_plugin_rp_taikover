# 本地渲染配置

`renderer.json` 会覆盖插件内置的 `resource/config/renderer_defaults.json`，并由
`local_test/preview.py` 自动加载。图片路径相对于当前 JSON 文件，也可以填写绝对路径。

`backgrounds` 支持：

- `default`：所有 RP 的默认样式；
- 精确分值，例如 `0`、`50`、`100`；
- RP 区间，例如 `1-49`、`80-99`。

每项可配置 `mode`（`soft_gradient`、`glitch`、`rainbow`、`image`）、`image`、
`image_fit`（`cover` 或 `contain`）、`overlay_color`、`overlay_opacity`，以及：

```json
{
  "text": {
    "primary": "#FFFFFF",
    "secondary": "#E5E7EB",
    "score": "#FFFFFF",
    "stroke": "#000000",
    "stroke_width": 3
  },
  "surface": {
    "fill": "#050607",
    "opacity": 178,
    "outline": "#FFFFFF",
    "outline_opacity": 42
  }
}
```

`text.score` 可设为 `rank`，表示跟随当前 RP 等级色。透明度范围为 0~255。
