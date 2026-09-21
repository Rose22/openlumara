# Core: The Context System (`core.Context`)

The `Context` class is responsible for building the complete "view" of the conversation that is sent to the AI. It manages the logic of how message history, system prompts, and end-prompts are combined to create a coherent prompt while staying within token limits.

## Overview

Each channel has its own Context instance, which manages:
- Building the full context window for API requests
- Token counting and estimation
- Context trimming to fit within model limits
- Message history management

## Responsibilities

### 1. Prompt Assembly
The `Context` ensures that the prompt sent to the AI follows a strict and logical order:
1.  **System Prompt**: The foundational instructions (e.g., identity, rules) provided by the `Manager` and various `Modules`.
2.  **Message History**: The actual conversation between the user and the assistant.
3.  **End Prompt**: Dynamic information (like the current time) that is appended to the very end of the context to ensure the AI has the most up-to-date information without needing to reprocess the entire history.

**Important:** Context must ALWAYS follow this strict turn order: `system` -> `user` -> `assistant` -> `user` -> `assistant` -> ...
- `assistant` -> `tool` -> `assistant` is VALID (tool use flow)
- `assistant` -> `assistant` is INVALID (needs a spacer)

### 2. Token Management and Trimming
To prevent exceeding the AI model's context window, the `Context` performs several optimization and trimming tasks:
- **Token Counting**: Calculates token usage using character-based estimation (~4 chars per token). Note: The old tiktoken-based counting has been replaced with a simpler character division method.
- **Binary Search Trimming**: If the prompt is too large, it uses **binary search** to efficiently find the minimum number of messages to remove from the front until the prompt fits within the allowed limit (with a 5% safety buffer).
- **Max Messages Limit**: Before token trimming, applies a `max_messages` limit (default 200) to history — keeps the most recent N messages.
- **Multimodal Optimization**: To save tokens, it strips non-text content (like images) from all messages in the history except for the most recent one. Stripped multimedia is replaced with `"[multimedia content]"`.

### 3. Role and Turn Management
The `Context` ensures the conversation follows the required turn order:
- **Spacer Messages**: Inserts `" "` spacer messages between:
  - `assistant` -> `assistant` (invalid, needs user spacer)
  - `user` -> `user` (invalid, needs assistant spacer)
  - `tool` -> `user` (invalid, needs assistant spacer)
  - `user` -> `tool` (invalid, needs assistant spacer)
- **Valid flows NOT modified**: `assistant` -> `tool` -> `assistant` is valid and kept as-is.
- **Removes Ghost Messages**: Filters out messages marked as "ghost" (`_metadata.ghost = True`).
- **Removes Signal Messages**: Filters out internal signal messages (like `SUMMARIZATION_CUTOFF`).
- **Handles Reasoning Content**: Manages whether reasoning/thinking tokens should be kept in the context or stripped out, based on config options.

### 4. Injection Processing
- **Module Message Injection**: After assembling the prompt, iterates through messages and appends any `"injection"` field content to user messages. The injection content is appended directly to the message content (no `[SYSTEM MESSAGES]` header in current implementation).

### 5. Error Handling
- If the system prompt + end prompt alone exceed the maximum context size, the Context pushes an error message to the channel and disconnects the API to prevent spamming.

## Class: `Context`

### Initialization

```python
Context(channel)
```

**Parameters:**
- `channel` - The Channel instance that owns this context

**Attributes:**
- `channel` - Reference to the owning channel
- `model_name` - The current model name (initially None)
- `using_api_token_data` - Flag set to True when API provides token usage data
- `token_encoding` - Token encoder (initially None)
- `chat` - Chat instance for this channel (`core.chat.Chat(channel)`)

**Special Message:**
- `SUMMARIZATION_CUTOFF` - Special message type that marks a cutoff point for summarization

### Methods

#### `async get(system_prompt=True, end_prompt=True, history=True, prevent_recursion=False)`

Builds and returns the full list of message dictionaries to be sent to the API.

**Parameters:**
- `system_prompt` (bool) - Include system prompt (default: True)
- `end_prompt` (bool) - Include end prompt (default: True)
- `history` (bool) - Include message history (default: True)
- `prevent_recursion` (bool) - Prevent recursion in token_threshold module (default: False)

**Returns:**
- List of message dicts ready for API, or `APIError`/`None` on error

**Behavior:**
1. Checks/reconnects API if not connected
2. Gets system prompt from `manager.get_system_prompt()`
3. Gets message history from `chat.messages.get()`
4. Applies summarization cutoff if present
5. Removes ghost and signal messages
6. Strips invalid assistant messages (no content, no tool calls)
7. Handles reasoning content preservation based on config
8. Applies max_messages limit
9. Strips multimodal data from older messages
10. Gets end prompt from `manager.get_end_prompt()`
11. Processes message injections from modules
12. Filters to approved keys only
13. Enforces turn order with spacers
14. Counts tokens and trims if over limit (binary search)
15. Checks if system+end prompts alone exceed limit

