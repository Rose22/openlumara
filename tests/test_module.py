# AI Written: Claude Opus 5.5, reviewed by Claude Fable 5.2
import core
import pytest


class Base(core.module.Module):
    __module__ = "modules.base"

    @core.module.tool
    async def inherited(self):
        pass


class Demo(Base):
    __module__ = "modules.demo"
    settings = {
        "greeting": {"default": "hello"},
        "limit": {"default": 3},
    }

    @core.module.tool
    async def search(self, query: str, limit: int = 5, exact: bool = False, tags: list = None):
        """Searches things.

        Args:
            query (str): what to look for
                across multiple lines
            limit (int): max results

        Returns:
            a list
        """

    async def helper(self):
        """not a tool"""


@pytest.fixture
def demo(manager):
    return Demo(manager)


def test_only_tools_defined_on_the_class_register(demo, channel):
    channel.tool_loader.register_module(demo)
    assert set(channel.tool_loader.catalog) == {"demo_search"}


def test_schema_from_signature_and_docstring(demo, channel):
    channel.tool_loader.register_module(demo)
    func = channel.tool_loader.catalog["demo_search"]["tool"]["function"]
    params = func["parameters"]

    assert params["required"] == ["query"]
    assert {k: v["type"] for k, v in params["properties"].items()} == {
        "query": "string", "limit": "integer", "exact": "boolean", "tags": "array",
    }
    assert params["properties"]["query"]["description"] == "what to look for across multiple lines"
    assert "description" not in params["properties"]["exact"]
    # sections are stripped from the tool description
    assert func["description"] == "Searches things."


def test_command_registration(monkeypatch):
    monkeypatch.setattr(core.module, "_command_registry", {})

    class Cmds(core.module.Module):
        __module__ = "modules.cmds"

        @core.module.command("Greet")
        async def greet(self, args):
            """says hi
            more text"""

        @core.module.command("quiet", help="shh", send_to_ai=False)
        async def quiet(self, args):
            pass

    assert [cls for cls, _ in core.module._command_registry["greet"]] == [Cmds]
    assert core.module.get_command_description("greet") == "says hi"
    assert core.module.get_command_description("quiet") == "shh"
    assert core.module.command_is_temporary("quiet")
    assert not core.module.command_is_temporary("greet")
    assert not core.module.command_is_temporary("missing")


def test_command_is_never_a_tool(monkeypatch, manager, channel):
    monkeypatch.setattr(core.module, "_command_registry", {})

    class Both(core.module.Module):
        __module__ = "modules.both"

        @core.module.tool
        @core.module.command("both")
        async def both(self, args):
            pass

    channel.tool_loader.register_module(Both(manager))
    assert channel.tool_loader.catalog == {}


def test_config_falls_back_to_settings_defaults(demo):
    assert demo.config.get("greeting") == "hello"
    assert demo.config.get("greeting", default="bye") == "bye"
    assert demo.config.get("missing") is None
    assert demo.config.get() is None


def test_config_reads_saved_values(demo, set_config):
    set_config(modules={"settings": {"demo": {"limit": 10, "nested": {"a": 1}}}})
    assert demo.config.get("limit") == 10
    assert demo.config.get("nested", "a") == 1
    # nested misses use the plain default, not the schema one
    assert demo.config.get("nested", "b", 0) == 0


def test_config_set_ignores_unknown_keys(demo, set_config):
    set_config(modules={"settings": {"demo": {"limit": 10}}})
    demo.config.set("limit", 20)
    demo.config.set("unknown", 1)
    assert demo.config.get("limit") == 20
    assert "unknown" not in core.config.config["modules"]["settings"]["demo"]


def test_result_envelope(demo):
    assert demo.result("ok") == {"status": "success", "content": "ok"}
    assert demo.result({"x": 1}, success=False) == {"status": "error", "content": {"x": 1}}
