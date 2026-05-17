# Commands & Settings 🛠️

Want to take control of OpenLumara? You can use special commands to change settings or control the system on the fly!

Most commands start with a `/` (like `/help`).

### Useful Commands:

- **`/help`**: Shows you a list of all the commands you can use. It's the best place to start!
- **`/status`**: Tells you how the AI is doing and how much 'memory' (context) it's using.
- **`/new`**: Want to start fresh? This starts a brand new chat session.
- **`/chat <ID>`**: Want to go back to an old conversation? Use this to load a chat from your history.
- **`/restart`**: If things feel a bit slow, this will restart the OpenLumara server.

### Customizing Your Experience ⚙️

OpenLumara is designed to be highly customizable. All your settings are stored in a file called `config.yml`. 

The system is smart: when you add new 'tools' (modules), it automatically adds their settings to your configuration file for you. You can change almost everything—from which AI model you use to how your different channels (like Telegram or Discord) behave.

**Pro Tip:** Use the `/config` command to make changes quickly, or use the Web UI for a more visual way to manage your settings! ✨

# Using the `/config` Command

The `/config` command allows you to view and modify the system configuration directly from your chat interface.

## Syntax

### Viewing Configuration (GET)
To view a specific configuration value or a group of settings:
`/config <path>`

- **Root level**: `/config` lists all top-level configuration categories.
- **Nested path**: `/config <category> <key>` retrieves the value at that path.
- **Settings groups**: If you point to a category that contains settings, it will list the available settings and their descriptions.

### Modifying Configuration (SET)
To update a configuration value:
`/config <path> <value>`

- The `<path>` should point to the specific key you wish to change.
- The `<value>` will be automatically converted to its appropriate type (boolean, integer, float, or string).
- **Warning**: You cannot overwrite a settings group (a dictionary of settings) with a single value.

## Examples

### Get all top-level categories
`/config`

### Get a specific value
`/config core cmd_prefix`

### Set a specific value
`/config core cmd_prefix !`

### View available settings for the Discord channel
`/config channels discord`

### Toggle a boolean setting
`/config modules coder allow_code_execution true`

### Set a numeric limit
`/config modules sandboxed_shell memory_limit 512m`

## Important Notes
- Changes are persisted automatically to the `config.yml` file.
- Be careful when modifying core settings, as incorrect values might require a server restart or could affect system stability.
- Type conversion is handled automatically (e.g., `true` becomes a boolean `True`).
