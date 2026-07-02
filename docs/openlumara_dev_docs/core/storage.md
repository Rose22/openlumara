# Core: The Storage System (`core.storage`)

The `storage` module provides a robust and flexible way to persist data to the local file system. Instead of standard Python dictionaries and lists, OpenLumara uses specialized classes that automatically handle serialization and deserialization.

## Supported Formats

The storage system supports several data formats, allowing developers to choose the best one for their needs:

- **JSON (`json`)**: The default format. Great for structured, human-readable data. Used for chat storage.
- **YAML (`yaml`)**: Excellent for configuration files and human-editable data. Used for `config.yml`.
- **MessagePack (`msgpack`)**: A high-performance, binary format. Ideal for large datasets or when speed and storage efficiency are priorities (e.g., `save.msgpack` for persistent state).
- **Text (`text`)**: Simple line-separated text files.
- **Markdown (`markdown`)**: A unique, hierarchical storage format where nested dictionary keys are mapped to a directory/file structure (e.g., `{"ideas": {"topic": "text"}}` becomes `ideas/topic.md`).

## Key Classes

### `StorageList`
A subclass of the standard Python `list`. It behaves like a list but automatically saves its contents to a file whenever changes are made or when explicitly told to.

**Methods**:
| Method | Description |
| :--- | :--- |
| `save()` | Writes the list contents to disk. |
| `load()` | Reads the file and populates the list. |
| `get()` | Returns the full list contents. |
| `_write()` | Internal: serializes and writes to file. |
| `_read()` | Internal: reads and deserializes from file. |
| `_file_changed()` | Internal: checks if the file was modified externally. |
| `_update_mtime()` | Internal: tracks the file's last modification time. |

**Common Use Case**: Storing chat histories (`{channel}_chats.json`).

### `StorageDict`
A subclass of the standard Python `dict`. It behaves like a dictionary but handles persistence.

**Methods**:
| Method | Description |
| :--- | :--- |
| `save()` | Writes the dict contents to disk. |
| `load()` | Reads the file and populates the dict. |
| `get()` | Returns the full dict contents. |
| `__getitem__(key)` | Bracket access: `dict["key"]`. Raises `KeyError` if not found. |
| `__setitem__(key, value)` | Bracket assignment: `dict["key"] = value`. Auto-saves. |
| `__contains__(key)` | Membership test: `"key" in dict`. |
| `_write()` | Internal: serializes and writes to file. |
| `_read()` | Internal: reads and deserializes from file. |
| `_file_changed()` | Internal: checks if the file was modified externally. |
| `_update_mtime()` | Internal: tracks the file's last modification time. |
| `_parse_nested_keys(key)` | Internal: parses markdown-style nested keys (`a/b/c`). |
| `_flatten_nested_keys(data)` | Internal: flattens nested dicts for markdown storage. |
| `_delete_nested_key(key)` | Internal: deletes a nested key in markdown storage. |

**Common Use Case**: Storing configuration (`config.yml`), saved data (`save.msgpack`), and module configs.

**Advanced Feature: Hierarchical Markdown Storage**
When using the `markdown` type, `StorageDict` can represent nested structures as actual files and folders on your disk.
- A key like `project/module/settings` will be saved as `project/module/settings.md`.
- This makes it incredibly easy to browse and edit your agent's knowledge or configuration using any standard text editor.

### `StorageText`
A simple class for managing a single string of text in a file.

**Methods**:
| Method | Description |
| :--- | :--- |
| `set(value)` | Sets the text content and saves. |
| `get()` | Returns the current text. |
| `load()` | Reads the file and populates the text. |
| `save()` | Writes the text to disk. |
| `__str__()` | Returns the current text content. |
| `_write()` | Internal: writes text to file. |
| `_read()` | Internal: reads text from file. |
| `_file_changed()` | Internal: checks if the file was modified externally. |
| `_update_mtime()` | Internal: tracks the file's last modification time. |

**Common Use Case**: Storing a single long-form text block, like a system prompt or a single note.

## Usage Example

```python
import core

# Using StorageDict with JSON
config = core.storage.StorageDict("my_config", "json")
config["theme"] = "dark"
config["volume"] = 0.8
config.save()

# Using StorageList with MessagePack (efficient)
chat_history = core.storage.StorageList("history", "msgpack")
chat_history.append({"role": "user", "content": "Hello!"})
chat_history.save()

# Using Hierarchical Markdown
knowledge = core.storage.StorageDict("knowledge", "markdown")
knowledge["science/physics/gravity"] = "Gravity is a force..."
knowledge.save() 
# This creates: knowledge/science/physics/gravity.md
```

## Constructor Parameters

All storage classes accept:
| Parameter | Type | Description |
| :--- | :--- | :--- |
| `name` | `str` | The base filename (without extension). |
| `format` | `str` | The storage format (`json`, `yaml`, `msgpack`, `text`, `markdown`). |
| `path` | `str` | Optional: The directory to save in. Defaults to the project root. |
| `autoload` | `bool` | If `True` (default), loads from disk on instantiation. |
| `override_temporary` | `bool` | If `True`, loads from disk even if the file is temporary (used by config). |
