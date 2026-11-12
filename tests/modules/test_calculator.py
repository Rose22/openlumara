# AI Written: Claude Opus 5.5, reviewed by Claude Fable 5.2

import pytest

from modules.calculator.module import Calculator


@pytest.fixture
def calc(manager):
    return Calculator(manager)


@pytest.mark.parametrize("expr, expected", [
    ("2 + 2", 4),
    ("(3 + 4) * 2", 14),
    ("2 ** 10", 1024),
    ("7 / 2", 3.5),
])
async def test_evaluates_arithmetic(calc, expr, expected):
    res = await calc.calculate(expr)
    assert res["status"] == "success"
    assert res["content"] == expected


@pytest.mark.parametrize("expr", [
    "1 / 0",
    "__import__('os').system('true')",
    "open('/etc/passwd').read()",
    "(1).__class__.__bases__",
    "().__class__.__base__.__subclasses__()",
    "os",
])
async def test_rejects_unsafe_or_invalid(calc, expr):
    assert (await calc.calculate(expr))["status"] == "error"
