# Configuration in Hermes Agent

## Overview

Hermes Agent uses a hierarchical configuration system that allows customization of behavior, appearance, and functionality through YAML files, environment variables, and runtime commands. The configuration is designed to be persistent across sessions while remaining flexible for experimentation.

## Configuration Sources

Hermes loads configuration from multiple sources in this order (later sources override earlier ones):

1. **Default Configuration** - Built-in defaults in the codebase
2. **Global Configuration File** - `~/.hermes/config.yaml` (or `$HERMES_HOME/config.yaml`)
3. **Environment Variables** - Variables prefixed with `HERMES_`
4. **Project Configuration** - `./.hermes/config.yaml` (when enabled)
5. **Runtime Overrides** - Command-line flags and runtime commands

### Configuration File Locations

- **User Configuration**: `~/.hermes/config.yaml` (primary configuration file)
- **Project Configuration**: `./.hermes/config.yaml` (optional, opt-in via `HERMES_ENABLE_PROJECT_CONFIG`)
- **Environment Variables**: `HERMES_CONFIG_*` or `HERMES_*` prefixed variables
- **Secrets**: `~/.hermes/.env` (for API keys and sensitive data only)

## Configuration Structure

The main configuration file (`config.yaml`) is organized into sections:

```yaml
# Core agent configuration
model:
  default: nous-hermes-2-7b  # Default model to use
  provider: nous             # Model provider (nous, openai, anthropic, etc.)
  base_url: https://api.nousresearch.com/v1  # API base URL
  api_key: sk-...            # API key (usually from .env)
  context_length: 4096       # Maximum context length

agent:
  max_turns: 90              # Maximum tool-calling iterations
  tool_use_enforcement: true # Whether to enforce tool usage
  service_tier: standard     # Service tier (standard, premium, etc.)
  verify_on_stop: true       # Verify state when stopping

terminal:
  backend: local             # Terminal backend (local/docker/ssh/modal/daytona/singularity)
  cwd: ~                     # Default working directory
  timeout: 180               # Command timeout in seconds

compression:
  enabled: true              # Enable context compression
  threshold: 0.50            # Compression trigger threshold
  target_ratio: 0.20         # Target compression ratio

display:
  skin: default              # UI skin/theme
  interface: cli             # Interface type (cli/tui)
  language: en               # Interface language
  show_reasoning: false      # Show model reasoning in responses
  show_cost: false           # Show token usage cost
  pet: none                  # Desktop pet mascot

approvals:
  mode: smart                # Approval mode (smart/manual/off)
  timeout: 300               # Approval timeout in seconds
  cron_mode: lazy            # How cron jobs handle approvals

stt:
  enabled: true              # Enable speech-to-text
  provider: local            # STT provider (local/groq/openai/mistral/elevenlabs/deepinfra)
  local:
    model: base              # Vosk model size (tiny/base/small/medium/large-v3)

tts:
  provider: edge             # TTS provider (edge/elevenlabs/openai/minimax/mistral/neutts/gemini/piper/kittentts/deepinfra/xai)

memory:
  memory_enabled: true       # Enable persistent memory
  user_profile_enabled: true # Store user-specific memories
  provider: honcho           # Memory provider (default/hindsight/honcho/mem0/etc.)
  write_approval: smart      # How to handle memory writes

security:
  redact_secrets: true       # Automatically redact secrets in logs/output
  tirith_enabled: true       # Enable Tirith security scanner
  website_blocklist: []      # List of blocked websites

delegation:
  model: nous-hermes-2-7b    # Model for delegated tasks
  provider: nous             # Provider for delegated tasks
  max_concurrent_children: 3 # Max parallel delegated tasks
  max_iterations: 50         # Max iterations for delegated agents
  max_spawn_depth: 1         # Max delegation depth (1 = no nested delegation)

checkpoints:
  enabled: true              # Enable filesystem checkpoints
  max_snapshots: 50          # Maximum checkpoints to keep

curator:
  enabled: true              # Enable automatic skill curation
  consolidate: false         # Whether to consolidate overlapping skills
  interval_hours: 24         # How often to run curation
  stale_after_days: 30       # When to consider skills stale
```

## Environment Variables

Hermes respects environment variables for configuration:

### Common Environment Variables
- `HERMES_CONFIG_YAML` - Path to custom config file
- `HERMES_PROFILE` - Which profile to use
- `HERMES_DISPLAY_INTERFACE` - Force cli or tui interface
- `HERMES_DISPLAY_SKIN` - Override UI skin
- `HERMES_MODEL` - Override default model
- `HERMES_PROVIDER` - Override default provider
- `HERMES_TERMINAL_BACKEND` - Override terminal backend
- `HERMES_TTS_PROVIDER` - Override TTS provider
- `HERMES_STT_PROVIDER` - Override STT provider

