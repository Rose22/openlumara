import core
import copy

class Context:
    def __init__(self, channel):
        self.channel = channel

        # UI-agnostic chat history system - save/load context windows from save file!
        self.chat = core.chat.Chat(self.channel)

    async def get(self, system_prompt=True, end_prompt=True):
        """
        builds the full context window using system prompt + message history + end prompt
        to the API, we send this full context.

        to frontend channels, we send only the message history part of the context (context.chat.get()),
        without the system prompt and without the modifications we do to it such as the endprompt.

        context must ALWAYS follow this strict turn order: system->user->assistant->user->assistant->user->...
        """

        if not self.channel.manager.API.connected:
            return None

        # context = system prompt (top) + message history (middle) + endprompt (bottom)
        context = []

        # always insert system prompt at start of context
        if system_prompt:
            context = [{"role": "system", "content": await self.channel.manager.get_system_prompt()}]

        # insert message history
        messages_orig = await self.chat.get()
        if messages_orig:
            # deepcopy so we dont end up modifying the original messages array
            messages = copy.deepcopy(messages_orig)
            context.extend(messages)

        """
        insert endprompt

        the endprompt is information provided by modules that should be at the very end so that context doesnt have to get reprocessed every time,
        since context reprocessing happens from the point of change onward!

        like if you change something in context, it'll reprocess everything after the part where you made the change.

        so the endprompt is useful for info that changes constantly,
        such as the current time and date.
        """
        if end_prompt:
            histend = await self.channel.manager.get_end_prompt()
            if histend:
                # we merge the end prompt with the last message, to stay compliant with API message turn rules

                # or, if we're in the very first message of a chat, we put it in the system prompt instead, just at the beginning, so that it has the information right at the start
                if len(context) == 1:
                    context[0]["content"] += f"\n\n{histend}"
                else:
                    # otherwise we search for the last user message and merge the endprompt into it
                    for i in range(len(context) - 1, -1, -1):
                        # ^ this is for loop that loops backwards through the array!
                        # saves a ton of time

                        if context[i].get("role") == "user":
                            # found it, use it immediately
                            context[i]["content"] += f"\n\n[SYSTEM INFO]:\n{histend}"
                            break

                    # since we're working with a deepcopy, this won't be visible to any frontend channels!

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

    async def get_token_usage(self):
        max_tokens = core.config.get("api").get("max_context", 8192)

        try:
            prompt_tokens = await self.chat.count_tokens(await self.get(system_prompt=True))
        except AttributeError as e:
            # when modules don't have a channel assigned yet, this error triggers. we handle it "gracefully".
            return {"current": 0, "max": max_tokens}
        except Exception as e:
            core.log_error("error while fetching token usage", e)

        return {
            "current": prompt_tokens,
            "max": max_tokens
        }
