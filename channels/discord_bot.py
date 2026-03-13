import core
import discord
import asyncio
import datetime

class Client(discord.Client):
    def __init__(self, channel, **kwargs):
        super(Client, self).__init__(**kwargs)
        self.ai_channel = channel

    async def _stream_to_discord(self, token_stream, discord_channel):
        """streams a message to discord in steps"""
        message_obj = await discord_channel.send("...")

        message_content = []

        next_edit_time = datetime.datetime.now()
        message_content_full = []
        max_tokens_per_message = 400
        shown_reasoning_text = False
        async with message_obj.channel.typing():
            async for token in token_stream:
                # if tokens exceed 200, add a new message to target for the edits
                if len(message_content) >= max_tokens_per_message:
                    message_content = []
                    message_obj = await discord_channel.send("...")

                if token.get("type") == "reasoning":
                    # reasoning would be very hard to show on discord lol
                    if not shown_reasoning_text:
                        await message_obj.edit(content="thinking..")
                        shown_reasoning_text = True
                    continue

                word = token.get("content")
                message_content.append(word)
                message_content_full.append(word)

                # edit message every few seconds or if token limit reached
                if datetime.datetime.now() >= next_edit_time or len(message_content) >= max_tokens_per_message:
                    await message_obj.edit(content="".join(message_content))
                    next_edit_time = datetime.datetime.now() + datetime.timedelta(seconds=1)

        if message_content:
            await message_obj.edit(content="".join(message_content))
            return "".join(message_content)
        else:
            return "..come again?"

    async def on_ready(self):
        core.log("discord", "logged in.")

    async def on_message(self, message):
        if message.author == self.user:
            return

        self._channel = message.channel

        if message.content:
            # only reply if mentioned
            mentioned = False
            for member in message.mentions:
                if member.id == self.user.id:
                    mentioned = True

            if mentioned:
                core.log("discord", f"<{message.author.name}> {message.clean_content}")

                async with message.channel.typing():
                    try:
                        content = message.content.strip()
                        # remove mentions from message before sending
                        for mention in message.raw_mentions:
                           content = content.replace(str(mention), "") 
                           content = content.replace("<@>", "")

                        response_obj = self.ai_channel.send_stream({"role": "user", "content": content})
                    except Exception as e:
                        return await message.channel.send(f"error while sending request to AI: {e}")

                try:
                    response_content = await self._stream_to_discord(response_obj, message.channel)
                    core.log("discord", f"<{message.guild.me.name}> {response_content}")
                except Exception as e:
                    return await message.channel.send(f"error while receiving response from AI: {e} | {e.__traceback__.tb_frame.f_code.co_filename}, {e.__traceback__.tb_frame.f_code.co_name}, ln:{e.__traceback__.tb_lineno}")

class Discord(core.channel.Channel):
    def __init__(self, manager):
        super().__init__(manager)

        intents = discord.Intents.default()
        intents.message_content = True
        self._client = Client(self, intents=intents)

    async def _announce(self, msg: str, type: str = None):
        if not msg:
            return None

        for guild in self._client.guilds:
            for channel in guild.channels:
                if isinstance(channel, discord.TextChannel) and channel.permissions_for(guild.me).view_channel:
                    await channel.send(msg)

    async def run(self):
        token = core.config.config.get("channels").get("settings").get("discord").get("token")

        if not token:
            core.log("error", "discord token not set! set it in config.yaml as discord_token")
            return False

        core.log("discord", "logging in..")

        try:
            await self._client.start(token)
        except Exception as e:
            core.log("error", f"error connecting to discord: {e}")
