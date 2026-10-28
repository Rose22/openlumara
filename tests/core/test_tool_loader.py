# -- AI GENERATED CODE (Claude) :: (2026-10-25) harness:openlumara status:unreviewed
"""
core/tool_loader.py - tool registration, schema generation, argument preflight.

intent: build OpenAI function-calling schemas from signatures + Google-style
docstrings, and validate/leniently-coerce incoming JSON arguments BEFORE
dispatch so a bad call gets a helpful error instead of a TypeError from
inside the tool body. The explicit bool guard in _coerce_arg documents that
True must never become the integer 1.

registration contract (dev 223f7b1): only @core.module.tool decorated
methods are cataloged - implicit registration of every public method is
gone. Commands stay non-tools even when double-decorated, disabled_tools
are never registered, and a module that registers zero tools while still
holding public callables gets a "did you forget the decorator" warning.
Built tool dicts are cached per (function, tool_name) since schemas are
static.
"""

import pytest

import core


@pytest.fixture
def loader(fake_channel):
    return core.tool_loader.ToolLoader(fake_channel)


# ---- parse_tool_docstring ----------------------------------------------

def test_parse_docstring_none(loader):
    assert loader.parse_tool_docstring(None) == ({}, "")


def test_parse_docstring_plain_description(loader):
    descriptions, desc = loader.parse_tool_docstring("Just a description.\nSecond line.")
    assert descriptions == {}
    assert desc == "Just a description.\nSecond line."


def test_parse_docstring_args_section(loader):
    doc = """Do a thing.

    Args:
        alpha: the alpha value
        beta (int): a beta value with a type hint
            continuation of beta's description.

    Returns:
        nothing useful
    """
    descriptions, desc = loader.parse_tool_docstring(doc)

    assert descriptions == {
        "alpha": "the alpha value",
        "beta": "a beta value with a type hint continuation of beta's description.",
    }
    # the Args/Returns sections must not leak into the description
    assert desc == "Do a thing."


def test_parse_docstring_stops_at_end_sections(loader):
    doc = """Thing.

    Args:
        a: one

    Raises:
        ValueError: nope

    Args:
        b: two
    """
    descriptions, _ = loader.parse_tool_docstring(doc)
    # parsing stops at the first end section: b is NOT picked up
    assert "a" in descriptions and "b" not in descriptions


# ---- _tool_dict_from_func -------------------------------------------------

def test_tool_dict_from_signature_and_docstring(loader):
    def sample(alpha: str, beta: int = 2, gamma: bool = True):
        """Does a thing.

        Args:
            alpha: the alpha value
        """

    tool = loader._tool_dict_from_func(sample, "sample")
    fn = tool["function"]

    assert tool["type"] == "function"
    assert fn["name"] == "sample"
    assert fn["description"] == "Does a thing."
    assert fn["strict"] is False

    params = fn["parameters"]
    assert params["type"] == "object"
    assert params["additionalProperties"] is False
    assert params["required"] == ["alpha"]
    assert params["properties"]["alpha"] == {
        "type": "string", "description": "the alpha value",
    }
    assert params["properties"]["beta"] == {"type": "integer"}
    assert params["properties"]["gamma"] == {"type": "boolean"}


def test_tool_dict_unknown_annotation_falls_back_to_string(loader):
    def weird(value):
        """No annotation."""

    tool = loader._tool_dict_from_func(weird, "weird")
    assert tool["function"]["parameters"]["properties"]["value"] == {"type": "string"}


def test_tool_dict_without_docstring_has_no_description_key(loader):
    def nodoc(value: str): pass

    tool = loader._tool_dict_from_func(nodoc, "nodoc")
    assert "description" not in tool["function"]


# ---- _simple_annotation ----------------------------------------------------

def test_simple_annotation_stringized_and_real(loader):
    assert loader._simple_annotation("int") is int
    assert loader._simple_annotation("bool") is bool
    assert loader._simple_annotation("boolean") is None  # json names are not python names
    assert loader._simple_annotation(str) is str
    assert loader._simple_annotation(float) is None  # not in the type map
    assert loader._simple_annotation({}) is None      # unhashable


