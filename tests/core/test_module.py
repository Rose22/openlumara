# -- AI GENERATED CODE (Claude) :: (2026-10-25) harness:openlumara status:unreviewed
"""
core/module.py - command registration, empty-coroutine detection, results.

intent: @command registers handlers per Module subclass with lowercased names
and docstring-derived help; send_to_ai=True (the default) means the command
stays visible to the AI, send_to_ai=False makes it "temporary"/ghost.
is_empty_coroutine lets the framework skip spawning background tasks for
modules that did not actually implement on_background.
"""

import pytest

import core


# ---- command decorator + registry ---------------------------------------

@pytest.fixture
def clean_registry(monkeypatch):
    reg = {}
    monkeypatch.setattr(core.module, "_command_registry", reg)
    return reg


def test_command_registration_and_help(clean_registry):
    class Demo(core.module.Module):
        __module__ = "modules.cmd_probe"

        @core.module.command("MixedCase ", help="does things")
        async def mixed(self, args): pass

        @core.module.command("nodocmd")
        async def nodoc(self, args):
            """first line help
            second line
            """

    # names are lowercased and stripped
    assert "mixedcase" in clean_registry
    assert "nodocmd" in clean_registry
    # explicit help wins, otherwise first docstring line
    assert core.module.get_command_description("mixedcase") == "does things"
    assert core.module.get_command_description("nodocmd") == "first line help"


def test_command_temporariness(clean_registry):
    class Demo(core.module.Module):
        __module__ = "modules.cmd_probe2"

        @core.module.command("persistentcmd")
        async def p(self, args): pass

        @core.module.command("ghostcmd", send_to_ai=False)
        async def g(self, args): pass

    assert core.module.command_is_temporary("persistentcmd") is False
    assert core.module.command_is_temporary("ghostcmd") is True


def test_command_is_temporary_if_any_registration_is(clean_registry):
    # two modules can register the same command name; one temporary wins
    class A(core.module.Module):
        __module__ = "modules.cmd_a"

        @core.module.command("sharedcmd")
        async def s(self, args): pass

    class B(core.module.Module):
        __module__ = "modules.cmd_b"

        @core.module.command("sharedcmd", send_to_ai=False)
        async def s2(self, args): pass

    assert core.module.command_is_temporary("sharedcmd") is True


def test_temporariness_helpers_on_unknown_command(clean_registry):
    assert core.module.command_is_temporary("not_registered") is False
    assert core.module.get_command_description("not_registered") is None


# ---- is_empty_coroutine ------------------------------------------------------

async def _empty_pass(): pass
async def _empty_doc(): """only a docstring"""
async def _empty_ellipsis(): ...
async def _empty_doc_and_pass():
    """docs"""
    pass
async def _real_body():
    return 1


@pytest.mark.parametrize("func", [_empty_pass, _empty_doc, _empty_ellipsis, _empty_doc_and_pass])
def test_empty_coroutines_detected(func):
    assert core.module.is_empty_coroutine(func) is True


def test_non_empty_coroutine_detected():
    assert core.module.is_empty_coroutine(_real_body) is False


def test_sourceless_callable_is_conservatively_not_empty():
    # intent (fallback comment): when source can't be fetched, assume NOT
    # empty so a real background task is never silently skipped
    assert core.module.is_empty_coroutine(print) is False


# ---- Module.result -----------------------------------------------------------

def test_result_success_envelope(fake_manager):
    class Demo(core.module.Module):
        __module__ = "modules.result_probe"

    result = Demo(fake_manager).result({"data": 1})
    assert result == {"status": "success", "content": {"data": 1}}


def test_result_error_envelope(fake_manager):
    class Demo(core.module.Module):
        __module__ = "modules.result_probe2"

    result = Demo(fake_manager).result("it broke", success=False)
    assert result == {"status": "error", "content": "it broke"}


# ---- ModuleConfig.get ----------------------------------------------------------

@pytest.fixture
def modconfig():
    structure = {
        "simple": {"default": "schema-default", "description": "d"},
        "flag": {"default": False},
    }
    cm = core.config.ConfigManager(core.config.config, base_path=["modules", "settings", "mcprobe"])
    return core.module.ModuleConfig(None, structure, cm)


def test_moduleconfig_no_args_returns_none(modconfig):
    assert modconfig.get() is None


def test_moduleconfig_single_key_falls_back_to_schema_default(modconfig):
    assert modconfig.get("simple") == "schema-default"
    assert modconfig.get("flag") is False


def test_moduleconfig_explicit_default_beats_schema_default(modconfig):
    assert modconfig.get("simple", default="mine") == "mine"


def test_moduleconfig_nested_miss_returns_plain_default(modconfig):
    # schema-default fallback is single-key only (intent: nested lookups are
    # explicit; a miss there means "not configured")
    assert modconfig.get("nope", "inner") is None


def test_moduleconfig_trailing_nonstring_is_treated_as_default(modconfig):
    assert modconfig.get("nope", 42) == 42


def test_moduleconfig_reads_values_present_in_config(modconfig):
    modconfig.config["simple"] = "from-config"
    assert modconfig.get("simple") == "from-config"


# ---- tool decorator (dev 223f7b1) ------------------------------------------

def test_tool_decorator_marks_and_passes_through():
    def candidate(): pass

    returned = core.module.tool(candidate)

    # same function object, just flagged - the loader keys on _is_tool
    assert returned is candidate
    assert candidate._is_tool is True


def test_tool_marked_methods_are_still_plain_callables():
    class Demo(core.module.Module):
        __module__ = "modules.tool_flag_probe"

        @core.module.tool
        async def ping(self, msg: str):
            return msg

    # registration lives in the loader; the decorator itself must not
    # wrap or alter the method
    assert Demo.ping._is_tool is True
    assert not hasattr(Demo.ping, "_is_command")