**Token Trimming Process:**
1. Calculates current token count (tools + context)
2. Leaves 5% buffer below max
3. Reserves tokens for last user message
4. Uses binary search to find optimal trim point
5. Trims from the front of history (keeps system and end prompts)

#### `async get_size()`

Returns a detailed breakdown of the current context size, as raw data only.
Formatting (units, separators, layout) is the responsibility of the consumer
(`/status`, the webUI context popup, etc).

**Returns:**
- Dict of raw numbers:
  - `max_context`: configured context window size
  - `total_tokens`: tokens currently in the window
  - `percent_full`: `total_tokens` as a percentage of `max_context`
  - `total_words`: word count across all parts
  - `system_prompt`: `{tokens, words}`
  - `tools`: `{active, tokens, words}`
  - `message_history`: `{tokens, words}`
  - `end_prompt`: `{tokens, words}`

**Note:** Uses `self.get()` for dynamic trimming, not raw message history.

#### `async get_total_tokens(trim=True)`

Returns the total token count of the context plus tools array. Prefers the
API's own reported `prompt_tokens` (cached in the chat's metadata, plus a
character-based estimate for any messages added since that measurement), and
falls back to the estimate alone for APIs that don't report usage.

**Returns:**
- Integer token count, or 0 if context is empty

#### `async count_tokens(data)`

Counts tokens in any data structure.

**Parameters:**
- `data` - Any data (list of messages, dict, string, etc.)

**Returns:**
- Integer token count

**Behavior:**
1. If data is a list (likely messages):
   - Strips non-text content from messages (multimodal content doesn't count)
   - Converts to JSON string
2. Otherwise:
   - Converts to JSON string
3. Counts characters and divides by 4 (1 token ≈ 4 characters)

**Note:** This is a simplified character-based estimator, not a real tokenizer. Multimodal content is exempt from token limits.

#### `_count_text_tokens(text)`

Counts tokens by counting characters.

**Parameters:**
- `text` (str) - The text to count

**Returns:**
- Integer token count (len(text) // 4)

## The `SUMMARIZATION_CUTOFF` Signal

A special internal message type used to mark a point in chat history for summarization:

```python
{"_metadata": {"signal": "SUMMARIZATION_CUTOFF"}}
```

**Behavior in `get()`:**
1. Searches backwards through messages for the last cutoff signal
2. If found, replaces all messages before it with:
   ```python
   [{"role": "user", "content": "Summarize our chat so far."}]
   ```
3. Returns only messages after the cutoff point

**Use Case:** Enables chat summarization without losing the user-facing end of chat history. When combined with a summarization module, old conversation parts can be summarized while keeping recent messages intact.

## The Prompt Structure

The final prompt sent to the AI looks conceptually like this:

```json
[
  {"role": "system"|"developer", "content": "...[System Prompt from Modules]..."},
  {"role": "user", "content": "...[User Message 1]\n\n[injection content]..."},
  {"role": "assistant", "content": "...[Assistant Response 1]..."},
  {"role": "tool", "tool_call_id": "...", "content": "..."},
  {"role": "assistant", "content": "...[Tool response handling]..."},
  {"role": "user", "content": "...[User Message 2]..."},
  {"role": "developer"|"user", "content": "...[End Prompt from Modules]..."}
]
```

**Notes:**
- System role is `"system"` by default, or `"developer"` if `api.use_developer_role` is True
- End prompt role follows the same pattern (developer if supported, otherwise user)
- Injection content is appended directly to user message content
- Spacer messages (`" "`) may be inserted between consecutive same-role messages
- Approved keys only: `role`, `content`, `reasoning_content`, `tool_calls`, `tool_call_id`, `function_call`, `tool`

## Configuration Dependencies

| Config Key | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `api.max_messages` | int | 200 | Maximum history messages to keep. Applied before token trimming. |
| `api.max_context` | int | 8192 | Maximum total context size in tokens. |
| `model.keep_reasoning_in_context` | bool | True | If False, strips `reasoning_content` from all messages. |
| `model.only_preserve_reasoning_for_current_agentic_loop` | bool | True | If True, only preserves reasoning in current agentic loop. |
| `api.use_developer_role` | bool | False | If True, uses `"developer"` role for system/end prompts. |

## Agentic Loop Reasoning Preservation

When `only_preserve_reasoning_for_current_agentic_loop` is True:
- The channel tracks `agentic_loop_start` (message index where current loop began)
- Reasoning is stripped from messages before this index (unless they have tool calls)
- This saves significant context tokens during complex tool-calling chains

## Best Practices

1. **Use `get()` for API requests** - Handles all trimming and validation
2. **Use `get_size()` for status display** - Provides detailed breakdown
3. **Check return value of `get()`** - May return `APIError` or `None` on connection failure
4. **Respect the 5% buffer** - Binary search leaves room for API overhead
5. **Multimodal content is stripped from history** - Only the last message keeps full multimodal data
