# AI Written: Claude Opus 5.5, reviewed by Claude Fable 5.2
import core
import pytest


class Alpha(core.module.Module):
    __module__ = "modules.alpha"

    @core.module.tool
    async def add(self, a: int, b: int = 1):
        """Adds numbers.

        Args:
        a (int): first number
        b (int): second number
        """
        return self.result(a + b)

    @core.module.tool
    async def shout(self, text: str, loud: bool = True):
        return self.result(text.upper() if loud else text)


class Beta(core.module.Module):
    __module__ = "modules.beta"

    @core.module.tool
    async def ping(self):
        return "pong"


def make_loader(channel, *module_classes):
    loader = core.tool_loader.ToolLoader(channel)
    for cls in module_classes:
        module = cls(channel.manager)
        channel.manager.modules[module.name] = module
        loader.register_module(module)
    loader.register_meta_tools()
    loader.refresh()
    return loader


@pytest.fixture
def loader(channel, set_config):
    set_config(model={"dynamic_tool_loading": True})
    return make_loader(channel, Alpha, Beta)


def test_dynamic_loading_exposes_only_meta_tools(loader):
    assert loader.active_names == ["tools_load", "tools_call"]


def test_preloaded_modules_are_active(channel, set_config):
    set_config(model={"dynamic_tool_loading": True, "preloaded_modules": ["Alpha"]})
    loader = make_loader(channel, Alpha, Beta)
    assert loader.active_names == ["tools_load", "tools_call", "alpha_add", "alpha_shout"]


def test_without_dynamic_loading_every_tool_is_active(channel):
    loader = make_loader(channel, Alpha, Beta)
    assert loader.active_names == ["alpha_add", "alpha_shout", "beta_ping"]


def test_disabled_tool_drops_out_on_refresh(channel):
    loader = make_loader(channel, Alpha, Beta)
    channel.manager.modules["alpha"].disabled_tools.append("shout")
    loader.refresh()
    assert "alpha_shout" not in loader.active_names


async def test_tools_load_returns_schemas(loader):
    assert (await loader.tools_load("beta"))["tools"][0]["name"] == "beta_ping"
    result = await loader.tools_load(["ALPHA"])
    assert result["status"] == "success"
    assert [t["name"] for t in result["tools"]] == ["alpha_add", "alpha_shout"]
    assert result["tools"][0]["parameters"]["required"] == ["a"]


async def test_tools_load_reports_unknown_modules(loader):
    assert (await loader.tools_load(["nope"]))["status"] == "error"
    partial = await loader.tools_load(["beta", "nope"])
    assert partial["status"] == "success"
    assert partial["not_found"] == ["nope"]


async def test_tools_load_skips_disabled_tools(loader, channel):
    channel.manager.modules["alpha"].disabled_tools.append("shout")
    result = await loader.tools_load(["alpha"])
    assert [t["name"] for t in result["tools"]] == ["alpha_add"]
    assert result["disabled"] == ["alpha_shout"]


@pytest.mark.parametrize("name, params, expected", [
    ("alpha_add", '{"a": 2, "b": 3}', 5),
    ("alpha_add", {"a": 2}, 3),
    ("alpha_add", '{"a": "4"}', 5),  # numeric strings are coerced
    ("alpha_shout", '{"text": "hi", "loud": "false"}', "hi"),
])
async def test_tools_call_runs_the_tool(loader, name, params, expected):
    assert await loader.tools_call(name, params) == {"status": "success", "content": expected}


@pytest.mark.parametrize("name, params", [
    ("alpha_add", "{}"),                # missing required arg
    ("alpha_add", '{"a": 1, "c": 2}'),  # unknown arg
    ("alpha_add", '{"a": "one"}'),      # wrong type
    ("alpha_add", "[1, 2]"),            # not an object
    ("alpha_missing", "{}"),
    ("tools_load", "{}"),
])
async def test_tools_call_rejects_bad_calls(loader, name, params):
    assert (await loader.tools_call(name, params))["status"] == "error"


async def test_tools_call_refuses_disabled_tools(loader, channel):
    channel.manager.modules["alpha"].disabled_tools.append("add")
    result = await loader.tools_call("alpha_add", '{"a": 1}')
    assert result["status"] == "error"
    assert "disabled" in result["content"]


def test_module_without_decorated_tools_warns(channel):
    class Legacy(core.module.Module):
        __module__ = "modules.legacy"

        async def do_thing(self):
            pass

    logs = []
    channel.log = lambda category, message: logs.append((category, message))
    channel.tool_loader.register_module(Legacy(channel.manager))
    assert logs and logs[0][0] == "warning" and "do_thing" in logs[0][1]
