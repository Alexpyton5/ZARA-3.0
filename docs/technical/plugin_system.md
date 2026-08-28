# Plugin System in ZARA 3.0

## Overview

ZARA 3.0 employs a plugin system that extends functionality without modifying the core. This design keeps the agent's core narrow and efficient while allowing extensive customization at the edges through self-contained modules.

## Plugin Architecture

Plugins in ZARA are self-contained modules that add specific capabilities to the agent. They follow a standardized structure and are loaded at runtime.

### Supported Plugin Types

ZARA supports several types of plugins:
1. **Platform Plugins** - Add support for new messaging platforms (Telegram, Discord, etc.)
2. **Memory Providers** - Different backends for persistent memory storage
3. **Model Providers** - Integrations with various LLM providers
4. **Desktop Plugins** - UI extensions for the Electron desktop app
5. **TUI Widgets** - Widget applications for the Ink terminal interface
6. **Image Generation** - Integrations with image generation APIs
7. **Video Generation** - Integrations with video generation APIs
8. **Observability** - Logging, metrics, and tracing extensions
9. **Security** - Enhanced security features and policies
10. **Productivity** - Integrations with productivity tools and services

## Plugin Structure

A typical plugin follows this directory structure:
```
plugin-name/
├── __init__.py          # Plugin initialization and registration
├── plugin.yaml          # Plugin metadata (optional)
├── references/          # Documentation and reference materials
├── scripts/             # Helper scripts
├── templates/           # Template files for configuration
└── [plugin-specific directories and files]
```

### __init__.py Requirements
The `__init__.py` file must:
1. Contain a `register(ctx)` function that registers the plugin's capabilities
2. Or contain a class that inherits from the appropriate base class
3. Handle plugin initialization and cleanup properly

### Plugin Metadata (plugin.yaml)
Optional YAML file with plugin information:
```yaml
name: plugin-name
description: "Brief description of what the plugin does"
version: 1.0.0
author: Plugin Author
license: MIT
website: https://example.com
repository: https://github.com/example/plugin
```

## Plugin Discovery and Loading

ZARA discovers plugins from multiple sources in this order:
1. **Bundled Plugins** - Shipped with ZARA (`hermes-agent/plugins/`)
2. **User Plugins** - Installed by the user (`~/.hermes/plugins/`)
3. **Project Plugins** - Local to a project (`./.hermes/plugins/` when `HERMES_ENABLE_PROJECT_PLUGINS` is set)
4. **Entry Point Plugins** - Installed via Python packages (`hermes_agent.plugins` entry points)

### Loading Precedence
When multiple plugins with the same name are found:
- Bundled plugins take precedence over user plugins
- User plugins take precedence over project plugins
- Project plugins take precedence over entry point plugins
- First-seen wins within each source type

## Plugin Registration

Plugins register their capabilities through the plugin context (`ctx`) passed to their `register` function. The context provides access to:

### Registration Methods

1. **Tool Registration** - Register new tools available to the agent
```python
ctx.register_tool(
    name="my_custom_tool",
    description="What the tool does",
    function=my_tool_function,
    input_schema={...}  # JSON Schema for parameters
)
```

2. **Slash Command Registration** - Register new slash commands
```python
ctx.register_slash_command(
    name="mycommand",
    description="What the command does",
    function=my_command_handler,
    aliases=[\"mc\", \"mycmd\"]
)
```

3. **Event Handler Registration** - Register for agent events
```python
ctx.register_event_handler(
    event_type="message_received",
    handler=my_event_handler
)
```

4. **Settings Registration** - Register configurable settings
```python
ctx.register_settings_section(
    section="myplugin",
    fields=[...]  # List of setting field definitions
)
```

5. **UI Component Registration** (for desktop/TUI plugins)
```python
ctx.register_ui_component(
    component_type="settings_panel",
    component=MySettingsPanel
)
```

## Status

**PRONTO** — Functional and tested as part of Fases 1-2. The plugin system enables extension of ZARA's capabilities without modifying core code.