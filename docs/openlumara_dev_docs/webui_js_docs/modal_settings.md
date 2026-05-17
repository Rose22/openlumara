# modal_settings.js Documentation

`modal_settings.js` is the core engine for the Settings interface. It manages loading, organizing, and saving user preferences, including theme, API, and module configurations.

## Core Functionality

### Settings Lifecycle
- `loadSettings()`: Fetches settings from `/settings/load`.
  - Attempts to load module info and model lists from the API.
  - If the server is unreachable, it falls back to using data from `settingsData` (the local cache).
  - Organizes the raw data into a structured category-based object.
  - Triggers the rendering of the settings form and navigation.
- `saveSettings()`: Sends the current `settingsData` to `/settings/save`.
  - Detects if changes require a server restart (e.g., module or channel changes).
  - Handles error reporting and provides feedback (success/error/restart).
- `resetSettingsForm()`: Reverts all unsaved changes to the original values stored in `settingsOriginal`.

### Organization & Parsing
- `organizeSettingsIntoCategories(originalData, moduleInfo)`: Transforms the flat settings object into a hierarchical structure optimized for the UI.
  - Groups settings by top-level keys (e.g., `api`, `appearance`).
  - Handles complex structures like `modules` and `channels` by parsing their nested settings and enabled/disabled lists.
  - Implements "direct" groups for items that don't belong to a sub-category.
- `flattenSettingsObject(obj, prefix, schema, callback)`: Recursively flattens a settings object into dot-notation keys (e.g., `modules.my_module.settings.param`).

### UI Component Creation (Dynamic Inputs)
The `createSettingItem` function acts as a factory, generating the appropriate input element based on the detected or specified type:
- **`reasoning_effort_slider`**: A slider for AI reasoning effort.
- **`model`**: A dropdown for selecting AI models (with a refresh button).
- **`toggle_list`**: A grid of switches for enabling/disabling modules or channels.
- **`boolean`**: A standard toggle switch.
- **`number`**: A numeric input.
- **`textarea`**: A multi-line text area.
- **`select`**: A dropdown menu with dynamic description updates.
- **`slider`**: A standard numeric slider.
- **`percentage`**: A specialized slider for 0-100% values.

### Theme & Appearance
- `applyTheme(family, mode)`: Applies a specific color theme and dark/light mode to the document.
- `createThemeSection()`: Builds the typography, sound, and color theme controls.
- `createFontFamilyDropdown(...)`: A custom-built dropdown for selecting fonts, including Google Font loading and previewing.

## State Management
- `settingsData`: The current working copy of user settings.
- `settingsOriginal`: A deep copy of the settings as they were when last loaded or saved.
- `settingsHasChanges`: A boolean flag indicating if the current state differs from the original.
- `moduleInfoCache`: A cache of module descriptions and safety statuses.
