# Core: The Chat System (`core.Chat`)

The `Chat` class is responsible for managing the lifecycle and persistence of individual chat sessions. It acts as the interface between the high-level `Context` and the low-level persistent storage.

## Responsibilities

### 1. Session Management
`Chat` manages a collection of chat sessions, allowing the user to:
- **Create New Chats**: Start fresh conversations with unique IDs and metadata.
- **Switch Chats**: Load existing chat histories by their ID.
- **Clear Chats**: Wipe the message history of the current session.
- **Delete Chats**: Permanently remove a chat session from storage.
- **Auto-Resume**: Automatically reload the last used chat session upon application startup (via a save file tracking the current index).

### 2. Message Persistence
Every message sent or received is stored within a chat session. `Chat` ensures that:
- **History is Maintained**: The sequence of user and assistant messages is preserved.
- **Metadata is Stored**: Titles, categories, tags, and custom metadata (like character info) are kept alongside the messages.
- **Efficient Storage**: Data is saved using efficient formats (like JSON) to ensure fast loading and low overhead.

### 3. Token Tracking
`Chat` tracks the token usage of the current conversation:
- **API-Provided Usage**: Whenever the API returns usage data, `Chat` updates its internal counter and sets `using_api_token_data = True`.
- **Local Estimation**: If the API does not provide usage data, `Chat` uses a local tokenizer (`tiktoken`) to estimate the number of tokens used in the current context. Falls back to character-based estimation (~4 chars/token) if tiktoken fails.

### 4. Data Integrity and Cleanup
`Chat` performs maintenance on the chat collection:
- **Automatic Title Generation**: When a new message is sent in a blank chat, it automatically generates a short title based on the message content (first 100 chars).
- **Cleanup on Init**: On construction, removes "empty" chats (no messages) and chats that only contain command/responses (detected via `_is_command_only()`).
- **Missing Metadata**: Automatically adds missing fields from `DEFAULT_DATA` to existing chats.

## Key Methods

### Session Management
| Method | Description |
| :--- | :--- |
| `new(category="general", title="", metadata={})` | Creates a new chat session with ULID-based ID, timestamps, and metadata. |
| `clear()` | Deletes all messages from the current chat and resets token usage. |
| `delete(id)` | Permanently removes a chat session by its ID. Adjusts current index if needed. |
| `load(id)` | Loads an existing chat session into the current context by ID. |
| `save()` | Saves the current chat data. Auto-creates a new chat if none is current. |

### Message Operations
| Method | Description |
| :--- | :--- |
| `get(index=None)` | Retrieves the full list of messages in the current chat. Auto-creates if none current. |
| `add(message, ghost=False)` | Appends a new message. Handles auto-title, ghost flagging, and module `on_message_inject()` injection (e.g., timestamps). |
| `pop(index=None)` | Removes a message at the given index (defaults to last). Returns new last index. |
| `set(messages)` | Overwrites the entire message history. Auto-creates if none current. |
| `delete_from(index)` | Deletes all messages from the given index onward (keeps up to and including the target). |
| `get_message(index)` | Returns a specific message by index. |
| `get_last_message_with_role(role, cutoff_index=None)` | Searches backwards for the last message with a given role. Useful for regenerating (targets the last user message before a cutoff). |

### Metadata Operations
| Method | Description |
| :--- | :--- |
| `get_title()` | Returns the current chat's title. |
| `set_title(title)` | Sets the current chat's title. |
| `get_category()` | Returns the current chat's category. |
| `set_category(category)` | Sets the current chat's category. |
| `get_categories()` | Collects and returns all unique categories across all chats. |
| `get_tags()` | Returns the current chat's tags list. |
| `set_tags(tags)` | Sets the current chat's tags (replaces all). |
| `add_tag(tag)` | Adds a single tag (if not already present). |
| `pop_tag(tag)` | Removes a single tag (if present). |
| `get_data(data_key=None)` | Returns custom_data dict, or a specific key's value. |
| `set_data(data_key, data_value)` | Sets a custom data key. |
| `get_all()` | Returns the full list of all chat sessions. |
| `get_id()` | Returns the current chat's ID string. |

### Token Operations
| Method | Description |
| :--- | :--- |
| `count_tokens(messages=None)` | Counts tokens using tiktoken (with model-aware encoding). Handles content, reasoning, tool calls, tool_call_ids, and names. Conservative counting: 3 tokens/message overhead + 1 for assistant priming. |
| `get_token_usage()` | Returns current token usage. Prioritizes API data if `using_api_token_data` is True, otherwise falls back to local counting. |
| `set_token_usage(usage)` | Sets the chat's token usage counter. |

### Internal Methods
| Method | Description |
| :--- | :--- |
| `_is_command_only(messages)` | Checks if a messages array contains only user commands and command responses (for cleanup). |
| `_set_current(index)` | Sets the current chat index and saves it to a file for auto-resume. |
| `_find_index(id)` | Finds the index of a chat by its ID string. |
| `_count_text_tokens(text)` | Helper to encode text using tiktoken or fall back to character-based estimation. |

## Instance Attributes

| Attribute | Type | Description |
| :--- | :--- | :--- |
| `data` | `StorageList` | The persistent list of all chat sessions for this channel. |
| `channel` | `Channel` | Reference to the owning channel. |
| `current` | `int \| None` | Index of the current chat session. `None` if no chat is loaded. |
| `current_save_path` | `str` | Path to the auto-resume file tracking the current chat index. |
| `using_api_token_data` | `bool` | Flag set to `True` when the API first provides token usage data. |
| `token_encoding` | `tiktoken.Encoding \| None` | The tiktoken encoder for the current model. |
| `model_name` | `str \| None` | The current model name (used to detect encoding changes). |

## `DEFAULT_DATA`

Each chat session starts with these defaults:
```python
{
    "title": "",
    "category": "general",
    "tags": [],
    "custom_data": {},
    "token_usage": 0
}
```

## Data Structure

A single chat session is represented as a dictionary:

```json
{
  "id": "8-char-ulid",
  "title": "Chat Title",
  "category": "general",
  "tags": ["tag1", "tag2"],
  "messages": [
    {"role": "user", "content": "Hello!"},
    {"role": "assistant", "content": "Hi there!"}
  ],
  "custom_data": {
    "character": "some_char_id"
  },
  "created": "ISO-timestamp",
  "updated": "ISO-timestamp",
  "token_usage": 1234
}
```

Ghost messages include `"ghost": true` and are filtered out by `Context.get()`. Injection messages include `"injection": "..."` and are processed by `Context` to append system messages to user content.
