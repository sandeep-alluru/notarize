# MCP / Claude Integration

tracemarket ships an MCP server that exposes its core operations as native Claude tools.

## Install

```bash
pip install "tracemarket[mcp]"
```

## Add to Claude Desktop

Edit `~/.config/claude/claude_desktop_config.json` (Linux) or
`~/Library/Application Support/Claude/claude_desktop_config.json` (macOS):

```json
{
  "mcpServers": {
    "tracemarket": {
      "command": "tracemarket-mcp"
    }
  }
}
```

## Claude Code slash commands

After cloning the repo, these project-level commands are available:

| Command | What it does |
|---|---|
| `/project:test` | Run test suite and report failures |
| `/project:pr-prep` | Run lint + types + tests + CHANGELOG check |
| `/project:release <version>` | Prepare a release |

## Smithery

tracemarket is listed on [smithery.ai](https://smithery.ai) — search for "tracemarket" to install with one click.