### Secret Environment Variables (should be in .env)
- `VOICE_TOOLS_OPENAI_KEY` - OpenAI API key for voice tools
- `ELEVENLABS_API_KEY` - ElevenLabs API key
- `MINIMAX_API_KEY` - MiniMax API key
- `MISTRAL_API_KEY` - Mistral API key
- `GOOGLE_API_KEY` - Google API key for Gemini/TTS
- `GROQ_API_KEY` - Groq API key
- `DEEPINFRA_API_KEY` - DeepInfra API key
- `HERMES_OAUTH_CLIENT_ID` - OAuth client ID
- `HERMES_OAUTH_CLIENT_SECRET` - OAuth client secret

### Platform-specific Variables
- `TELEGRAM_BOT_TOKEN` - Telegram bot token
- `DISCORD_BOT_TOKEN` - Discord bot token
- `SLACK_BOT_TOKEN` - Slack bot token
- And others for various platforms

## Configuration Commands

Hermes provides several commands for managing configuration:

### Interactive Setup Wizard
```bash
hermes setup          # Full interactive setup
hermes setup model    # Model/provider setup only
hermes setup tts      # TTS setup only
hermes setup terminal # Terminal setup only
```

### Configuration Inspection and Modification
```bash
hermes config show              # Show entire configuration
hermes config show model        # Show model section only
hermes config get model.provider # Get specific configuration value
hermes config set model.provider nous  # Set configuration value
hermes config unset model.provider     # Remove configuration value
hermes config edit              # Open configuration in editor
hermes config path              # Show path to config file
hermes config env-path          # Show path to .env file
hermes config check             # Check for missing sections from older configs
```

### Model and Provider Management
```bash
hermes model                    # Interactive model/provider picker
hermes model list               # List available models
hermes model show               # Show current model configuration
hermes fallback list            # Show fallback provider chain
hermes fallback add nous        # Add provider to fallback chain
hermes fallback remove nous     # Remove provider from fallback chain
```

### Credential Management
```bash
hermes auth                     # Interactive credential manager
hermes auth list                # List stored credentials
hermes auth add nous            # Add new credential
hermes auth remove nous 0       # Remove credential by provider and index
hermes auth reset nous          # Reset all credentials for provider
hermes auth status              # Show credential pool status
```

## Profiles

Hermes supports multiple independent configurations through profiles:

### Profile Management
```bash
hermes profile list             # List all profiles
hermes profile create work      # Create new profile (optional: --clone)
hermes profile use work         # Switch to a profile
hermes profile show work        # Show profile details
hermes profile rename work job  # Rename a profile
hermes profile delete work      # Delete a profile
hermes profile export work      # Export profile to file
hermes profile import file.yaml # Import profile from file
```

### Profile Structure
Each profile has its own isolated configuration directory:
```
~/.hermes/profiles/
├── default/
│   ├── config.yaml
│   ├── .env
│   ├── skills/
│   ├── plugins/
│   ├── memories/
│   └── state.db
├── work/
│   ├── config.yaml
│   ├── .env
│   ├── skills/
│   ├── plugins/
│   ├── memories/
│   └── state.db
└── personal/
    ├── config.yaml
    ├── .env
    ├── skills/
    ├── plugins/
    ├── memories/
    └── state.db
```

Profiles are activated with:
```bash
hermes --profile work
# or in config.yaml:
profile: work
```

## Configuration Validation

Hermes includes tools to validate and troubleshoot configuration:

### Doctor Command
```bash
hermes doctor                 # Run diagnostics and suggest fixes
hermes doctor --fix           # Automatically fix common issues
```

### Configuration Checking
```bash
hermes config check           # Check for missing sections from older configs
```

### Dependency Checking
The doctor command checks:
- Python version and dependencies
- Required system tools (ffmpeg, git, etc.)
- API connectivity to configured providers
- File permissions and directory accessibility
- Configuration syntax and validity

## Best Practices

### For Users
1. **Use the Setup Wizard** - Start with `hermes setup` for initial configuration
2. **Separate Secrets** - Keep API keys in `.env`, not in `config.yaml`
3. **Use Profiles** - Separate different use cases with profiles (work, personal, testing)
4. **Backup Configuration** - Periodically backup `~/.hermes/` directory
5. **Document Changes** - Keep track of why you changed specific settings
6. **Start with Defaults** - Begin with default settings and adjust as needed

### For Advanced Users
1. **Use Environment Variables** - For deployment automation and CI/CD
2. **Leverage Project Configuration** - For repository-specific settings
3. **Monitor Configuration Changes** - Use version control for `config.yaml`
4. **Understand Section Dependencies** - Some sections affect others (e.g., model affects available tools)
5. **Test Changes Safely** - Use one-shot mode to test configuration: `hermes -z "test command"`

### For Developers
1. **Follow Naming Conventions** - Use clear, consistent section and key names
2. **Provide Sensible Defaults** - Make configuration easy to start with
3. **Document Configuration Options** - Explain what each setting does
4. **Validate Configuration** - Add validation logic to prevent invalid combinations
5. **Consider Performance** - Some settings have performance implications

