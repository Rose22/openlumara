import core
import copy

class Context:
    # special message type (not intended to be added to context) that
    # will cause context.get() to cut off messages before this cutoff point
    SUMMARIZATION_CUTOFF = {"signal": "SUMMARIZATION_CUTOFF"}

    def __init__(self, channel):
        self.channel = channel

        # UI-agnostic chat history system - save/load context windows from save file!
        self.chat = core.chat.Chat(self.channel)

    async def get(self, system_prompt=True, end_prompt=True, prevent_recursion=False):
        """
        builds the full context window using system prompt + message history + end prompt
        to the API, we send this full context.

        to frontend channels, we send only the message history part of the context (context.chat.get()),
        without the system prompt and without the modifications we do to it such as the endprompt.

        context must ALWAYS follow this strict turn order: system->user->assistant->user->assistant->user->...
        """

        if not self.channel.manager.API.connected:
            return None

        # Configuration
        max_messages = int(core.config.get("api").get("max_messages", 200))
        max_tokens = int(core.config.get("api").get("max_context", 8192))
        system_role = "system" if not self.channel.manager.API.supports_developer_role else "developer"
        dev_role = "developer" if self.channel.manager.API.supports_developer_role else "user"

        # 1. Prepare Components
        system_msg = []
        if system_prompt:
            content = await self.channel.manager.get_system_prompt()
            if content:
                system_msg = [{"role": system_role, "content": content}]

        # Get history from the chat (the full, untrimmed version)
        messages = copy.deepcopy(await self.chat.get())

        # we need to support chat summarization without losing the user-facing end of chat history
        # so that we can cut context without actually losing our logs..

        # so, i'm using a special entry in the messages array that serves as a cutoff point
        # from which to actually return the chat history

        # find the last occurence of it and return only the messages from that point onward
        for i in range(len(messages) - 1, -1, -1):
            if messages[i].get("signal", "") == "SUMMARIZATION_CUTOFF":
                messages = [{"role": "user", "content": "Summarize our chat so far"}]+messages[i:]
                break

        # Remove ghost messages from history
        messages = [msg for msg in messages if not msg.get("ghost")]
        
        # If disabled, remove reasoning from all prior messages
        if not core.config.get("model", "keep_reasoning_in_context"):
            messages = [{k: v for k, v in m.items() if k != "reasoning_content"} for m in messages]

        # Apply max_messages limit to history first
        if messages and len(messages) > max_messages:
            messages = messages[-max_messages:]

        # Strip multimodal data from all messages except the last one to save tokens
        if messages:
            for i in range(len(messages) - 1):
                msg = messages[i]
                if msg.get("role") in ("tool", "tool_calls"):
                    # dont mess with toolcalls
                    continue

                content = msg.get("content")
                if isinstance(content, list):
                    # Keep only the parts of the message that are text
                    msg["content"] = [
                        part for part in content
                        if isinstance(part, dict) and part.get("type") == "text"
                    ]
                elif isinstance(content, str):
                    pass
                else:
                    # disallow non-string content
                    continue

        # enforce correct turn order
        if messages:
            enforced_messages = []
            for msg in messages:
                if (
                    enforced_messages and
                    enforced_messages[-1].get("role") == "assistant" and
                    msg.get("role") == "assistant" and
                    # IMPORTANT: Only inject if neither message is a tool call.
                    # Assistant -> Tool -> Assistant is VALID.
                    # Assistant -> Assistant is INVALID.
                    not enforced_messages[-1].get("role") == "tool"
                ):
                    # We inject a "spacer" user message.
                    # Using a single space " " is less intrusive to the LLM
                    # than "[SYSTEM_TICK]" and satisfies the API requirement.
                    enforced_messages.append({"role": "user", "content": " "})

                enforced_messages.append(msg)

            messages = enforced_messages

        end_msg = []
        if end_prompt:
            histend = await self.channel.manager.get_end_prompt(prevent_recursion=prevent_recursion)
            if histend:
                end_msg = [{"role": dev_role, "content": histend}]

        # 2. Build and Trim Context
        # We combine them to check the total token count
        full_context = system_msg + messages + end_msg
        
        # Calculate current token count
        current_tokens = await self.chat.count_tokens(full_context)

        # Leave a small buffer (5%) to avoid hitting exact limit
        token_buffer = max_tokens * 0.05
        effective_max_tokens = max_tokens - token_buffer

        # If we are over the limit, we trim the history (the middle part)
        # We don't trim the system prompt or the end prompt as they are essential.
        while current_tokens > effective_max_tokens and messages:
            messages.pop(0)
            full_context = system_msg + messages + end_msg
            current_tokens = await self.chat.count_tokens(full_context)

        # If we are STILL over the limit even with empty history, it's a single massive message
        if current_tokens > max_tokens and messages:
             await self.channel.announce(
                "Your request exceeds the maximum token limit. Please send a smaller message!",
                "error"
            )

        return full_context

    async def get_size(self):
        message_history = await self.get(system_prompt=False)
        sysprompt = await self.channel.manager.get_system_prompt()
        histend = await self.channel.manager.get_end_prompt()
        
        # Use the chat's count_tokens method for consistency
        sysprompt_size_tokens = await self.chat.count_tokens([{"role": "system", "content": sysprompt}])
        sysprompt_size_words = len(str(sysprompt).split())
        
        message_hist_size_tokens = await self.chat.count_tokens(await self.chat.get())
        message_hist_size_words = len(str(message_history).split())
        
        histend_size_tokens = await self.chat.count_tokens([{"role": "user", "content": histend}]) if histend else 0
        histend_size_words = len(str(histend).split()) if histend else 0

        combined_size_words = message_hist_size_words + sysprompt_size_words + histend_size_words

        # Get total token usage - prefer API-provided usage if available
        if hasattr(self.chat, 'token_usage') and self.chat.token_usage > 0:
            token_usage = self.chat.token_usage
        else:
            token_usage = await self.chat.count_tokens(await self.get(system_prompt=True))

        return {
            "system prompt size": f"{sysprompt_size_tokens} tokens | {sysprompt_size_words} words",
            "message history size": f"{message_hist_size_tokens} tokens | {message_hist_size_words} words",
            "end prompt size": f"{histend_size_tokens} tokens | {histend_size_words} words",
            "total size": f"{token_usage} tokens | {combined_size_words} words",
        }

    async def get_token_usage(self):
        max_tokens = core.config.get("api").get("max_context", 8192)

        # First, check if we have API-provided token usage from the last response
        if hasattr(self.chat, 'token_usage') and self.chat.token_usage > 0:
            return {
                "current": self.chat.token_usage,
                "max": max_tokens
            }

        # Otherwise, calculate token usage locally
        # we use prevent_recursion to tell the system prompt retrieval
        # call in self.get() to not include token usage data

        try:
            prompt_tokens = await self.chat.count_tokens(await self.get(system_prompt=True, prevent_recursion=True))
        except AttributeError as e:
            # when modules don't have a channel assigned yet, this error triggers. we handle it "gracefully".
            return {"current": 0, "max": max_tokens}
        except Exception as e:
            # Return a conservative estimate on error
            return {"current": 0, "max": max_tokens}

        return {
            "current": prompt_tokens,
            "max": max_tokens
        }
