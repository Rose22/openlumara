import core
import json

class Context:
    # special message type (not intended to be added to context) that
    # will cause context.get() to cut off messages before this cutoff point
    SUMMARIZATION_CUTOFF = {"_metadata": {"signal": "SUMMARIZATION_CUTOFF"}}

    def __init__(self, channel):
        self.channel = channel
        self.model_name = None
        self.using_api_token_data = False
        self.token_encoding = None
        self.compressing = False
        self._overflow_warned = False

        # prompt cache invalidation debugging
        self._prompt_cache_state = {}

        # UI-agnostic chat history system - save/load context windows from save file!
        self.chat = core.chat.Chat(self.channel)

    async def get(self, system_prompt=True, end_prompt=True, history=True, prevent_recursion=False, trim=True):
        """
        builds the full context window using system prompt + message history + end prompt
        to the API, we send this full context.
        to frontend channels, we send only the message history part of the context (context.chat.messages.get()),
        without the system prompt and without the modifications we do to it such as the endprompt.
        context must ALWAYS follow this strict turn order: system->user->assistant->user->assistant->user->...
        """
        if not self.channel.manager.API.connected:
            # attempt to connect
            result = await self.channel.manager.API.connect()
            if result is not True:
                self.channel.log("api", str(result))
                return result

        # Configuration
        max_messages = int(core.config.get("api").get("max_messages", 200))
        max_tokens = int(core.config.get("api").get("max_context", 16768))
        system_role = "system" if not self.channel.manager.API.supports_developer_role else "developer"
        dev_role = "developer" if self.channel.manager.API.supports_developer_role else "user"

        # 1. Prepare Components
        system_msg = []
        if system_prompt:
            try:
                content = await self.chat.get_system_prompt()
            except Exception as e:
                self.channel.log_error("Error while getting system prompt", e)

            if content:
                system_msg = [{"role": system_role, "content": content}]

        messages = []
        # set when a summarization cutoff exists so trimming can pin the summary
        summary_ref = None
        if history:
            # Get history from the chat (the full, untrimmed version)
            # create a shallow copy of it by doing a list comprehension
            messages = [dict(msg) for msg in await self.chat.messages.get()]

            # we need to support chat summarization without losing the user-facing end of chat history
            # so that we can cut context without actually losing our logs..

            # so, i'm using a special entry in the messages array that serves as a cutoff point
            # from which to actually return the chat history

            # find the last occurence of it and return only the messages from that point onward
            # keep a reference to the summary message so trimming can never cut past it.
            for i in range(len(messages) - 1, -1, -1):
                if messages[i].get("_metadata", {}).get("signal") == "SUMMARIZATION_CUTOFF":
                    summary_content = messages[i + 1].get("content") if i + 1 < len(messages) else None
                    if isinstance(summary_content, str) and summary_content.strip():
                        summary_ref = {"role": "user", "content": summary_content}
                        messages = [summary_ref] + messages[i + 2:]
                    else:
                        self.channel.log("context", "Broken summarization cutoff detected (summary missing or empty) - ignoring it")
                        messages = messages[i + 2:]
                    break

            # Remove ghost messages and signal messages from history
            messages = [msg for msg in messages if not msg.get("_metadata", {}).get("ghost") and not msg.get("_metadata", {}).get("signal")]

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

                # strip reasoning from tool calls prior to the current agentic loop
                loop_idx = self.channel.agentic_loop_start
                messages[:loop_idx] = [
                    {k: v for k, v in m.items() if k != "reasoning_content"}
                    if "tool_calls" in m else m
                    for m in messages[:loop_idx]
                ]

            # Apply max_messages limit to history first
            # -- prompt-cache optimization: evict in BLOCK-sized chunks instead of one
            # message per append. With a sliding -max_messages: window, every new
            # message (every tool result during an agent loop) shifts every retained
            # message by one slot, which breaks vLLM's automatic prefix caching at the
            # very first message and forces full re-prefill of the whole context on
            # every step. Chunked eviction keeps the retained prefix byte-identical
            # between evictions: the start index only advances once per BLOCK appends.
            #
            # The chunk size is derived deterministically from the history length
            # (no extra state needed): while len(messages) stays inside the same
            # BLOCK-wide band past the limit, the drop count - and therefore the
            # whole sent prefix - is constant.
            EVICT_BLOCK = 32
            if len(messages) > max_messages:
                overflow = len(messages) - max_messages
                drop = ((overflow - 1) // EVICT_BLOCK + 1) * EVICT_BLOCK
                # never cut inside an assistant(tool_calls) -> tool(...) group:
                # leading orphan tool messages are rejected by strict providers,
                # so slide the cut forward past them (drop only grows).
                while drop < len(messages) and messages[drop].get("role") == "tool":
                    drop += 1
                if summary_ref is not None:
                    # keep the pinned summary at the front (same rule the token
                    # trimming below applies - trimming must never cut past it)
                    messages = [summary_ref] + messages[drop:]
                else:
                    messages = messages[drop:]

        end_msg = []
        if end_prompt:
            histend = await self.chat.get_end_prompt(prevent_recursion=prevent_recursion)
            if histend:
                end_msg = [{"role": dev_role, "content": histend}]

        # now we inject anything modules want to inject into the user messages
        for message in messages:
            metadata = message.get("_metadata")
            if not metadata:
                continue

            if metadata.get("injection"):
                if message.get("role") == "user":
                    content = message.get("content")
                    if content and isinstance(content, str):
                        message["content"] += f"\n\n{metadata['injection']}"

        # remove any non-standard (metadata) fields from the messages
        # so that we can cleanly send it to the API
        # we cant just remove only the _metadata field because old chat history used to use metadata fields
        # straight on the message object itself without containing it into a _metadata array,
        # so we need to be aggressive here
        approved_keys = ["role", "content", "reasoning_content", "tool_calls", "tool_call_id", "function_call", "tool"]
        messages = [{k: v for k, v in msg.items() if k in approved_keys} for msg in messages]

        # strip metadata from tool calls
        messages = [
            {
                **msg,
                "tool_calls": [
                    {k: v for k, v in tc.items() if k != "_metadata"} if isinstance(tc, dict) else tc
                    for tc in msg["tool_calls"]
                ]
            }
            if msg.get("tool_calls") else msg
            for msg in messages
        ]

        # remove the content field from a message if its value is None
        cleaned = []
        for msg in messages:
            if msg.get("content") is None:
                if msg.get("role") == "assistant":
                    msg.pop("content", None)
                    cleaned.append(msg)
                else:
                    # user/system/tool messages require the content field according to spec,
                    # but a null value is illegal, so use a blank string instead
                    msg["content"] = ""
                continue
            cleaned.append(msg)
        messages = cleaned

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

                    # assistant -> assistant: insert user spacer
                    if last_role == "assistant" and current_role == "assistant":
                        enforced_messages.append({"role": "user", "content": " "})
                    # user -> user: insert assistant spacer
                    elif last_role == "user" and current_role == "user":
                        enforced_messages.append({"role": "assistant", "content": " "})
                    # tool -> user: insert assistant spacer (tool result without assistant response)
                    elif last_role == "tool" and current_role == "user":
                        enforced_messages.append({"role": "assistant", "content": " "})
                    # user -> tool: insert assistant spacer (tool call without tool result)
                    elif last_role == "user" and current_role == "tool":
                        enforced_messages.append({"role": "assistant", "content": " "})

                enforced_messages.append(msg)

            messages = enforced_messages

        # 2. Build and Trim Context
        # We combine them to check the total token count

        # Count tool tokens separately (tools are passed as a separate API parameter, not as messages)
        tool_tokens = 0
        if self.channel.manager.tools:
            tool_tokens = await self.count_tokens(self.channel.manager.tools)

        # then combine it all
        full_context = system_msg + messages + end_msg
        
        # Calculate current token count (includes tools + context)
        current_tokens = await self.count_tokens(full_context) + tool_tokens

        # Leave a small buffer (5%) to avoid hitting exact limit
        effective_max_tokens = int(max_tokens * 0.95)
        
        # If we are over the limit, trim the history (the middle part).
        # We don't trim the system prompt or the end prompt as they are essential.
        # Use binary search to find the optimal trim point efficiently.

        # trimming is skipped entirely when trim=False so is_over_threshold() can measure raw fullness.
        if current_tokens > effective_max_tokens and messages and trim:
            keep = [summary_ref] if summary_ref else []
            rest = messages[1:] if summary_ref else messages

            # Binary search: find the minimum number of messages to remove from the front of rest
            lo, hi = 0, len(rest)
            best_trim = len(rest)  # worst case: remove everything after the summary

            while lo <= hi:
                mid = (lo + hi) // 2
                candidate_context = system_msg + keep + rest[mid:] + end_msg
                tokens = tool_tokens + await self.count_tokens(candidate_context)

                if tokens <= effective_max_tokens:
                    best_trim = mid
                    hi = mid - 1
                else:
                    lo = mid + 1

            messages = keep + rest[best_trim:]
            full_context = system_msg + messages + end_msg
            current_tokens = tool_tokens + await self.count_tokens(full_context)

        # If we are STILL over the limit even with empty history,
        # the system prompt + end prompt alone exceed the limit, or a single message is too large.
        if trim and current_tokens > max_tokens:
            if not self._overflow_warned:
                self._overflow_warned = True

                await self.channel.push(
                    f"Your system prompt of {current_tokens} tokens somehow exceeds the maximum context size of {max_tokens}! Please set a larger context size. Or disable some modules, disable system prompt insertion across modules, do whatever you can to reduce token size."
                )

            return None

        if core.debug:
            # prompt cache invalidation debug check
            await self._debug_prompt_cache_check(
                full_context,
                (self.chat.current, system_prompt, end_prompt, history, prevent_recursion, trim)
            )

        return full_context

    async def is_over_threshold(self):
        if not core.config.get("model", "automatically_compress_context"):
            return False

        max_tokens = core.config.get("api", "max_context")
        if not max_tokens:
            return False

        threshold = core.config.get("model", "context_compression_threshold")

        used_tokens = await self.get_total_tokens()
        if not used_tokens:
            return False

        used_ratio = used_tokens / max_tokens

        return used_ratio >= threshold

    async def get_latest_summary(self):
        """returns the newest handoff summary in this chat, or None if never compacted"""
        messages = await self.chat.messages.get()
        for i in range(len(messages) - 1, -1, -1):
            if messages[i].get("_metadata", {}).get("signal") == "SUMMARIZATION_CUTOFF":
                if i + 1 < len(messages):
                    return messages[i + 1].get("content")
                return None
        return None

    async def compress(self):
        """compress context using the special summarization cutoff signal (reversible non-destructive compression)"""

        # chat.add() and toolcall_manager.process() both call this function,
        # so this is a guard that prevents compress() from being called recursively
        # where it shouldn't
        if self.compressing:
            return False

        self.compressing = True
        # allow system prompt to be regenerated
        self.chat._cached_system_prompt = None

        # if this chat was compacted before, its summary is merged into rather than re-summarized
        prev_summary = await self.get_latest_summary()

        compress_prompt = """
[SYSTEM INSTRUCTION]
Compress the conversation so far into a handoff summary for a brand-new session with zero other context. A fresh instance reading ONLY this summary must continue seamlessly.

Format (markdown, no preamble, no closing remarks):

1. STATE - 1-3 sentences: what's in flight right now, status, open questions.
2. REQUESTS → OUTCOMES - one bullet per user request: "request: outcome". Merge similar exchanges into one bullet. Telegraphic style (no full sentences, no articles where droppable).
3. FACTS - only specifics needed to continue: exact quoted values (paths, names, IDs, commands, dates, error strings), decisions, preferences learned THIS session. Omit anything already inferable from the system prompt.
4. TOOLS - only calls whose results still matter for continuing: "tool(args-key): result". Omit routine/obsolete calls entirely.
5. NEXT - explicit remaining actions as imperative bullets. Write "none" if done.

Hard rules:
- Brevity beats completeness EXCEPT for exact values (paths, IDs, names, quotes) - those must be verbatim.
- Target: smallest summary that loses no actionable information. If a detail wouldn't change what you do next, cut it.
- No filler ("the user asked whether...", "it was decided that..."). Use fragments.
- NEVER restate identity, memories, tools, scheduler, or anything from the system prompt.
- Never invent or guess details not present in the history.
- No meta-commentary about summarizing. Output the summary only.
""".strip()

        # merge the previous summary with the new one
        # by repeating the summary in the request,
        # since some models won't be good at seeing the previous summary at
        # the very start of context
        if prev_summary:
            compress_prompt += (
                "\n\nPREVIOUS HANDOFF SUMMARY\n"
                "This conversation was compacted before. Your previous handoff summary is quoted below. Merge it into your output:\n"
                "- Move finished NEXT items into REQUESTS -> OUTCOMES.\n"
                "- Replace STATE with the current status based on the newest messages.\n"
                "- Carry over all FACTS and exact values (paths, IDs, names, quotes) unless a newer message contradicts them.\n"
                "- Delete entries invalidated by newer messages.\n"
                "Output ONE unified summary in the same format - never a diff, never mention this section.\n\n"
                '"""\n' + prev_summary + '\n"""'
            )

        # get the user's latest request and pin it in the compaction request
        active_request = None
        for msg in reversed(await self.chat.messages.get()):
            meta = msg.get("_metadata", {})
            if msg.get("role") == "user" and not meta.get("is_cmd") and not meta.get("signal") and not meta.get("ghost"):
                active_request = self.channel._extract_content(msg)
                break

        if active_request:
            compress_prompt += f'\n\nThe user\'s active request is the message below. Before the numbered sections, output a line "ACTIVE USER REQUEST:" followed by this message quoted verbatim. Do NOT paraphrase it.\n"""\n{active_request}\n"""'

        try:
            compress_context = await self.channel.context.get(end_prompt=False)
            if compress_context is None:
                return False

            # request the stream
            stream = self.channel.manager.API.send_stream(
                compress_context + [{"role": "user", "content": compress_prompt}]
            )

            # send the stream into the current channel
            response = await self.channel.push_stream(stream)

            # validate the result
            if not response or not isinstance(response.get("content"), str) or not response.get("content").strip():
                # if the AI somehow decided not to output any final content,
                # we first fall back to the reasoning. and if we can't do that...
                # the compaction has basically failed
                reasoning = response.get("reasoning_content")
                if reasoning and reasoning.strip():
                    response["content"] = reasoning
                else:
                    return False

            # add special cutoff message that gets handled by the context manager
            await self.channel.context.chat.messages.add(self.channel.context.SUMMARIZATION_CUTOFF)

            # add AI's summarization
            await self.channel.context.chat.messages.add(response)

            # the cached API measurement no longer reflects reality after
            # compression (context shrank), so invalidate it until the next one lands
            if self.chat.current is not None:
                self.chat.data[self.chat.current]["token_usage"] = 0
                self.chat.data[self.chat.current]["token_usage_mark"] = 0
                self.using_api_token_data = False

            return response
        finally:
            self.compressing = False

    async def get_size(self):
        """basically just a fancy display of current token use, used by the `/status` command, and can optionally be used by other parts of the framework"""

        # measure all parts from a single trimmed context build so the breakdown sums to what is actually sent to the API.
        max_context = int(core.config.get("api", "max_context"))

        full = await self.get()
        if not full:
            full = []

        # determine whether the system prompt and end prompt parts exist within the built context,
        # so we can slice the full context into system + history + end parts
        try:
            system_present = bool(await self.chat.get_system_prompt())
        except Exception:
            system_present = False
        histend = await self.chat.get_end_prompt(prevent_recursion=True)

        sys_msgs = full[:1] if (system_present and full) else []
        end_msgs = full[-1:] if (histend and len(full) > len(sys_msgs)) else []
        hist_msgs = full[len(sys_msgs): len(full) - len(end_msgs)]

        # now we count the tokens for each part of the context
        sysprompt_size_tokens = await self.count_tokens(sys_msgs)
        sysprompt_size_words = len(str(sys_msgs).split())

        message_hist_size_words = len(str(hist_msgs).split())

        histend_size_tokens = await self.count_tokens(end_msgs)
        histend_size_words = len(str(end_msgs).split()) if end_msgs else 0

        tool_array_size_tokens = await self.count_tokens(self.channel.manager.tools)
        tool_array_size_words = len(str(self.channel.manager.tools).split())

        # get amount of tools active
        tools_amount = len(self.channel.manager.tools)

        combined_size_words = tool_array_size_words + sysprompt_size_words + message_hist_size_words + histend_size_words

        token_usage = await self.get_total_tokens()
        pct_full = round((token_usage / max_context) * 100)

        # count how often this chat has been compacted, based on the number of
        # summarization cutoff markers
        compaction_count = 0
        try:
            for msg in await self.chat.messages.get():
                if msg.get("_metadata", {}).get("signal") == "SUMMARIZATION_CUTOFF":
                    compaction_count += 1
        except Exception:
            pass

        message_hist_size_tokens = max(token_usage - sysprompt_size_tokens - histend_size_tokens - tool_array_size_tokens, 0)

        return {
            "max_context": max_context,
            "total_tokens": token_usage,
            "percent_full": pct_full,
            "compaction_count": compaction_count,
            "total_words": combined_size_words,
            "system_prompt": {"tokens": sysprompt_size_tokens, "words": sysprompt_size_words},
            "tools": {"active": tools_amount, "tokens": tool_array_size_tokens, "words": tool_array_size_words},
            "message_history": {"tokens": message_hist_size_tokens, "words": message_hist_size_words},
            "end_prompt": {"tokens": histend_size_tokens, "words": histend_size_words}
        }

    def _count_text_tokens(self, text: str) -> int:
        """does the actual token-counting by counting characters"""

        if not text:
            return 0
        
        # 1 token is roughly 4 characters for most English text
        return len(text) // 4

    async def record_api_usage(self, num_tokens):
        """caches the API's real prompt token count as the single source of truth,
        along with a mark of how many messages were included in that measurement"""
        if self.chat.current is None or num_tokens <= 0:
            return

        chat_data = self.chat.data[self.chat.current]
        chat_data["token_usage"] = num_tokens
        try:
            chat_data["token_usage_mark"] = len(await self.chat.messages.get())
        except Exception:
            chat_data["token_usage_mark"] = 0

        self.using_api_token_data = True

        await self.chat.save()

    async def get_total_tokens(self):
        """returns the total amount of tokens taken up by the prompt + the tools array.
        the API's reported count is the single source of truth; estimation is only
        used when no API figure exists, or for messages added after it was measured."""
        if self.chat.current is not None:
            chat_data = self.chat.data[self.chat.current]
            api_base = int(chat_data.get("token_usage", 0))
            mark = int(chat_data.get("token_usage_mark", 0))

            # mark > 0 gate: only a real API measurement sets it (new() stores
            # a raw estimate with mark 0, which must not be treated as a base)
            if api_base > 0 and mark > 0:
                messages = await self.chat.messages.get()
                if mark <= len(messages):
                    # estimate only what landed after the API measured, on top of the real number
                    delta = 0
                    if len(messages) > mark:
                        # strip _metadata since it's never sent to the API and would inflate the estimate
                        delta = await self.count_tokens([{k: v for k, v in m.items() if k != "_metadata"} for m in messages[mark:]])
                    return api_base + delta

        # no API data available (fresh chat, or an API that doesn't report usage): estimate
        context = await self.get()
        if not context:
            return 0

        num_tokens = await self.count_tokens(context)

        # add the total token count of the tools array
        if self.channel.manager.tools:
            num_tokens += await self.count_tokens(self.channel.manager.tools)

        return num_tokens

    async def count_tokens(self, data):
        """
        the function that gets called all over the framework to count the token usage of any data.
        converts the data into a json string, then uses _count_text_tokens() to do the actual counting
        """
        num_tokens = 0

        if isinstance(data, core.api.APIError):
            return 0

        try:
            if isinstance(data, list):
                # this is likely an array of messages
                # count only the text tokens, since API's exempt multimodal content from token limits

                # first i coded this function by hand using a for loop that copied each message and stripped it of any non-text content, 
                # then i asked my local AI for a more compact and performance friendly way to do it.
                # now that's a good way to use AI coding, imho :)
                # thanks Qwen3.6-35B!
                cleaned_messages = [
                    {**msg, "content": [item for item in (msg.get("content") or []) if item.get("type") == "text"]}
                    if isinstance(msg.get("content"), list)
                    else msg
                    for msg in data
                ]
                data_str = json.dumps(cleaned_messages)
            else:
                data_str = json.dumps(data)
        except Exception as e:
            raise Exception(f"Error while counting tokens: {core.detail_error(e)}")

        num_tokens = self._count_text_tokens(data_str)
        return num_tokens

    def _fingerprint_context(self, context):
        # per-message snapshots + sha256 fingerprints of the exact dicts sent to the API.
        # snapshots are immutable JSON strings on purpose: the message dicts share nested
        # structures (tool_calls lists etc.) with the chat storage via shallow copies, so
        # holding dict references lets post-build mutations rewrite the "previous" state
        # in-place and hide the real diff.
        import hashlib

        snaps = []
        for msg in context:
            snaps.append(json.dumps(msg, sort_keys=True, ensure_ascii=False, default=str))
        hashes = [hashlib.sha256(s.encode("utf-8")).hexdigest() for s in snaps]
        return hashes, snaps

    def _diff_text(self, a, b):
        """describe how two strings differ: lengths + first divergence + snippets"""
        n = min(len(a), len(b))
        i = 0
        while i < n and a[i] == b[i]:
            i += 1
        if i == n and len(a) != len(b):
            longer = b if len(b) > len(a) else a
            action = "grew" if len(b) > len(a) else "shrank"
            return f"{len(a)} -> {len(b)} chars ({action} by {abs(len(b) - len(a))}, common prefix intact) :: tail {longer[i:i+160]!r}"
        return f"{len(a)} -> {len(b)} chars, first diff at {i} :: was {a[i:i+160]!r} | now {b[i:i+160]!r}"

    def _diff_message_snaps(self, prev_snap, cur_snap):
        """field-by-field diff between two immutable message snapshots.
        logs each changed field and returns (changed_fields, reason)."""
        try:
            p = json.loads(prev_snap)
            c = json.loads(cur_snap)
        except Exception:
            return [], "snapshot diff failed"

        changed_fields = []
        for key in sorted(set(p.keys()) | set(c.keys())):
            pv, cv = p.get(key), c.get(key)
            if pv == cv:
                continue
            changed_fields.append(key)
            if isinstance(pv, str) and isinstance(cv, str):
                self.channel.log("prompt-cache", f"    field {key!r}: {self._diff_text(pv, cv)}")
            else:
                ps = json.dumps(pv, ensure_ascii=False, default=str)
                cs = json.dumps(cv, ensure_ascii=False, default=str)
                if len(ps) > 200 or len(cs) > 200:
                    self.channel.log("prompt-cache", f"    field {key!r}: {self._diff_text(ps, cs)}")
                else:
                    self.channel.log("prompt-cache", f"    field {key!r}: was {ps} | now {cs}")

        reason = "message content mutated"
        if changed_fields == ["reasoning_content"]:
            reason = "reasoning_content text changed on a past message"
        elif changed_fields and set(changed_fields) <= {"tool_calls"}:
            reason = "tool_calls mutated in-place on a past message (shared nested reference!)"
        elif changed_fields == ["content"]:
            reason = "content text changed on a past message"

        return changed_fields, reason

    def _diff_system_prompt(self, prev_snap, cur_snap):
        """line-level diff of two system prompt snapshots, so we can see exactly
        what changed rather than a character offset into a huge string"""
        import difflib

        try:
            p = json.loads(prev_snap).get("content") or ""
            c = json.loads(cur_snap).get("content") or ""
        except Exception:
            return

        if p == c:
            return

        # n=0: only the changed lines, no context padding
        diff_lines = [l for l in difflib.unified_diff(p.splitlines(), c.splitlines(), lineterm="", n=0)][2:]

        # collapse the @@ -x,y +a,b @@ hunk headers into the changed lines only
        changed = [l for l in diff_lines if not l.startswith("@@")]
        if not changed:
            return

        max_lines = 30
        self.channel.log("prompt-cache", f"  system prompt diff ({len(changed)} changed lines):")
        for line in changed[:max_lines]:
            self.channel.log("prompt-cache", f"    | {line[:300]}")
        if len(changed) > max_lines:
            self.channel.log("prompt-cache", f"    | .. {len(changed) - max_lines} more changed lines not shown")

    async def _debug_prompt_cache_check(self, context, flags):
        """check if the context has changed in any way"""
        if not core.debug:
            return
        
        hashes, snaps = self._fingerprint_context(context)

        # the end prompt sits at the very end and legitimately changes every turn,
        # so it is excluded from the prefix comparison
        if flags[2]:  # end_prompt
            core_hashes = hashes[:-1]
            core_snaps = snaps[:-1]
        else:
            core_hashes = hashes
            core_snaps = snaps

        prev = self._prompt_cache_state.get(flags)

        if flags not in self._prompt_cache_state and len(self._prompt_cache_state) >= 8:
            self._prompt_cache_state.pop(next(iter(self._prompt_cache_state)))
        self._prompt_cache_state[flags] = {"hashes": hashes, "core": core_hashes, "snaps": core_snaps}

        if prev is None:
            return

        first_diff = None
        for i in range(min(len(prev["core"]), len(core_hashes))):
            if prev["core"][i] != core_hashes[i]:
                first_diff = i
                break

        if first_diff is None and len(core_hashes) >= len(prev["core"]):
            # pure append: prompt cache intact
            return

        reason = None
        expected = False

        if len(core_hashes) < len(prev["core"]) and core_hashes == prev["core"][len(prev["core"]) - len(core_hashes):]:
            reason = f"history trimmed from the front ({len(prev['core']) - len(core_hashes)} messages dropped)"
        elif len(core_hashes) < len(prev["core"]):
            # context shrank without a clean front-trim: almost certainly compression
            reason = "context compressed (history rewritten into a summary)"
            expected = True

        if reason is None and first_diff is not None:
            try:
                p_role = json.loads(prev["snaps"][first_diff]).get("role")
            except Exception:
                p_role = None
            if first_diff == 0 and p_role in ("system", "developer"):
                reason = "system prompt changed"
                expected = True
                self._diff_system_prompt(prev["snaps"][0], core_snaps[0])

        tag = "expected" if expected else "UNEXPECTED"

        if reason is not None:
            self.channel.log("prompt-cache", f"[{tag}] prompt cache invalidated :: {reason}")
            self.channel.log("prompt-cache", f"  first divergence at message index {first_diff} (core messages: {len(prev['core'])} -> {len(core_hashes)})")
            return

        # a previously-sent message changed. diff it field by field from the
        # immutable snapshots (immune to in-place mutation of the live dicts).
        changed_fields, reason = [], "unknown"
        if first_diff is not None and first_diff < len(prev["snaps"]) and first_diff < len(core_snaps):
            changed_fields, reason = self._diff_message_snaps(prev["snaps"][first_diff], core_snaps[first_diff])

        self.channel.log("prompt-cache", f"[UNEXPECTED] prompt cache invalidated :: {reason}")
        self.channel.log("prompt-cache", f"  first divergence at message index {first_diff} (core messages: {len(prev['core'])} -> {len(core_hashes)})")
        if changed_fields:
            self.channel.log("prompt-cache", f"  changed fields: {', '.join(changed_fields)}")