## Configuration Security

### Secrets Management
1. **Never Commit Secrets** - Add `.env` to `.gitignore`
2. **Use .env for Secrets Only** - `config.yaml` is for non-secret settings
3. **Leverage Secret Stores** - Integrate with Bitwarden, 1Password, etc. via Hermes secrets
4. **Rotate Regularly** - Change API keys and tokens periodically
5. **Limit Permissions** - Use scoped tokens with minimum necessary permissions

### Configuration Protection
1. **File Permissions** - Ensure config files are not world-readable
2. **Backup Encryption** - Consider encrypting backups of sensitive configuration
3. **Audit Changes** - Track who changed what and when in shared environments
4. **Immutable Infrastructure** - In deployment scenarios, consider read-only configuration

## Troubleshooting

### Configuration Not Loading
1. Check file permissions on `~/.hermes/config.yaml`
2. Verify YAML syntax is valid (use online YAML validator)
3. Look for errors in `~/.hermes/logs/agent.log`
4. Try starting with minimal configuration: `hermes --ignore-rules`
5. Check if `$HERMES_HOME` environment variable is pointing to the right place

### Invalid Configuration Values
1. Use `hermes config get` to verify current values
2. Check allowed values in documentation or command help
3. Ensure proper YAML formatting (quotes, indentation, etc.)
4. Verify that referenced files or directories exist
5. Check for type mismatches (string vs integer vs boolean)

### Conflicting Configuration
1. Remember the override order: defaults < config.yaml < env vars < runtime
2. Use `hermes config show` to see the final resolved configuration
3. Check for environment variables that might be overriding file settings
4. Look at project configuration if `HERMES_ENABLE_PROJECT_CONFIG` is set
5. Consider that some settings require restart to take effect

### Provider-specific Issues
1. Verify API keys are valid and have correct permissions
2. Check provider status pages for outages or rate limits
3. Ensure correct base URLs for self-hosted providers
4. Verify model names are exactly as expected by the provider
5. Check if required ports are open for local providers

## Advanced Configuration Topics

### Dynamic Configuration
Some configuration can be changed at runtime without restart:
- Skin/theme changes (`hermes skin set <key> <hex>`)
- Some display settings
- Certain tool enabling/disabling
- Approval mode changes

### Configuration Templates
Hermes includes template configurations for common use cases:
- `hermes config template minimal` - Minimal working configuration
- `hermes config template development` - Configuration for plugin development
- `hermes config template production` - Optimized for production use
- `hermes config template privacy` - Maximum privacy settings

### Configuration Migration
When upgrading Hermes:
1. Run `hermes config migrate` to update configuration format
2. Check `hermes config check` for deprecated sections
3. Review release notes for breaking changes
4. Test migrated configuration with `hermes doctor`
5. Keep backup of pre-migration configuration

## Reference Configuration

### Minimal Working Configuration
```yaml
model:
  provider: nous
  base_url: https://api.nousresearch.com/v1

agent:
  max_turns: 50

terminal:
  backend: local

display:
  interface: cli

memory:
  memory_enabled: true
```

### Development Configuration
```yaml
model:
  provider: nous
  max_turns: 100

agent:
  tool_use_enforcement: true
  verify_on_stop: true

terminal:
  backend: local
  pty: true

display:
  interface: cli
  show_reasoning: true
  show_cost: true

memory:
  memory_enabled: true
  write_approval: manual

security:
  redact_secrets: false  # For debugging
```

### Production Configuration
```yaml
model:
  provider: nous
  service_tier: premium
  max_turns: 150

agent:
  tool_use_enforcement: true
  verify_on_stop: true

terminal:
  backend: ssh  # or modal/daytona for cloud
  timeout: 300

display:
  interface: cli
  show_reasoning: false
  show_cost: true

memory:
  memory_enabled: true
  user_profile_enabled: true
  provider: honcho
  write_approval: smart

security:
  redact_secrets: true
  tirith_enabled: true

delegation:
  max_concurrent_children: 5
  max_spawn_depth: 2

checkpoints:
  enabled: true
  max_snapshots: 100

curator:
  enabled: true
  consolidate: true
  interval_hours: 12
```

## References

- [Configuration Documentation](https://hermes-agent.nousresearch.com/docs/user-guide/configuration)
- [Environment Variables Reference](https://hermes-agent.nousresearch.com/docs/reference/environment-variables)
- [CLI Reference: Configuration Commands](https://hermes-agent.nousresearch.com/docs/reference/cli-commands#configuration)
- [Profiles Documentation](https://hermes-agent.nousresearch.com/docs/user-guide/features/profiles)
- [Doctor Command Documentation](https://hermes-agent.nousresearch.com/docs/user-guide/features/doctor)
- [Secret Management Documentation](https://hermes-agent.nousresearch.com/docs/user-guide/features/secrets)