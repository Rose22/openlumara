# Core: The Storage System (`core.storage`)

The `storage` module provides a robust and flexible way to persist data to the local file system. Instead of standard Python dictionaries and lists, OpenLumara uses specialized classes that automatically handle serialization and deserialization.

## Supported Formats

The storage system supports several data formats, allowing developers to choose the best one for their needs:

- **JSON (`json`)**: The default format. Great for structured, human-readable data.
- **YAML (`yaml`)**: Excellent for configuration files and human-editable data.
- **MessagePack (`msgpack`)**: A high-performance, binary format. Ideal for large datasets or when speed and storage efficiency are priorities (e.g., chat history).
- **Text (`text`)**: Simple line-separated text files.
- **Markdown (`markdown`)**: A unique, hierarchical storage format where nested dictionary keys are mapped to a directory/file structure (e.g., `{"ideas": {"topic": "text"}}` becomes `ideas/topic.md`).

## Key Classes

### `StorageList`
A subclass of the standard Python `list`. It behaves like a list but automatically saves its contents to a file whenever changes are made or when explicitly told to.

**Common Use Case**: Storing a simple list of strings or a list of dictionaries.

### `StorageDict`
A subclass of the standard Python `dict`. It behaves like a dictionary but handles persistence.

**Common Use Case**: Storing configuration settings, user profiles, or complex metadata.

**Advanced Feature: Hierarchical Markdown Storage**
When using the `markdown` type, `StorageDict` can represent nested structures as actual files and folders on your disk.
- A key like `project/module/settings` will be saved as `project/module/settings.md`.
- This makes it incredibly easy to browse and edit your agent's knowledge or configuration using any standard text editor.

### `StorageText`
A simple class for managing a single string of text in a file.

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

## Automatic Loading and Reloading

- **`autoload`**: If set to `True` (default), the class will automatically load its content from the file system upon instantiation.
- **`autoreload`**: If set to `True`, the class will re-read the file from disk every time a `get()` operation is performed. This is useful if external processes might be modifying the files.
