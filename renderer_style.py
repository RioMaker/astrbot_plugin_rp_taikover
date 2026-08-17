from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Mapping


def deep_merge(base: Mapping[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    """递归合并配置；后加载的值覆盖前者。"""
    result = copy.deepcopy(dict(base))
    for key, value in override.items():
        if isinstance(value, Mapping) and isinstance(result.get(key), Mapping):
            result[str(key)] = deep_merge(result[str(key)], value)
        else:
            result[str(key)] = copy.deepcopy(value)
    return result


def _load_json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"渲染配置不存在：{path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"渲染配置 JSON 无效：{path}（{exc}）") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"渲染配置顶层必须是对象：{path}")
    return payload


def _normalize_image_paths(payload: Mapping[str, Any], base_dir: Path) -> dict[str, Any]:
    normalized = copy.deepcopy(dict(payload))
    backgrounds = normalized.get("backgrounds")
    if not isinstance(backgrounds, dict):
        return normalized
    for raw_style in backgrounds.values():
        if not isinstance(raw_style, dict):
            continue
        image = str(raw_style.get("image") or "").strip()
        if not image:
            continue
        image_path = Path(image).expanduser()
        if not image_path.is_absolute():
            image_path = base_dir / image_path
        raw_style["image"] = str(image_path.resolve())
    return normalized


def _parse_inline_json(raw: Any) -> dict[str, Any]:
    if raw in (None, ""):
        return {}
    if isinstance(raw, Mapping):
        return dict(raw)
    try:
        payload = json.loads(str(raw))
    except json.JSONDecodeError as exc:
        raise ValueError(f"RENDERER_CONFIG_JSON 无效：{exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("RENDERER_CONFIG_JSON 顶层必须是对象")
    return payload


def _positive_int(value: Any, key: str, minimum: int = 12, maximum: int = 120) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{key} 必须是整数") from exc
    if not minimum <= number <= maximum:
        raise ValueError(f"{key} 必须位于 {minimum}~{maximum}")
    return number


def load_renderer_style(
    resource_dir: str | Path,
    plugin_config: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """加载内置默认、用户文件、内联 JSON 和 AstrBot 直接覆盖项。"""
    resource_dir = Path(resource_dir)
    plugin_dir = resource_dir.parent
    config = plugin_config or {}
    default_path = resource_dir / "config" / "renderer_defaults.json"
    style = _normalize_image_paths(_load_json_object(default_path), default_path.parent)

    custom_path_text = str(config.get("RENDERER_CONFIG_PATH") or "").strip()
    if custom_path_text:
        custom_path = Path(custom_path_text).expanduser()
        if not custom_path.is_absolute():
            custom_path = plugin_dir / custom_path
        custom_path = custom_path.resolve()
        custom = _normalize_image_paths(_load_json_object(custom_path), custom_path.parent)
        style = deep_merge(style, custom)

    inline = _parse_inline_json(config.get("RENDERER_CONFIG_JSON"))
    if inline:
        style = deep_merge(style, _normalize_image_paths(inline, plugin_dir))

    typography = style.setdefault("typography", {})
    direct_sizes = {
        "RP_VALUE_FONT_SIZE": "rp_value_font_size",
        "USER_GREETING_FONT_SIZE": "user_greeting_font_size",
    }
    for config_key, style_key in direct_sizes.items():
        raw_value = config.get(config_key)
        if raw_value not in (None, "", 0, "0"):
            typography[style_key] = _positive_int(raw_value, config_key)

    backgrounds = style.setdefault("backgrounds", {})
    direct_images = {
        "DEFAULT_BACKGROUND_IMAGE": "default",
        "RP0_BACKGROUND_IMAGE": "0",
        "RP100_BACKGROUND_IMAGE": "100",
    }
    for config_key, selector in direct_images.items():
        raw_path = str(config.get(config_key) or "").strip()
        if not raw_path:
            continue
        image_path = Path(raw_path).expanduser()
        if not image_path.is_absolute():
            image_path = plugin_dir / image_path
        rule = backgrounds.setdefault(selector, {})
        if not isinstance(rule, dict):
            rule = {}
            backgrounds[selector] = rule
        rule["image"] = str(image_path.resolve())

    typography["rp_value_font_size"] = _positive_int(
        typography.get("rp_value_font_size", 52), "typography.rp_value_font_size"
    )
    typography["user_greeting_font_size"] = _positive_int(
        typography.get("user_greeting_font_size", 28),
        "typography.user_greeting_font_size",
    )
    if not isinstance(backgrounds.get("default"), dict):
        raise ValueError("backgrounds.default 必须是对象")
    return style


def _selector_matches(selector: str, rp_value: int) -> bool:
    if "-" not in selector:
        return False
    left, right = selector.split("-", 1)
    try:
        minimum, maximum = int(left.strip()), int(right.strip())
    except ValueError:
        return False
    return 0 <= minimum <= rp_value <= maximum <= 100


def background_style_for_score(style: Mapping[str, Any], rp_value: int) -> dict[str, Any]:
    """默认样式打底，区间按 JSON 顺序叠加，精确分值最后覆盖。"""
    backgrounds = style.get("backgrounds", {})
    if not isinstance(backgrounds, Mapping):
        return {}
    resolved = dict(backgrounds.get("default", {}))
    for selector, rule in backgrounds.items():
        if selector == "default" or not isinstance(rule, Mapping):
            continue
        if _selector_matches(str(selector), rp_value):
            resolved = deep_merge(resolved, rule)
    exact = backgrounds.get(str(int(rp_value)))
    if isinstance(exact, Mapping):
        resolved = deep_merge(resolved, exact)
    return resolved
