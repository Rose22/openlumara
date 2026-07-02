# Core: Utility Functions (`core.functions`)

The `functions` module provides low-level utility functions for logging, error handling, and path management. These are called by other core modules during initialization and early startup, before the `Manager` instance is available.

## Key Functions

### Logging
| Function | Description |
| :--- | :--- |
| `log(category, msg)` | Simple console log. **WARNING**: Strictly for cases where the manager or channel instances cannot be accessed (e.g., during config loading). If the manager is available (`global_instance` exists), it delegates to the manager's logging. Otherwise, prints directly to stdout with `[CATEGORY]` prefix. |
| `log_error(msg, e)` | Console log for errors with full traceback. Same pre-manager caveat as `log()`. In debug mode, prints the full traceback; otherwise prints a compact error message. |

### Error Handling
| Function | Description |
| :--- | :--- |
| `detail_error(e)` | Provides more detail about an exception in a compact format. In debug mode, returns: `{exception} | {filename}, {function}, ln:{line}\n\n{full_traceback}`. In non-debug mode, returns just `str(e)`. |

### Path Management
| Function | Description |
| :--- | :--- |
| `get_path(path="")` | Gets a path relative to the project root directory. Returns the root path if no subpath is specified. The project root is determined as the parent directory of this module's file. |
| `get_data_path(subpath=None)` | Gets the path to the `data` directory (configured via `config.core.data_folder`, default `"data"`). Creates the directory if it doesn't exist. If `subpath` is provided, appends it. Resolves relative paths from the project root. |
| `sandbox_path(base_path, requested_path)` | **Security-critical**: Protects against path traversal attacks and symlink exploits. Validates the requested path is within `base_path`. Handles cross-platform path separators, URL decoding, and double-encoding attacks. Raises `ValueError` if the path escapes the sandbox or contains symlinks. |
| `validate_path_string(path)` | Validates a path string for traversal and encoding attacks. Strips separators, handles URL decoding (up to 3 levels), normalizes slashes, and checks for `..` and null bytes. |

### List Utilities
| Function | Description |
| :--- | :--- |
| `remove_duplicates(lst)` | Removes duplicates from a list while preserving order. |

## Security

The `sandbox_path()` and `validate_path_string()` functions are critical security defenses against path traversal attacks. They:
1. Strip path separators from the input.
2. Decode URL encoding (up to 3 levels to prevent double/triple encoding bypasses).
3. Normalize path separators for cross-platform compatibility.
4. Check for `..` components and null bytes.
5. Block symlinks at any level of the path.
6. Verify the resolved real path starts with the base path prefix.

## Usage Example

```python
import core

# Safe path resolution (prevents traversal attacks)
safe_path = core.sandbox_path("/project/data", "subdir/../file.txt")
# Returns: /project/data/file.txt

# Get data directory
data_dir = core.get_data_path()  # e.g., "/project/data"
chat_dir = core.get_data_path("chats")  # e.g., "/project/data/chats"

# Early logging (before manager is ready)
core.log("config", "Loading configuration...")
core.log_error("config failed", e)
```