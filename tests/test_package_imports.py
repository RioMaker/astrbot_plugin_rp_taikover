import importlib
import sys
import types
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_renderer_modules_support_astrbot_package_import():
    """AstrBot 会把插件作为包加载，包内模块必须使用相对导入。"""
    package_name = "astrbot_plugin_rp_taikover_test"
    package = types.ModuleType(package_name)
    package.__path__ = [str(ROOT)]
    package.__package__ = package_name
    sys.modules[package_name] = package
    try:
        core = importlib.import_module(f"{package_name}.rp_core")
        renderer = importlib.import_module(f"{package_name}.rp_renderer")
        effects = importlib.import_module(f"{package_name}.rp_renderer_effects")
        assert renderer.RankCatalog is core.RankCatalog
        assert issubclass(effects.RpImageRenderer, renderer.RpImageRenderer)
    finally:
        for module_name in list(sys.modules):
            if module_name == package_name or module_name.startswith(f"{package_name}."):
                sys.modules.pop(module_name, None)
