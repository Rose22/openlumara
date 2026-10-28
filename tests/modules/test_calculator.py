# -- AI GENERATED CODE (Claude) :: (2026-10-25) harness:openlumara status:unreviewed
"""
modules/calculator - thin simpleeval wrapper.

simpleeval is an auto-installed runtime dependency; the whole file is
skipped when it is not present in the environment under test.
"""

import pytest

pytest.importorskip("simpleeval", reason="calculator's auto-installed dependency")

from harness import apply_config  # noqa: E402
from modules.calculator.module import Calculator  # noqa: E402


@pytest.fixture
def calc(fake_manager):
    apply_config(
        core={"cmd_prefix": "/"},
        modules={"disabled_prompts": []},
    )
    return Calculator(fake_manager)


async def test_calculator_evaluates_expression(calc):
    res = await calc.calculate("2+2")
    assert res["status"] == "success"
    assert res["content"] == 4


async def test_calculator_error_envelope(calc):
    res = await calc.calculate("1/0")
    assert res["status"] == "error"


async def test_calculator_rejects_names_outside_grammar(calc):
    # simpleeval's sandbox must not expose python builtins/names
    res = await calc.calculate("__import__('os')")
    assert res["status"] == "error"