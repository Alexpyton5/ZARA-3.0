# API Skills in Hermes Agent

## Overview

Skills in Hermes Agent are reusable procedures that the agent can learn from experience and load into future sessions. They are the primary way to extend the agent's capabilities without modifying the core.

## Skill Structure

A skill consists of:
- A `SKILL.md` file with YAML frontmatter and markdown body
- Optional referenced files (references/, templates/, scripts/)

### SKILL.md Format

```yaml
---
name: skill-name
description: "Brief description of what the skill does"
version: 1.0.0
author: Your Name
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [tag1, tag2]
    homepage: https://example.com
    related_skills: [related-skill]
---
```

## Built-in Skills

Hermes Agent comes with built-in skills organized by category:
- `autonomous-ai-agents`: Skills for spawning and orchestrating AI agents
- `creative`: ASCII art, diagrams, design tools
- `devops`: SDLC review
- `email`: Email management
- `github`: GitHub workflow
- `media`: GIF search, YouTube transcripts
- `mlops`: HuggingFace, Weights & Biases, llama.cpp
- `note-taking`: Obsidian
- `productivity`: Airtable, Box, Google Workspace, etc.
- `research`: arXiv, blocked page recovery, blog watcher
- `smart-home`: Philips Hue
- `social-media`: Twitter/X, LinkedIn, etc.
- `software-development`: Code review, testing, debugging

## Using Skills

### Listing Skills

```bash
hermes skills list
```

### Browsing Skills

```bash
hermes skills browse
```

### Searching Skills

```bash
hermes skills search <query>
```

### Installing Skills

From the Hermes Skill Hub:
```bash
hermes skills install <skill-id>
```

From a direct URL:
```bash
hermes skills install https://example.com/skill.md
```

### Enabling/Disabling Skills

```bash
hermes tools enable <skill-name>
hermes tools disable <skill-name>
```

## Creating Skills

### Skill Development Process

1. Identify a recurring task that would benefit from automation
2. Develop the procedure manually first
3. Extract the exact commands and steps
4. Create the skill following the template below
5. Test the skill in isolation
6. Share or publish the skill

### Skill Template

Create a directory for your skill in `~/.hermes/skills/`:
```
~/.hermes/skills/
└── my-skill/
    ├── SKILL.md
    ├── references/
    │   └── api.md
    ├── templates/
    │   └── config.yaml
    └── scripts/
        └── validate.py
```

### SKILL.md Requirements

- Must have valid YAML frontmatter
- Must include a markdown body with:
  - Trigger condition (when to use the skill)
  - Numbered steps with exact commands
  - Pitfalls section
  - Verification steps

### Example: hello-world Skill

```yaml
---
name: hello-world
description: "Says hello in multiple languages"
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
---
```

# Hello World Skill

## Use when
You need to greet someone in multiple languages.

## Steps

1. Run the following command to see available languages:
   ```bash
   hermes chat -q "List 5 ways to say hello in different languages"
   ```

2. Choose the languages you want to use

3. Run:
   ```bash
   hermes chat -q "Say hello in French, Spanish, and Japanese"
   ```

## Pitfalls
- The skill relies on the agent's language capabilities
- Some languages may not be supported by the underlying LLM

## Verification
- Verify that the output contains greetings in the requested languages
- Check that the pronunciation guides are included if requested
```

## Skill Management

### Updating Skills

```bash
hermes skills update <skill-id>
```

### Uninstalling Skills

```bash
hermes skills uninstall <skill-id>
```

### Publishing Skills

To share your skill with others:
1. Publish the skill to a GitHub repository
2. Share the raw URL to the SKILL.md file
3. Others can install it with `hermes skills install <url>`

## Skill Storage

- Built-in skills: `~/.hermes/hermes-agent/skills/`
- User-installed skills: `~/.hermes/skills/`
- Project-local skills: `./.hermes/skills/` (when `HERMES_ENABLE_PROJECT_PLUGINS` is set)
- Pip-installed skills: Available through Python entry points

## Configuration

Skills can be configured via:
- `hermes skills config` - Interactive configuration
- Direct editing of `~/.hermes/config.yaml` under the `skills` section

## Best Practices

1. Keep skills focused on a single task
2. Use exact commands and specify versions when needed
3. Include error handling and verification steps
4. Document pitfalls and limitations
5. Test skills in isolation before sharing
6. Follow the existing skill naming conventions
7. Use the skill's metadata to help users discover it

## Troubleshooting

### Skill Not Found

1. Run `hermes skills list` to verify the skill is installed
2. Check that you're using the correct skill name or ID
3. Ensure the skill is enabled for your current platform

### Skill Not Working

1. Check the skill's requirements and dependencies
2. Verify that any required API keys or tokens are configured
3. Look at the skill's references and templates for additional setup
4. Try running the skill's steps manually to isolate the issue

## References

- [Skills Catalog](https://hermes-agent.nousresearch.com/docs/reference/skills-catalog)
- [Contributor Guide](https://hermes-agent.nousresearch.com/docs/reference/contributor-guide)
- [CLI Reference: Skills](https://hermes-agent.nousresearch.com/docs/reference/cli-commands#skills)