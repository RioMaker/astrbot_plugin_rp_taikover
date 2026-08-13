import importlib
import sys
import types
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _identity_decorator(*_args, **_kwargs):
    return lambda target: target


def test_main_supports_astrbot_package_loading():
    """模拟 AstrBot 以“插件包.main”形式加载入口模块。"""
    created_modules: list[str] = []

    def make_module(name: str, package: bool = False) -> types.ModuleType:
        module = types.ModuleType(name)
        if package:
            module.__path__ = []
        sys.modules[name] = module
        created_modules.append(name)
        return module

    astrbot = make_module("astrbot", package=True)
    api = make_module("astrbot.api", package=True)
    components = make_module("astrbot.api.message_components")
    event = make_module("astrbot.api.event", package=True)
    event_filter = make_module("astrbot.api.event.filter")
    star = make_module("astrbot.api.star")
    core = make_module("astrbot.core")

    astrbot.api = api
    api.message_components = components
    api.logger = types.SimpleNamespace(
        debug=lambda *_args, **_kwargs: None,
        info=lambda *_args, **_kwargs: None,
        warning=lambda *_args, **_kwargs: None,
        error=lambda *_args, **_kwargs: None,
        exception=lambda *_args, **_kwargs: None,
    )
    event.AstrMessageEvent = type("AstrMessageEvent", (), {})
    event.filter = types.SimpleNamespace(
        command=_identity_decorator,
        permission_type=_identity_decorator,
    )
    event_filter.PermissionType = types.SimpleNamespace(ADMIN="ADMIN")
    star.Context = type("Context", (), {})
    star.Star = type("Star", (), {})
    star.StarTools = type("StarTools", (), {})
    star.register = _identity_decorator
    core.AstrBotConfig = dict

    package_name = "astrbot_plugin_rp_taikover_main_test"
    package = make_module(package_name, package=True)
    package.__path__ = [str(ROOT)]
    package.__package__ = package_name

    try:
        main_module = importlib.import_module(f"{package_name}.main")
        assert main_module.ContentStore.__module__ == f"{package_name}.rp_core"
        assert main_module.RpImageRenderer.__module__ == f"{package_name}.rp_renderer_effects"
    finally:
        for module_name in list(sys.modules):
            if module_name == package_name or module_name.startswith(f"{package_name}."):
                sys.modules.pop(module_name, None)
        for module_name in reversed(created_modules):
            sys.modules.pop(module_name, None)
