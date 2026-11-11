import asyncio
import hashlib
import json
import json_repair
import re

import partial_json_parser

def parse_lenient_json(raw):
    """parse a (possibly incomplete) JSON object string into a plain dict.
    never raises: falls back to {'_raw': text} for non-JSON input."""
    if not isinstance(raw, str) or not raw.strip():
        return {}
    try:
        parsed = partial_json_parser.loads(raw, allow_partial=partial_json_parser.Allow.ALL)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass
    return {"_raw": raw}


def turn_hash(turn):
    """stable content hash for a grouped turn"""
    parts = []
    for message in turn.get("messages", []):
        calls = ",".join(
            f"{tc.get('id')}:{(tc.get('_metadata') or {}).get('response')}"
            for tc in (message.get("tool_calls") or [])
        )
        parts.append("|".join([
            str(message.get("index")),
            str(message.get("role")),
            str(message.get("content")),
            str(message.get("reasoning_content")),
            str((message.get("_metadata") or {}).get("is_cmd")),
            calls,
        ]))
    payload = "\n".join(parts).encode("utf-8")
    return hashlib.md5(payload).hexdigest()


class TurnCollector:
    """
    this takes a raw openAI messages array and turns it into a grouped list of dicts,
    where a "turn" is a group of any assistant/tool messages inbetween a user's request
    
    (but now we use steps, which is like a sub-turn.. where it groups reasoning, content, and its associated toolcalls together into one "step")

    so basically, a user makes their request, then the response gets grouped into one single object
    that contains multiple messages, grouped by type (reasoning, content, toolcall, etc)

    this works for chat history (group_history) and even for streams (group_stream)

    this is a port from the old webui's frontend-only turn collection logic
    now available in the core for any channel to use :)
    """

    def __init__(self, channel=None):
        self.channel = channel

    def on_result_summary(self, tool, meta):
        """ask the module that owns this tool for a one-line result hint.

        a module may define  on_tool_summary(self, name, args, response) -> str;
        """
        try:
            if "response" not in meta:
                return ""
            
            # bridged (tools_call) calls summarize as the tool they wrap
            name = meta.get("display_name") or (tool.get("function") or {}).get("name")
            
            if not name:
                return ""
            
            loader = getattr(self.channel, "tool_loader", None)
            if loader is None:
                return ""
            
            entry = loader.catalog.get(name)
            if entry is None:
                return ""
            
            module = self.channel.manager.modules.get(entry["module"])
            hook = getattr(module, "on_tool_summary", None)
            if not callable(hook):
                return ""
            
            response = meta.get("response")
            if isinstance(response, str):
                try:
                    response = json.loads(response)
                except (json.JSONDecodeError, ValueError):
                    pass
                
            text = hook(name, meta.get("args_parsed") or {}, response)
            if not text:
                return ""
            
            text = str(text).strip()
            if not text:
                return ""
            return text.splitlines()[0][:120]
        except Exception:
            return ""

    async def group_history(self, history):
        """
        Groups all finalized messages from history into turns.
        Returns a list of turn objects.
        """
        turns = []
        current_assistant_turn = None

        for index, msg in enumerate(history):
            msg = dict(msg)

            role = msg.get('role')

            # add the index to the message so that it can be directly targeted no matter which turn it is in
            msg["index"] = index
            
            if role == 'user':
                if current_assistant_turn:
                    # if a user message arrives and it's currently still
                    # the assistant's turn, that means we finalize it, and move onto a new turn!
                    turns.append(current_assistant_turn)
                    current_assistant_turn = None
                
                # append the user message as a single turn. a user message is never multiple turns
                turns.append({
                    "role": "user",
                    "messages": [msg.copy()],
                    "first_message_index": index
                })
            else:
                # create the assistant turn if it doesn't already exist
                if not current_assistant_turn:
                    current_assistant_turn = {
                        "role": "assistant",
                        "first_message_index": index,
                        "messages": []
                    }

                # update the last message index.. since this is a for loop,
                # by the time we reach the last message, this will be set to the last message index
                current_assistant_turn["last_message_index"] = index
                    
                current_assistant_turn["messages"].append(msg)

        if current_assistant_turn:
            turns.append(current_assistant_turn)

        # merge tool responses into their tool calls
        for turn in turns:
            if turn["role"] != 'assistant':
                continue
            
            response_map = {}
            for msg in turn["messages"]:
                if msg.get("role") == 'tool':
                    response_map[msg["tool_call_id"]] = msg.get("content")

            for msg in turn["messages"]:
                if msg.get("tool_calls"):
                    annotated_tools = []
                    for tool in msg["tool_calls"]:
                        tool = dict(tool)
                        meta = {}
                        tool["_metadata"] = meta
                        if tool.get("id") in response_map:
                            meta["response"] = response_map[tool["id"]]
                        # precompute the failed flag so channels don't
                        # re-parse every response just to tint a card
                        
                        meta["failed"] = self._tool_call_failed(tool)
                        # ... and the parsed arguments (plus the one-line arg
                        # summary for headers). tools_call proxies are unwrapped
                        # so the card shows the proxied call, not the wrapper.
                        
                        raw_args = (tool.get("function") or {}).get("arguments")
                        parsed_args = parse_lenient_json(raw_args)
                        bridge_name, bridge_args = self._bridge_from_args(
                            (tool.get("function") or {}).get("name"), parsed_args, raw_args
                        )
                        if bridge_name is not None or bridge_args is not None:
                            meta["bridge"] = True
                            if bridge_name:
                                meta["display_name"] = bridge_name
                            meta["args_parsed"] = bridge_args if bridge_args is not None else {}
                            meta["summary"] = self._summary_from_args(meta["args_parsed"])
                        else:
                            meta["args_parsed"] = parsed_args
                            meta["summary"] = self._tool_call_summary(tool)
                            
                        meta["result_summary"] = self.on_result_summary(tool, meta)
                        annotated_tools.append(tool)
                    msg["tool_calls"] = annotated_tools

        for turn in turns:
            turn["hash"] = turn_hash(turn)

        for turn in turns:
            if turn["role"] != "assistant":
                continue
            steps, final_messages = self.build_steps(turn["messages"])
            turn["steps"] = steps
            turn["final_messages"] = final_messages

        return turns

    @staticmethod
    def _tool_call_failed(tool):
        # a tool call failed when its parsed response is {status: "error"}
        # response lives under the call's _metadata key
        response = (tool.get("_metadata") or {}).get("response")
        
        if response is None:
            return False
        
        try:
            parsed = json.loads(response) if isinstance(response, str) else response
        except (json.JSONDecodeError, TypeError):
            return False
        
        return isinstance(parsed, dict) and parsed.get("status") == "error"

    # one-line arg summary for completed tool call headers, ported from
    # the webui frontend's toolCallArgsSummary(): the single most
    # informative argument value, paths keep their tail.
    TOOL_ARG_PRIORITY = [
        "path", "file_path", "filepath", "file", "filename", "url",
        "query", "pattern", "regex_pattern", "sub_path", "subfolder",
        "folder", "id", "name", "content", "text",
    ]

    @staticmethod
    def _truncate_arg(s):
        if len(s) <= 70:
            return s
        if "/" in s or "\\" in s:
            return ".." + s[-68:]
        return s[:69].rstrip() + ".."

    @staticmethod
    def _arg_to_string(value):
        if isinstance(value, str):
            return value
        if isinstance(value, (dict, list)):
            try:
                return json.dumps(value)
            except (TypeError, ValueError):
                return str(value)
        if value is None:
            return "null"
        if value is True:
            return "true"
        if value is False:
            return "false"
        return str(value)

    # tools_call (and friends) proxy the real call as {name, params}.
    # display-wise we unwrap that
    BRIDGE_TOOLS = ("tools_call",)

    @classmethod
    def _bridge_from_args(cls, tool_name, wrapper_args, raw=""):
        """Extract whatever is confidently known from a bridge tool's (possibly
        partial) wrapper args: (display_name_or_None, inner_args_or_None).

        Both None means "not a recognisable bridge call yet" -> render raw.
        Order-agnostic: models may stream {"arguments": {...}, "name": ...},
        and the inner args must already display while the name is still
        pending, or long arguments never appear to stream at all.
        """
        if tool_name not in cls.BRIDGE_TOOLS or not isinstance(wrapper_args, dict):
            return None, None

        name = wrapper_args.get("name")
        name = name.strip() if isinstance(name, str) and name.strip() else None

        if name is None and raw:
            try:
                repaired_wrapper = json_repair.loads(raw)
            except Exception:
                repaired_wrapper = None
            if isinstance(repaired_wrapper, dict) and repaired_wrapper:
                wrapper_args = repaired_wrapper
                name = wrapper_args.get("name")
                name = name.strip() if isinstance(name, str) and name.strip() else None

        if name is not None:
            complete = False
            if raw:
                if len(raw) < 512:
                    try:
                        json.loads(raw)
                        complete = True
                    except (ValueError, TypeError):
                        pass
                if not complete:
                    complete = re.search(
                        r'"name"\s*:\s*"' + re.escape(name) + r'\s*"', raw
                    ) is not None
            else:
                # no raw to check (shouldn't happen via turns): fall back to
                # the old sibling heuristic so history still unwraps.
                complete = (
                    "params" in wrapper_args or "arguments" in wrapper_args
                    or len(wrapper_args) >= 2
                )
            if not complete:
                name = None

        inner = wrapper_args.get("params")
        if inner is None:
            inner = wrapper_args.get("arguments")
        if isinstance(inner, str):
            inner_parsed = parse_lenient_json(inner)
            if "_raw" in inner_parsed:
                try:
                    inner_parsed = json_repair.loads(inner)
                except Exception:
                    inner_parsed = None
            inner = inner_parsed if isinstance(inner_parsed, dict) else None
        elif inner is not None and not isinstance(inner, dict):
            inner = None
            
        if inner is None and raw:
            started = re.search(r'"(?:arguments|params)"\s*:\s*[{"\[]', raw)
            if started:
                chunk = raw[started.end() - 1:]
                sliced = parse_lenient_json(chunk)
                if isinstance(sliced, dict) and "_raw" not in sliced:
                    inner = sliced
                else:
                    try:
                        cand = json_repair.loads(chunk)
                        if isinstance(cand, str):
                            cand = json_repair.loads(cand)
                        if isinstance(cand, dict) and cand:
                            inner = cand
                    except Exception:
                        pass
        if name is None and inner is None:
            return None, None
        return name, inner

    @staticmethod
    def _display_name(tool):
        """The name a tool call should display as (unwrapped bridge name if any)."""
        return ((tool.get("_metadata") or {}).get("display_name")
                or (tool.get("function") or {}).get("name"))

    @classmethod
    def _summary_from_args(cls, args):
        if not isinstance(args, dict) or not args or "_raw" in args:
            return ""
        entries = list(args.items())
        chosen = None
        for priority_key in cls.TOOL_ARG_PRIORITY:
            hit = next(((k, v) for k, v in entries if k == priority_key), None)
            if hit:
                chosen = hit
                break
        if chosen is None:
            chosen = next(((k, v) for k, v in entries if isinstance(v, str)), entries[0])
        return "(" + cls._truncate_arg(cls._arg_to_string(chosen[1])) + ")"

    @classmethod
    def _tool_call_summary(cls, tool):
        raw = (tool.get("function") or {}).get("arguments")
        if not isinstance(raw, str):
            return ""
        return cls._summary_from_args(parse_lenient_json(raw))

    @staticmethod
    def _modules_for(tool_calls):
        # deduped per-function counts grouped by module (first token):
        # [{"module": "Coder", "actions": [{"name": "file edit", "count": 2}]}]
        counts = {}
        order = []
        for tool in tool_calls or []:
            fn = TurnCollector._display_name(tool)
            if not fn:
                continue
            if fn not in counts:
                counts[fn] = 0
                order.append(fn)
            counts[fn] += 1
        groups = {}
        group_order = []
        for fn in order:
            parts = fn.split("_")
            module = parts[0][:1].upper() + parts[0][1:]
            action = "_".join(parts[1:])
            if module not in groups:
                groups[module] = []
                group_order.append(module)
            existing = next((a for a in groups[module] if a["name"] == action), None)
            if existing:
                existing["count"] += counts[fn]
            else:
                groups[module].append({"name": action, "count": counts[fn]})
        return [{"module": m, "actions": groups[m]} for m in group_order]

    @staticmethod
    def _step_status(tool_calls):
        # running: some call still lacks a response. failed: every call
        # failed. thoughts: tool-less step.
        if not tool_calls:
            return "thoughts"
        if any((t.get("_metadata") or {}).get("response") is None for t in tool_calls):
            return "running"
        if all(TurnCollector._tool_call_failed(t) for t in tool_calls):
            return "failed"
        return "done"

    @staticmethod
    def _is_final_content(msg):
        return (
            msg.get("role") == "assistant"
            and not msg.get("tool_calls")
            and isinstance(msg.get("content"), str)
            and msg.get("content", "").strip() != ""
        )

    @staticmethod
    def _segment_label(segment):
        # short human label for the collapsed Process header: the last
        # tool call as "Module: action", or what the model is busy doing
        tool_calls = segment.get("tool_calls")
        if tool_calls:
            # unwrapped bridge name when available (staticmethod: no self!)
            fn = TurnCollector._display_name(tool_calls[-1])
            if fn:
                parts = fn.split("_")
                return parts[0][:1].upper() + parts[0][1:] + ": " + " ".join(parts[1:])
        if isinstance(segment.get("reasoning_content"), str) and segment["reasoning_content"].strip():
            return "Thinking.."
        if isinstance(segment.get("content"), str) and segment["content"].strip():
            return "writing"
        return ""

    @staticmethod
    def _has_visible_chain_content(msg):
        if msg.get("tool_calls"):
            return len(msg["tool_calls"]) > 0
        if isinstance(msg.get("reasoning_content"), str) and msg["reasoning_content"].strip():
            return True
        if msg.get("role") == "assistant" and isinstance(msg.get("content"), str) and msg["content"].strip():
            return True
        return False

    def build_steps(self, messages):
        """split a finalized assistant turn's messages into (steps, final)"""
        final_indices = set()
        i = len(messages) - 1
        while i >= 0 and self._is_final_content(messages[i]):
            final_indices.add(i)
            i -= 1

        chain = []
        final = []
        for i, message in enumerate(messages):
            if i in final_indices:
                if isinstance(message.get("reasoning_content"), str) and message["reasoning_content"].strip():
                    chain_copy = dict(message)
                    chain_copy["content"] = ""
                    chain.append(chain_copy)
                    final_copy = dict(message)
                    final_copy.pop("reasoning_content", None)
                    final.append(final_copy)
                else:
                    final.append(message)
            elif self._has_visible_chain_content(message):
                chain.append(message)

        steps = []
        step_num = 0
        i = 0
        while i < len(chain):
            m = chain[i]
            has_tools = bool(m.get("tool_calls"))

            if has_tools:
                step_num += 1
                steps.append({
                    "step": step_num,
                    "status": self._step_status(m["tool_calls"]),
                    "reasoning_content": m.get("reasoning_content") or "",
                    "content": m.get("content") or "",
                    "tool_calls": m["tool_calls"],
                    "modules": self._modules_for(m["tool_calls"]),
                })
                i += 1
                continue

            # thought run: consecutive reasoning/content segments
            def is_thought(msg):
                return (
                    not msg.get("tool_calls")
                    and ((isinstance(msg.get("reasoning_content"), str) and msg["reasoning_content"].strip())
                         or (isinstance(msg.get("content"), str) and msg["content"].strip()))
                )
            j = i
            while j < len(chain) and is_thought(chain[j]):
                j += 1
            tool_seg = chain[j] if (j > i and j < len(chain) and chain[j].get("tool_calls")) else None

            reasoning = ""
            content = ""
            for k in range(i, j):
                if chain[k].get("reasoning_content"):
                    reasoning = (reasoning + "\n\n" if reasoning else "") + chain[k]["reasoning_content"]
                if chain[k].get("content"):
                    content = (content + "\n\n" if content else "") + chain[k]["content"]

            if tool_seg:
                # the run led to a tool call: fold it into that step
                step_num += 1
                steps.append({
                    "step": step_num,
                    "status": self._step_status(tool_seg["tool_calls"]),
                    "reasoning_content": reasoning,
                    "content": content,
                    "tool_calls": tool_seg["tool_calls"],
                    "modules": self._modules_for(tool_seg["tool_calls"]),
                })
                i = j + 1
            elif j == len(chain):
                # trailing thought run with no tool call: a thoughts step
                step_num += 1
                steps.append({
                    "step": step_num,
                    "status": "thoughts",
                    "reasoning_content": reasoning,
                    "content": content,
                    "tool_calls": [],
                    "modules": [],
                })
                i = j
            else:
                # thought run followed by something odd (e.g. tool-result
                # only message): keep the message as its own thoughts step
                step_num += 1
                steps.append({
                    "step": step_num,
                    "status": "thoughts",
                    "reasoning_content": m.get("reasoning_content") or "",
                    "content": m.get("content") or "",
                    "tool_calls": [],
                    "modules": [],
                })
                i += 1

        return steps, final

    async def group_stream(self, stream_generator):
        """
        this takes the stream object and yields the in-progress turn
        as step objects (dicts), shaped exactly like the steps
        build_steps() produces for history.

        high-frequency continuations are tiny append events (step_delta /
        final_delta). a full snapshot is emitted every 128 appends per step
        (streamed tool arguments: every 8th), plus on run-starts and every
        structural change, so any consumer can self-heal from a desync by
        simply ignoring deltas until the next full snapshot arrives.

        events yielded:
          {"type": "token", "content": raw_token}
              unchanged passthrough of every raw token (user messages,
              api errors, prompt progress, usage, ...)
          {"type": "step", "content": step}
              a step keyed by the step number. the step carries the same
              fields as a history step (step, status, reasoning_content,
              content, tool_calls, modules, label) plus two live-only flags:
                reasoning_live: while the AI is still reasoning
                is_tail:        while the step is the open end of the chain
          {"type": "step_delta", "content": delta}
              an append to a step:
              {"step": n, "append": [{"field": "reasoning_content",
              "text": chunk}, {"field": "tool_response",
              "id": call_id, "text": chunk}]}
          {"type": "final", "content": [messages]}
              a turn's final message(s), decided at the very end of the stream.
              during the steam, there is no way to determine which message is final,
              because a `content` token can at any time be followed up with `reasoning`
              or `tool_calls`.
          {"type": "final_delta", "content": delta}
              an append to the provisional final's content:
              {"step": n, "text": chunk}

        this used to be exclusive to the webUI, handled in the frontend.
        but since this is now in the core, it can be used in *ANY* channel.

        usage: (from within your channel's run()):
          async for event in self.get_streaming_turns(
              self.send_stream("user's message")
          ):
              do_whatever_with(event)
        """

        stream_response_map = {}

        step_num = 0
        step_has_tools = False
        steps = []
        steps_by_num = {}
        tools_owner = {}
        provisional_final = None
        last_token_type = None

        delta_counts = {}
        responses_seen = set()
        pending_deltas = []

        # args_parsed cache keyed by tool call id
        args_cache = {}
        inner_cache = {}
        name_cache = {}

        def _stamp_args(tool):
            tool_id = tool.get("id")
            raw = (tool.get("function") or {}).get("arguments")
            parsed = parse_lenient_json(raw)
            prev = args_cache.get(tool_id)
            if prev is not None and len(prev) > len(parsed):
                parsed = prev
            else:
                args_cache[tool_id] = parsed
            meta = tool.setdefault("_metadata", {})
            bridge_name, bridge_args = self._bridge_from_args(
                (tool.get("function") or {}).get("name"), parsed, raw
            )
            if bridge_name is None and bridge_args is None:
                if tool_id in name_cache:
                    # name resolved on an earlier token: keep the card fully
                    # unwrapped (inner args from the cache when we have them)
                    meta["bridge"] = True
                    meta["display_name"] = name_cache[tool_id]
                    cached_inner = inner_cache.get(tool_id)
                    meta["args_parsed"] = cached_inner if cached_inner is not None else parsed
                else:
                    meta["args_parsed"] = parsed
            else:
                meta["bridge"] = True
                if bridge_args is None:
                    bridge_args = inner_cache.get(tool_id)
                elif inner_cache.get(tool_id) is not None and len(inner_cache[tool_id]) > len(bridge_args):
                    bridge_args = inner_cache[tool_id]
                if bridge_args is not None:
                    inner_cache[tool_id] = bridge_args
                if bridge_name:
                    name_cache[tool_id] = bridge_name
                    meta["display_name"] = bridge_name
                elif tool_id in name_cache:
                    meta["display_name"] = name_cache[tool_id]
                meta["args_parsed"] = bridge_args if bridge_args is not None else {}

        emit_steps = []
        queued_ids = set()

        def queue(step):
            if step is not None and id(step) not in queued_ids:
                queued_ids.add(id(step))
                emit_steps.append(step)

        def bump_step():
            """open a new step number when the current one is closed off
            (no step yet, or it already attached tools). demotes the old
            tail so exactly one step ever carries is_tail."""
            nonlocal step_num, step_has_tools

            demoted = []
            if step_num == 0 or step_has_tools:
                for s in steps:
                    if s.get("is_tail"):
                        s["is_tail"] = False
                        s["reasoning_live"] = False
                        if not s["tool_calls"] and s["status"] == "thinking":
                            s["status"] = "thoughts"
                        stamp_label(s)
                        demoted.append(s)
                step_num += 1
                step_has_tools = False
            return demoted

        def get_step():
            step = steps_by_num.get(step_num)
            if step is None:
                step = {
                    "step": step_num,
                    "status": "thinking",
                    "reasoning_content": "",
                    "content": "",
                    "tool_calls": [],
                    "modules": [],
                    "label": "",
                    "reasoning_live": False,
                    "is_tail": True,
                }
                steps.append(step)
                steps_by_num[step_num] = step
            return step

        def stamp_step(step):
            step["modules"] = self._modules_for(step["tool_calls"])
            if step["tool_calls"]:
                step["status"] = self._step_status(step["tool_calls"])
            stamp_label(step)

        def stamp_label(step):
            # same builder as before, but a settled thought reads Thoughts
            # (the idle-state rename the frontend used to do live-side only)
            label = self._segment_label(step)
            if label == "Thinking.." and not step["reasoning_live"]:
                label = "Thoughts"
            step["label"] = label

        def step_is_visible(step):
            return bool(
                step["tool_calls"]
                or step["reasoning_content"].strip()
                or step["content"].strip()
            )

        def retract_final():
            """fold the provisional final bubble back into its step
            (build_steps joins a thought run's content with \n\n).
            returns the step to re-emit, or None when nothing remained."""
            nonlocal provisional_final

            message = provisional_final
            provisional_final = None

            text = message.get("content") or ""
            step = steps_by_num.get(step_num)
            if step is None and not text.strip() and not message.get("is_cmd"):
                return None

            step = step or get_step()
            if message.get("is_cmd"):
                step["is_cmd"] = True
            if text.strip():
                step["content"] = (step["content"] + "\n\n" if step["content"] else "") + text
            step["reasoning_live"] = False
            step["is_tail"] = True
            stamp_label(step)
            return step

        def refresh_tools(step):
            for tool in step["tool_calls"]:
                # annotations live under the call's _metadata key
                meta = tool.setdefault("_metadata", {})
                if tool.get("id") in stream_response_map:
                    meta["response"] = stream_response_map[tool["id"]]
                    # precomputed failed flag (mirrors group_history)
                    meta["failed"] = self._tool_call_failed(tool)
                # parsed args (mirrors group_history; unwraps tools_call)
                _stamp_args(tool)
                # arg summary on the (possibly unwrapped) args
                if meta.get("bridge"):
                    meta["summary"] = self._summary_from_args(meta.get("args_parsed"))
                else:
                    meta["summary"] = self._tool_call_summary(tool)
                    
                # module-owned one-line result hint, live path (mirrors group_history)
                meta["result_summary"] = self.on_result_summary(tool, meta)

        def merge_tool_calls(step, incoming_calls):
            existing_calls = step["tool_calls"]
            for incoming_call in incoming_calls:
                # copy on insert: shared with the stored message's tool calls
                incoming_call = dict(incoming_call)
                call_id = incoming_call.get("id")
                if call_id:
                    for idx, existing_call in enumerate(existing_calls):
                        if existing_call.get("id") == call_id:
                            existing_calls[idx] = incoming_call
                            break
                    else:
                        existing_calls.append(incoming_call)
                elif existing_calls and not existing_calls[-1].get("id"):
                    # no id to match on: assume it continues the last
                    # id-less call (providers that stream ids late/never)
                    existing_calls[-1] = incoming_call
                else:
                    existing_calls.append(incoming_call)
            for tc in existing_calls:
                if tc.get("id"):
                    tools_owner[tc["id"]] = step

        async for raw_token in stream_generator:
            # copy the token so we don't mutate it
            token = dict(raw_token)

            # enrich prompt progress with precomputed percent + ETA
            if token.get("type") == "prompt_progress" and isinstance(token.get("content"), dict):
                progress = dict(token["content"])
                cache = progress.get("cache") or 0
                processed = (progress.get("processed") or 0) - cache
                total = (progress.get("total") or 0) - cache
                elapsed_ms = progress.get("time_ms") or 0

                percent = round((processed / total) * 100) if total > 0 else 0
                eta = (elapsed_ms / 1000 / processed) * (total - processed) if (processed > 0 and total > processed) else 0

                progress["percent"] = percent
                progress["eta_seconds"] = round(eta, 1)
                token["content"] = progress

            # yield the raw token in case it needs to be processed 
            # (for things like user messages, API errors, etc)
            yield {"type": "token", "content": token}

            # skip grouping for non-display tokens
            if token.get("type") in ['prompt_progress', 'token_usage', 'timings', 'user_message', 'model_load_progress']:
                continue

            # remove timing data from the token
            if token.get("timings"):
                token.pop("timings")

            token_type = token.get("type")

            # merge tool call deltas and toolcalls into one type
            if token_type in ['tool_call_delta', 'tool_calls']:
                token_type = 'tool_calls'

            # per-token emit bookkeeping (queue() dedupes by identity:
            # step DICTS compare equal, retract+attach touch the same one)
            emit_steps.clear()
            queued_ids.clear()
            emit_final = False
            emit_final_delta = None
            retracted = None
            pending_deltas.clear()

            # ----
            # per-token machine. every branch mirrors a build_steps()
            # folding rule; after the branch, the emit phase ships whatever
            # this token touched: full snapshots at checkpoints and
            # structural changes, tiny append deltas in between.
            # ----
            if token_type == 'reasoning':
                # step numbers bump on SEGMENT boundaries only (the old
                # type-switch rule): continuation tokens of a live run must
                # never re-bump - bump_step looks at step_has_tools, which
                # this very machine mutates mid-run
                if last_token_type != 'reasoning':
                    for demoted in bump_step():
                        queue(demoted)
                step = get_step()

                if provisional_final is not None:
                    retracted = retract_final()

                if last_token_type != 'reasoning':
                    # new reasoning run inside this step: build_steps joins
                    # a thought run's segments with a blank line
                    if step["reasoning_content"]:
                        step["reasoning_content"] += "\n\n"
                    step["reasoning_live"] = True
                    step["is_tail"] = True
                    if not step["tool_calls"] and step["status"] == "thoughts":
                        # a thought that resumes after a retract/resume is
                        # live again: un-settle it so the dot pulses
                        step["status"] = "thinking"

                if token.get("content"):
                    step["reasoning_content"] += token["content"]

                if token.get("content") and last_token_type == 'reasoning':
                    delta_counts[step_num] = delta_counts.get(step_num, 0) + 1
                    if delta_counts[step_num] % 128:
                        pending_deltas.append({
                            "step": step_num,
                            "append": [{
                                "field": "reasoning_content",
                                "text": token["content"],
                            }],
                        })
                    else:
                        stamp_label(step)
                        queue(step)
                else:
                    stamp_label(step)
                    queue(step)

            elif token_type == 'content':
                if last_token_type != 'content' or provisional_final is None:
                    # a content run opens as the PROVISIONAL FINAL: while it
                    # is the newest thing in the stream it renders as an
                    # answer bubble - mid-stream there is no way to know
                    # whether a later segment pulls it back into the chain
                    for demoted in bump_step():
                        queue(demoted)

                    settled = steps_by_num.get(step_num)
                    if settled is not None and settled.get("is_tail"):
                        # the open step's reasoning just completed
                        settled["is_tail"] = False
                        settled["reasoning_live"] = False
                        if not settled["tool_calls"] and settled["reasoning_content"].strip():
                            settled["status"] = "thoughts"
                        stamp_label(settled)
                        queue(settled)

                    provisional_final = {
                        "role": "assistant",
                        "type": "content",
                        "step": step_num,
                        "content": token.get("content") or "",
                        "label": "writing",
                    }
                    if token.get("is_cmd"):
                        provisional_final["is_cmd"] = True
                    emit_final = True
                else:
                    added = token.get("content") or ""
                    provisional_final["content"] += added
                    delta_counts["final"] = delta_counts.get("final", 0) + 1
                    if delta_counts["final"] % 128 == 0:
                        emit_final = True
                    elif added:
                        emit_final_delta = {
                            "step": provisional_final["step"],
                            "text": added,
                        }

            elif token_type == 'tool_calls':
                if provisional_final is not None:
                    retracted = retract_final()
                # boundary-gated bump (same rule as reasoning): without
                # this, the tool_has_tools flag set by this very branch
                # makes every streamed argument delta mint a brand new
                # step (the exact cascade the 2026-10-25 first cut shipped)
                if last_token_type != 'tool_calls':
                    for demoted in bump_step():
                        queue(demoted)
                step = get_step()

                step["reasoning_live"] = False
                step["is_tail"] = True
                if token.get("tool_calls"):
                    merge_tool_calls(step, token["tool_calls"])
                step_has_tools = True
                refresh_tools(step)
                stamp_step(step)
                if last_token_type == 'tool_calls':
                    # streamed args re-parse every token: send a snapshot
                    # only every 8th, the display reads server-parsed
                    # args_parsed, so there is no clean append to delta
                    delta_counts[step_num] = delta_counts.get(step_num, 0) + 1
                    if delta_counts[step_num] % 8 == 0:
                        queue(step)
                else:
                    queue(step)

            elif token_type == 'tool':
                # responses accumulate per call; the OWNING step re-emits
                # (a late response can never land on the wrong step, unlike
                # the old last-segment guesswork)
                stream_response_map[token["tool_call_id"]] = (
                    stream_response_map.get(token["tool_call_id"]) or ""
                ) + (token.get("content") or "")
                step = tools_owner.get(token["tool_call_id"])
                if step is not None:
                    first_chunk = token["tool_call_id"] not in responses_seen
                    responses_seen.add(token["tool_call_id"])
                    if first_chunk:
                        refresh_tools(step)
                        stamp_step(step)
                        queue(step)
                    else:
                        delta_counts[token["tool_call_id"]] = (
                            delta_counts.get(token["tool_call_id"], 0) + 1
                        )
                        if delta_counts[token["tool_call_id"]] % 128 == 0:
                            refresh_tools(step)
                            stamp_step(step)
                            queue(step)
                        elif token.get("content"):
                            # keep the internal snapshot current silently,
                            # the delta carries the chunk to the client
                            for tool in step["tool_calls"]:
                                if tool.get("id") == token["tool_call_id"]:
                                    tool.setdefault("_metadata", {})["response"] = (
                                        stream_response_map[token["tool_call_id"]]
                                    )
                                    break
                            pending_deltas.append({
                                "step": step["step"],
                                "append": [{
                                    "field": "tool_response",
                                    "id": token["tool_call_id"],
                                    "text": token["content"],
                                }],
                            })

            last_token_type = token_type

            # ----
            # emit phase: changed steps first (ghosts without any visible
            # content are skipped), then final-snapshot changes: a retraction
            # yields an EMPTY list, a growing provisional final yields itself
            # (once it has visible text).
            # ----
            for step in emit_steps:
                if step_is_visible(step):
                    yield {"type": "step", "content": step}
            for delta in pending_deltas:
                yield {"type": "step_delta", "content": delta}
            if retracted is not None:
                yield {"type": "final", "content": []}
            if emit_final and (provisional_final.get("content") or "").strip():
                yield {"type": "final", "content": [provisional_final]}
            if emit_final_delta:
                yield {"type": "final_delta", "content": emit_final_delta}