# ---- _coerce_arg -------------------------------------------------------------

COERCE = core.tool_loader.ToolLoader._coerce_arg


def test_coerce_bool_is_never_an_int():
    # the explicit guard at the top of _coerce_arg: True != 1
    assert COERCE(True, int) == (True, False)
    assert COERCE(False, int) == (False, False)


def test_coerce_to_int():
    assert COERCE(5, int) == (5, True)
    assert COERCE("5", int) == (5, True)
    assert COERCE("+7", int) == (7, True)
    assert COERCE(" 5 ", int) == (5, True)
    assert COERCE(5.0, int) == (5, True)
    assert COERCE(5.5, int) == (5.5, False)
    assert COERCE("5.5", int) == ("5.5", False)
    assert COERCE("five", int) == ("five", False)


def test_coerce_to_bool():
    assert COERCE(True, bool) == (True, True)
    assert COERCE(1, bool) == (True, True)
    assert COERCE(0, bool) == (False, True)
    assert COERCE("TRUE ", bool) == (True, True)
    assert COERCE("false", bool) == (False, True)
    assert COERCE("yes", bool) == ("yes", False)


def test_coerce_to_str():
    assert COERCE("x", str) == ("x", True)
    assert COERCE(12, str) == ("12", True)
    assert COERCE(1.5, str) == ("1.5", True)
    assert COERCE({}, str) == ({}, False)


def test_coerce_leaves_unknown_combos_untouched():
    assert COERCE([], int) == ([], False)
    assert COERCE({"a": 1}, bool) == ({"a": 1}, False)


# ---- _preflight_args ----------------------------------------------------------

def test_preflight_missing_required_arg_gives_helpful_error(loader):
    def target(alpha: str, beta: int = 1): pass

    clean, err = loader._preflight_args(target, "target", {"beta": 2})
    assert clean is None
    assert "alpha: string (required)" in err


def test_preflight_unknown_arg_rejected(loader):
    def target(alpha: str): pass

    clean, err = loader._preflight_args(target, "target", {"alpha": "x", "nope": 1})
    assert clean is None
    assert "nope" in err


def test_preflight_coerces_leniently(loader):
    def target(alpha: str, beta: int = 1): pass

    clean, err = loader._preflight_args(target, "target", {"alpha": "5", "beta": "7"})
    assert err is None
    assert clean == {"alpha": "5", "beta": 7}


def test_preflight_explicit_none_passes_through(loader):
    # Optional-style params: an explicit null must not be "coerced"
    def target(alpha: str = "x"): pass

    clean, err = loader._preflight_args(target, "target", {"alpha": None})
    assert err is None
    assert clean == {"alpha": None}


def test_preflight_unannotated_and_kwargs_pass_through(loader):
    def target(a: int, *args, **kwargs): pass

    clean, err = loader._preflight_args(
        target, "target", {"a": "3", "args": [1], "kwargs": {"k": "v"}}
    )
    assert err is None
    assert clean["a"] == 3
    assert clean["args"] == [1] and clean["kwargs"] == {"k": "v"}


def test_preflight_type_mismatch_lists_all_problems(loader):
    def target(a: int, b: bool): pass

    clean, err = loader._preflight_args(target, "target", {"a": "x", "b": "maybe"})
    assert clean is None
    assert "'a' expects integer" in err
    assert "'b' expects boolean" in err


# ---- @core.module.tool registration (dev 223f7b1) -------------------------
#
# registration is decorator-driven now: __module__ gives each probe class a
# unique module name, and the command registry is sandboxed per test.

def _probe_namespace(monkeypatch):
    monkeypatch.setattr(core.module, "_command_registry", {})


