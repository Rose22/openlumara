# AI Written: Claude Opus 5.5, reviewed by Claude Fable 5.2
import core
import pytest


async def cmd(channel, text, authorized=True):
    return await channel.commands.process_input(text, authorized=authorized)


async def history(channel):
    return list(await channel.context.chat.messages.get())


@pytest.mark.parametrize("text", ["hello", " ping", "/unbalanced \"quote"])
async def test_non_commands_fall_through(channel, text):
    assert await cmd(channel, text) is False
    assert await history(channel) == []


async def test_custom_prefix(channel, set_config):
    set_config(core={"cmd_prefix": "!"})
    assert await cmd(channel, "/ping") is False
    assert await cmd(channel, "!ping") == "pong!"


async def test_command_and_reply_are_recorded(channel):
    await cmd(channel, "/ping")
    user, reply = await history(channel)
    assert user["content"] == "/ping"
    assert reply["content"] == "pong!"
    assert user["_metadata"]["is_cmd"] and reply["_metadata"]["is_cmd"]


@pytest.mark.parametrize("command, ghost", [("/help", True), ("/ping", False)])
async def test_ghost_commands_are_hidden_from_the_ai(channel, command, ghost):
    await cmd(channel, command)
    assert all(m["_metadata"].get("ghost", False) == ghost for m in await history(channel))


async def test_admin_commands_need_authorization(channel):
    with pytest.raises(core.exceptions.UnauthorizedException):
        await cmd(channel, "/ping", authorized=False)
    assert await cmd(channel, "/clear", authorized=False)


async def test_unknown_command(channel):
    assert "no such command" in await cmd(channel, "/doesnotexist")


async def test_quoted_arguments(channel):
    await cmd(channel, '/chat rename "my  chat"')
    assert channel.context.chat.get("title") == "my  chat"


async def test_module_commands_dispatch(channel, monkeypatch):
    monkeypatch.setattr(core.module, "_command_registry", {})

    class Greeter(core.module.Module):
        __module__ = "modules.greeter"

        @core.module.command("greet")
        async def greet(self, args):
            return f"hi {' '.join(args)}"

    channel.manager.modules["greeter"] = Greeter(channel.manager)
    assert await cmd(channel, "/GREET bob 'the builder'") == "hi bob the builder"


async def test_clear(channel):
    await channel.context.chat.messages.add({"role": "user", "content": "hi"})
    chat_id = channel.context.chat.get("id")
    await cmd(channel, "/clear")
    assert "hi" not in [m["content"] for m in await history(channel)]
    assert channel.context.chat.get("id") == chat_id


async def test_new(channel):
    await channel.context.chat.messages.add({"role": "user", "content": "hi"})
    old_id = channel.context.chat.get("id")
    await cmd(channel, "/new")
    assert channel.context.chat.get("id") != old_id
    assert len(channel.context.chat.get_all()) == 2


async def test_config_get(channel):
    assert await cmd(channel, "/config core tool_timeout") == str(core.config.get("core", "tool_timeout"))
    assert "does not exist" in await cmd(channel, "/config core nope")


@pytest.mark.parametrize("raw, value", [
    ("true", True), ("ON", True), ("off", False),
    ("42", 42), ("-3", -3), ("1.5", 1.5),
    ("hello world", "hello world"),
])
async def test_config_set_converts_types(channel, isolated, raw, value):
    await cmd(channel, f"/config core tool_timeout {raw}")
    saved = core.storage.StorageDict("config", "yaml", path=str(isolated.parent))
    assert saved["core"]["tool_timeout"] == value

