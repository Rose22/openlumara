# Core: Exceptions (`core.exceptions`)

The `exceptions` module defines custom exception classes used throughout the OpenLumara framework.

## Exception Classes

### `DependencyMissing`
Raised when a required third-party library is not installed. Used by the auto-installer and module loading system.

```python
raise core.exceptions.DependencyMissing("numpy is required for this module")
```

### `UnauthorizedException`
Raised when trying to execute a command or action that requires authorization but the user lacks the necessary permissions. Used by the command system to restrict admin commands.

```python
raise core.exceptions.UnauthorizedException("You are not authorized to run admin commands.")
```

## Usage

Both exceptions are imported via `core.exceptions`:

```python
import core

# Raising an authorization error
if not user.is_admin:
    raise core.exceptions.UnauthorizedException("Admin access required")

# Raising a missing dependency
if not hasattr(sys, 'numpy'):
    raise core.exceptions.DependencyMissing("numpy")
```