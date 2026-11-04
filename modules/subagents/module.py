import core

class Subagents(core.module.Module):
    """lets your AI spin up subagents (chat sessions with a seperate context) to perform a request"""

    async def _process_substream(self, stream, ctx):
        async for token in stream:
            yield token

            token_type = token.get("type")
            if token_type == "tool_calls":
                toolcall_request = await self.channel.tc_manager._build_recursive_request(token, [], [])
                async for sub_token in self.channel.tc_manager.process(toolcall_request, context=ctx):
                    yield sub_token

    @core.module.tool
    async def spawn(self, prompt: str):
        # hold a temporary context for this call
        ctx = []
        try:
            response = await self.channel.on_stream(
                self._process_substream(
                    self.manager.API.send_stream([
                        {
                            "role": "system",
                            "content": await self.channel.context.chat.get_system_prompt()
                        },
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ]),
                    ctx
                )
            )
        except Exception as e:
            return self.result(core.detail_error(e), success=False)

        return self.result(ctx[-1] if len(ctx) else None)
