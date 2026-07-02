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

    async def get(self, system_prompt=True, end_prompt=True, history=True, prevent_recursion=False):
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
            try:
                content = await self.channel.manager.get_system_prompt()
            except Exception as e:
                self.channel.log_error("Error while getting system prompt", e)

            if content:
                system_msg = [{"role": system_role, "content": content}]

        messages = []
        if history:
            # Get history from the chat (the full, untrimmed version)
            messages = copy.deepcopy(await self.chat.get())

            # we need to support chat summarization without losing the user-facing end of chat history
            # so that we can cut context without actually losing our logs..

            # so, i'm using a special entry in the messages array that serves as a cutoff point
            # from which to actually return the chat history

            # find the last occurence of it and return only the messages from that point onward
            for i in range(len(messages) - 1, -1, -1):
                if messages[i].get("signal") == "SUMMARIZATION_CUTOFF":
                    messages = [{"role": "user", "content": "Summarize our chat so far."}] + messages[i + 1:]
                    break

            # Remove ghost messages and signal messages from history
            messages = [msg for msg in messages if not msg.get("ghost") and not msg.get("signal")]

            # Strip invalid assistant messages (those without content or tool calls)
            messages = [
                msg for msg in messages
                if not (msg.get("role") == "assistant" and not msg.get("content") and not msg.get("tool_calls"))
            ]

            # If disabled, remove reasoning from all prior messages
            if not core.config.get("model", "keep_reasoning_in_context"):
                messages = [{k: v for k, v in m.items() if k != "reasoning_content"} for m in messages]

            if core.config.get("model", "only_preserve_reasoning_for_current_agentic_loop"):
                # TODO: i really need to make a more user friendly UI for core settings, that matches the UX of module/channel settings...
                # that name is ridiculous

                if core.config.get("model", "only_preserve_reasoning_for_current_agentic_loop"):
                    # strip reasoning from tool calls prior to the current agentic loop
                    loop_idx = self.channel.agentic_loop_start
                    messages[:loop_idx] = [
                        {k: v for k, v in m.items() if k != "reasoning_content"}
                        if "tool_calls" in m else m
                        for m in messages[:loop_idx]
                    ]

            # Apply max_messages limit to history first
            if len(messages) > max_messages:
                messages = messages[-max_messages:]

            # Strip multimodal data from all messages except the last one to save tokens
            if messages:
                for i in range(len(messages) - 1):
                    msg = messages[i]
                    if msg.get("role") in ("tool", "tool_calls"):
                        # Don't mess with tool calls
                        continue

                    content = msg.get("content")
                    if isinstance(content, list):
                        # Keep only the text parts of the message
                        text_parts = [
                            part for part in content
                            if isinstance(part, dict) and part.get("type") == "text"
                        ]
                        # If stripping leaves nothing, convert to a placeholder string
                        # to avoid sending an empty content list (which some APIs reject)
                        if text_parts:
                            msg["content"] = text_parts
                        else:
                            msg["content"] = "[multimedia content]"
                    elif isinstance(content, str):
                        pass
                    # Non-string, non-list content is left as-is (don't silently drop messages)

            # enforce correct turn order
            # system -> user -> assistant -> user -> assistant -> ...
            # assistant -> tool -> assistant is VALID (tool use flow)
            # assistant -> assistant is INVALID (needs spacer)
            if messages:
                enforced_messages = []
                for msg in messages:
                    if enforced_messages:
                        last_role = enforced_messages[-1].get("role")
                        current_role = msg.get("role")

                        # Two consecutive assistant messages need a spacer user message,
                        # BUT only if there's no tool message in between.
                        # assistant -> tool -> assistant is valid (tool use flow).
                        if last_role == "assistant" and current_role == "assistant":
                            enforced_messages.append({"role": "user", "content": " "})
                        # Two consecutive user messages also violate turn order
                        elif last_role == "user" and current_role == "user":
                            enforced_messages.append({"role": "assistant", "content": " "})

                    enforced_messages.append(msg)

                messages = enforced_messages

        end_msg = []
        if end_prompt:
            histend = await self.channel.manager.get_end_prompt(prevent_recursion=prevent_recursion)
            if histend:
                end_msg = [{"role": dev_role, "content": histend}]

        # now we inject anything modules want to inject into the user messages
        for message in messages:
            if message.get("injection"):
                if message.get("role") == "user":
                    content = message.get("content")
                    if content and isinstance(content, str):
                        message["content"] += f"\n\n[SYSTEM MESSAGES]\n{message['injection']}"

                # remove the field from all messages so that it's clean for the API
                del message["injection"]

        # 2. Build and Trim Context
        # We combine them to check the total token count
        full_context = system_msg + messages + end_msg
        
        # Calculate current token count
        current_tokens = await self.chat.count_tokens(full_context)

        # Leave a small buffer (5%) to avoid hitting exact limit
        effective_max_tokens = int(max_tokens * 0.95)

        # If we are over the limit, trim the history (the middle part).
        # We don't trim the system prompt or the end prompt as they are essential.
        # Use binary search to find the optimal trim point efficiently.
        if current_tokens > effective_max_tokens and messages:
            # Binary search: find the minimum number of messages to remove from the front
            lo, hi = 0, len(messages)
            best_trim = len(messages)  # worst case: remove everything

            while lo <= hi:
                mid = (lo + hi) // 2
                trimmed = messages[mid:]
                candidate_context = system_msg + trimmed + end_msg
                tokens = await self.chat.count_tokens(candidate_context)

                if tokens <= effective_max_tokens:
                    best_trim = mid
                    hi = mid - 1
                else:
                    lo = mid + 1

            messages = messages[best_trim:]
            full_context = system_msg + messages + end_msg
            current_tokens = await self.chat.count_tokens(full_context)

        # If we are STILL over the limit even with empty history,
        # the system prompt + end prompt alone exceed the limit, or a single message is too large.
        if current_tokens > max_tokens:
            await self.channel.push(
                f"Your system prompt of {current_tokens} tokens somehow exceeds the maximum context size of {max_tokens}! Please set a larger context size. Or disable some modules, disable system prompt insertion across modules, do whatever you can to reduce token size."
            )

            # immediately disconnect so we don't spam the API
            await self.channel.manager.API.disconnect()

            return None

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