def test_register_module_only_picks_up_decorated_methods(loader, fake_manager, monkeypatch):
    _probe_namespace(monkeypatch)

    class DecoProbe(core.module.Module):
        __module__ = "modules.deco_probe"

        @core.module.tool
        async def ping(self, msg: str):
            """Ping!

            Args:
                msg: what to echo
            """

        async def not_a_tool(self):
            """public but undecorated -> must NOT become a tool"""

        async def on_ready(self):
            """lifecycle hook, never a tool"""

        async def _private(self): pass

    inst = DecoProbe(fake_manager)
    loader.register_module(inst)

    assert list(loader.catalog) == ["deco_probe_ping"]
    entry = loader.catalog["deco_probe_ping"]
    assert entry["module"] == "deco_probe"
    assert entry["method"] == "ping"
    assert entry["tool"]["function"]["name"] == "deco_probe_ping"
    assert entry["description"] == "Ping!"


def test_register_module_skips_disabled_tools(loader, fake_manager, monkeypatch):
    _probe_namespace(monkeypatch)

    class DisabledProbe(core.module.Module):
        __module__ = "modules.disabled_probe"

        @core.module.tool
        async def off(self): pass

        @core.module.tool
        async def on(self): pass

    inst = DisabledProbe(fake_manager)
    inst.disabled_tools = ["off"]
    loader.register_module(inst)

    assert list(loader.catalog) == ["disabled_probe_on"]


def test_register_module_never_registers_commands(loader, fake_manager, monkeypatch):
    _probe_namespace(monkeypatch)

    class CmdProbe(core.module.Module):
        __module__ = "modules.cmd_tool_probe"

        @core.module.tool
        @core.module.command("dblprobe")
        async def dbl(self, args): pass

    inst = CmdProbe(fake_manager)
    loader.register_module(inst)

    # double-decorated is still a command, never a tool
    assert loader.catalog == {}


# ---- _warn_missed_tools -----------------------------------------------------

def test_warn_missed_tools_flags_unmigrated_module(loader, fake_channel, fake_manager, monkeypatch):
    _probe_namespace(monkeypatch)

    class LegacyProbe(core.module.Module):
        __module__ = "modules.legacy_probe"

        async def would_be_tool(self, x: str): pass

    loader.register_module(LegacyProbe(fake_manager))

    warnings = [m for cat, m in fake_channel.logs if cat == "warning"]
    assert len(warnings) == 1
    assert "registered 0 tools" in warnings[0]
    assert "would_be_tool" in warnings[0]


def test_no_warning_when_a_decorated_tool_exists(loader, fake_channel, fake_manager, monkeypatch):
    _probe_namespace(monkeypatch)

    class MigratedProbe(core.module.Module):
        __module__ = "modules.migrated_probe"

        @core.module.tool
        async def fine(self): pass

        async def leftover_public(self): pass

    loader.register_module(MigratedProbe(fake_manager))

    assert not [m for cat, m in fake_channel.logs if cat == "warning"]


def test_no_warning_for_lifecycle_only_module(loader, fake_channel, fake_manager, monkeypatch):
    _probe_namespace(monkeypatch)

    class QuietProbe(core.module.Module):
        __module__ = "modules.quiet_probe"

        async def on_ready(self): pass

        async def _internal(self): pass

    loader.register_module(QuietProbe(fake_manager))

    assert not [m for cat, m in fake_channel.logs if cat == "warning"]


# ---- _tool_dict_from_func caching (dev 02065ef) ------------------------------

def test_tool_dict_is_cached_per_function_and_name(loader):
    def cached_sample(value: str):
        """doc."""

    first = loader._tool_dict_from_func(cached_sample, "cached_sample")
    second = loader._tool_dict_from_func(cached_sample, "cached_sample")
    assert first is second  # schema is static -> reused, not rebuilt

    renamed = loader._tool_dict_from_func(cached_sample, "other_name")
    assert renamed is not first
    assert renamed["function"]["name"] == "other_name"


def test_tool_dict_cache_keys_on_the_underlying_function(loader):
    # bound methods are new objects on every getattr, so the cache must key
    # on __func__: two instances of the same class share one schema dict
    class Holder:
        def meth(self, v: str):
            """doc."""

    a = loader._tool_dict_from_func(Holder().meth, "m")
    b = loader._tool_dict_from_func(Holder().meth, "m")
    assert a is b
