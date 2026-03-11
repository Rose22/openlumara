import core

class Context:
    def __init__(self, channel):
        self.channel = channel

        # UI-agnostic chat history system - save/load context windows from save file!
        self.chat = core.chat.Chat(self.channel)

    async def get(self, system_prompt=True, end_prompt=True):
        """builds the full context window using system prompt + message history + end prompt"""

        # context = system prompt + message history
        context = []

        # always insert system prompt at start of context
        if system_prompt:
            context = context+[{"role": "system", "content": await self.channel.manager.get_system_prompt()}]

        # insert message history
        context = context+(await self.chat.get())

        if end_prompt:
            histend = await self.channel.manager.get_end_prompt()
            if histend:
                # for some reason, it won't accept a 2nd system prompt. so we add it as user
                # maybe theres a better way to do this..
                context = context+[{"role": "user", "content": histend}]

        return context

    async def get_size(self):
        message_history = await self.get(system_prompt=False)
        sysprompt = await self.channel.manager.get_system_prompt()
        histend = await self.channel.manager.get_end_prompt()
        sysprompt_size_tokens = await self.chat.count_tokens([{"role": "system", "content": sysprompt}])
        sysprompt_size_words = len(str(sysprompt).split())
        message_hist_size_tokens = await self.chat.count_tokens(await self.chat.get())
        message_hist_size_words = len(str(message_history).split())
        histend_size_tokens = await self.chat.count_tokens([{"role": "user", "content": histend}])
        histend_size_words = len(str(histend).split())

        combined_size_words = message_hist_size_words+sysprompt_size_words+histend_size_words

        token_usage = await self.chat.count_tokens(await self.get(system_prompt=True))

        return {
            "system prompt size": f"{sysprompt_size_tokens} tokens | {sysprompt_size_words} words",
            "message history size": f"{message_hist_size_tokens} tokens | {message_hist_size_words} words",
            "end prompt size": f"{histend_size_tokens} tokens | {histend_size_words} words",
            "total size": f"{token_usage} tokens | {combined_size_words} words",
        }
