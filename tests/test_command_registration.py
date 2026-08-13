import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_rp_subcommands_are_routed_by_one_parameterized_handler():
    """禁止重新注册带空格的 rp 子命令，否则会与 /rp 重复触发。"""
    tree = ast.parse((ROOT / "main.py").read_text(encoding="utf-8"))
    command_handlers: dict[str, ast.AsyncFunctionDef] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.AsyncFunctionDef):
            continue
        for decorator in node.decorator_list:
            if (
                isinstance(decorator, ast.Call)
                and isinstance(decorator.func, ast.Attribute)
                and decorator.func.attr == "command"
                and decorator.args
                and isinstance(decorator.args[0], ast.Constant)
                and isinstance(decorator.args[0].value, str)
            ):
                command_handlers[decorator.args[0].value] = node

    assert "rp" in command_handlers
    assert not any(name.startswith("rp ") or name == "rp统计" for name in command_handlers)
    rp_arguments = [argument.arg for argument in command_handlers["rp"].args.args]
    assert rp_arguments == ["self", "event", "action", "argument"]
