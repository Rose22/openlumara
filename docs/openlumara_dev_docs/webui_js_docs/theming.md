# Documentation: `theming.js`

## Overview
`theming.js` manages the application's visual appearance by controlling CSS variable injection. It supports multiple "theme families," each with potential "dark" and "light" mode variants. It also handles dynamic font loading from Google Fonts to allow users to customize the typography.

## Core Concepts

### Theme Identification
Themes are identified by a unique ID string, typically following the pattern `mode-family` (e.g., `dark-ocean`, `light-ocean`).
- **Mode**: `dark` or `light`.
- **Family**: The name of the design system (e.g., `monochrome`, `ocean`, `sunset`).

### Theme State
The module tracks the current visual state using two global variables:
- `currentThemeFamily`: The current design system being used.
- `currentThemeMode`: The current brightness mode (`dark` or `light`).

## Primary Functions

### `applyTheme(family, mode)`
The central function for changing the application's appearance.
1. **Theme Resolution**: Attempts to find the specific `mode-family` combination. If the requested mode doesn't exist for a family, it falls back to the available mode.
2. **Variable Reset**: Resets all CSS variables to their `BASE_THEME_VARS` defaults to prevent "leaking" styles from previous themes.
3. **Variable Injection**: Iterates through the `vars` object of the selected theme and applies them to the `:root` element using `document.documentElement.style.setProperty`.
4. **Font Application**:
    - Checks `localStorage` for a user-selected font.
    - If found, calls `loadGoogleFont()` to inject the Google Fonts stylesheet.
    - Updates `--font-family` and `--code-font` CSS variables.
5. **Persistence**: Saves the chosen `family` and `mode` to `localStorage`.

### `loadTheme()`
Initializes the theme on application startup. It retrieves the saved `themeFamily` and `themeMode` from `localStorage` and applies them. If no saved theme is found, it defaults to `monochrome` in `dark` mode.

### `createThemeButtons()`
Dynamically generates the UI for the theme selection menu.
- It iterates through all available theme families.
- It creates a preview button for each family.
- **Badges**: Adds visual indicators to buttons:
    - `◐`: Indicates the theme family supports both light and dark modes.
    - `Aa`: Indicates the theme uses a custom Google Font.

### `loadGoogleFont(fontName, weights)`
Dynamically creates and appends a `<link>` element to the `<head>` to load a specific font from Google Fonts. It prevents duplicate loading by checking for an existing element ID.

## Helper Functions

| Function | Description |
| :--- | :--- |
| `parseThemeId(themeId)` | Splits a theme ID into its `mode` and `family` components. |
| `buildThemeId(family, mode)` | Reconstructs a theme ID from its components. |
| `getThemeFamilies()` | Scans the global `themes` object to group all available themes by their family name. |
| `applyThemeMode(mode)` | A convenience function to change only the brightness mode while keeping the current family. |
| `toggleThemeMode(isLight)` | Toggles the brightness mode. |

## CSS Integration
The module relies on the existence of a global `themes` object and a `BASE_THEME_VARS` object. It works by overriding CSS variables defined in the main stylesheet, allowing for a highly decoupled and performant styling system.
