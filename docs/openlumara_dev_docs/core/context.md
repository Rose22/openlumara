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
- **History Trimming**: If the prompt is too large, it removes the oldest messages from the history (middle-out trimming) until the prompt fits within the allowed limit (with a 5% safety buffer).
- **Multimodal Optimization**: To save tokens, it strips non-text content (like images) from all messages in the history except for the most recent one.

### 3. Role and Turn Management
The `Context` ensures the conversation follows the required turn order (e.g., `system` -> `user` -> `assistant` -> `user`). It also:
- **Merges Consecutive Messages**: Merges consecutive assistant messages into a single block to reduce overhead.
- **Removes Ghost Messages**: Filters out messages marked as "ghost" (messages that are invisible to the AI).
- **Handles Reasoning Content**: Manages whether reasoning/thinking tokens should be kept in the context or stripped out.

## Key Methods

| Method | Description |
| :--- | :--- |
| `get(system_prompt=True, end_prompt=True)` | Builds and returns the full list of message dictionaries to be sent to the API. |
| `get_size()` | Returns a detailed breakdown of the current context size in both tokens and words. |
| `get_token_usage()` | Returns the current token usage (either from API data or local estimation). |
| `count_tokens(messages)` | Calculates the token count of a specific list of messages. |

## The Prompt Structure

The final prompt sent to the AI looks conceptually like this:

```json
[
  {"role": "system", "content": "...[System Prompt from Modules]..."},
  {"role": "user", "content": "...[User Message 1]..."},
  {"role": "assistant", "content": "...[Assistant Response 1]..."},
  {"role": "user", "content": "...[User Message 2]..."},
  {"role": "developer", "content": "...[End Prompt from Modules]..."}
]
```
*(Note: The role for the end prompt may be `developer` or `user` depending on the API's support.)*
