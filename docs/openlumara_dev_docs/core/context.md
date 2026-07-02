# Core: The Context System (`core.Context`)

The `Context` class is responsible for building the complete "view" of the conversation that is sent to the AI. It manages the logic of how message history, system prompts, and end-prompts are combined to create a coherent prompt while staying within token limits.

## Responsibilities

### 1. Prompt Assembly
The `Context` ensures that the prompt sent to the AI follows a strict and logical order:
1.  **System Prompt**: The foundational instructions (e.g., identity, rules) provided by the `Manager` and various `Modules`.
2.  **Message History**: The actual conversation between the user and the assistant.
3.  **End Prompt**: Dynamic information (like the current time) that is appended to the very end of the context to ensure the AI has the most up-to-date information without needing to reprocess the entire history.

### 2. Token Management and Trimming
To prevent exceeding the AI model's context window, the `Context` performs several optimization and trimming tasks:
- **Token Counting**: It calculates the total token count of the assembled prompt using `tiktoken`.
- **Binary Search Trimming**: If the prompt is too large, it uses **binary search** to efficiently find the minimum number of messages to remove from the front until the prompt fits within the allowed limit (with a 5% safety buffer).
- **Max Messages Limit**: Before token trimming, applies a `max_messages` limit (default 200) to history — keeps the most recent N messages.
- **Multimodal Optimization**: To save tokens, it strips non-text content (like images) from all messages in the history except for the most recent one. Stripped multimedia is replaced with `"[multimedia content]"`.

### 3. Role and Turn Management
The `Context` ensures the conversation follows the required turn order (e.g., `system` -> `user` -> `assistant` -> `user`). It also:
- **Merges Consecutive Messages**: Inserts spacer messages (`" "`) between consecutive assistant messages or consecutive user messages to maintain valid turn order. Note: `assistant -> tool -> assistant` is valid and not modified.
- **Removes Ghost Messages**: Filters out messages marked as "ghost" (messages that are invisible to the AI).
- **Removes Signal Messages**: Filters out internal signal messages (like `SUMMARIZATION_CUTOFF`).
- **Handles Reasoning Content**: Manages whether reasoning/thinking tokens should be kept in the context or stripped out, based on `keep_reasoning_in_context` and `only_preserve_reasoning_for_current_agentic_loop` config options.

### 4. Injection Processing
- **Module Message Injection**: After assembling the prompt, iterates through messages and appends any `"injection"` field content to user messages under a `[SYSTEM MESSAGES]` header. The injection field is then removed for cleanliness.

### 5. Error Handling
- If the system prompt + end prompt alone exceed the maximum context size, the Context pushes an error message to the channel and disconnects the API to prevent spamming.

## Key Methods

| Method | Description |
| :--- | :--- |
| `get(system_prompt=True, end_prompt=True, history=True, prevent_recursion=False)` | Builds and returns the full list of message dictionaries to be sent to the API. Handles all trimming, injection, and turn-order enforcement. |
| `get_size()` | Returns a detailed breakdown of the current context size: system prompt (tokens/words), message history (tokens/words), end prompt (tokens/words), and total. |
| `get_token_usage()` | Returns the current token usage with `current` and `max` keys. Prefers API data if available, otherwise calculates locally. |

## The `SUMMARIZATION_CUTOFF` Signal

A special internal message type (`{"signal": "SUMMARIZATION_CUTOFF"}`) that serves as a cutoff point for context trimming. When found, `Context.get()` replaces all messages before it with `{"role": "user", "content": "Summarize our chat so far."}`. This enables chat summarization without losing the user-facing end of chat history.

## The Prompt Structure

The final prompt sent to the AI looks conceptually like this:

```json
[
  {"role": "system"|"developer", "content": "...[System Prompt from Modules]..."},
  {"role": "user", "content": "...[User Message 1]\n\n[SYSTEM MESSAGES]\n...[Injection]..."},
  {"role": "assistant", "content": "...[Assistant Response 1]..."},
  {"role": "user", "content": "...[User Message 2]..."},
  {"role": "developer"|"user", "content": "...[End Prompt from Modules]..."}
]
```

- The system role is `"system"` by default, or `"developer"` if `api.use_developer_role` is True.
- The end prompt role follows the same pattern.
- Injection content is appended to user messages after processing.
- Spacer messages (`" "`) may be inserted between consecutive same-role messages.

## Configuration Dependencies

| Config Key | Description |
| :--- | :--- |
| `api.max_messages` | Maximum number of history messages to keep (default: 200). Applied before token trimming. |
| `api.max_context` | Maximum total context size in tokens (default: 8192). |
| `model.keep_reasoning_in_context` | If False, strips `reasoning_content` from all messages. |
| `model.only_preserve_reasoning_for_current_agentic_loop` | If True, only preserves reasoning in messages from the current agentic loop onward. |
| `api.use_developer_role` | If True, uses `"developer"` role instead of `"system"`/`"developer"` for prompts. |
