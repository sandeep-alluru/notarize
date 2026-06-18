"""MCP server for notarize.

Start:  python -m notarize.mcp_server
Or:     notarize-mcp

Add to Claude Desktop (~/.config/claude/claude_desktop_config.json):
    {
        "mcpServers": {
            "notarize": {
                "command": "notarize-mcp"
            }
        }
    }
"""

from __future__ import annotations

import json
import sys
from typing import Any


def _require_mcp() -> Any:
    try:
        import mcp.server.stdio
        import mcp.types as types
        from mcp.server import Server

        return mcp, types, Server
    except ImportError:
        print(
            "MCP server requires: pip install 'notarize[mcp]'",
            file=sys.stderr,
        )
        sys.exit(1)


def run_server() -> None:
    """Start the MCP server on stdio."""
    mcp_mod, types, server_cls = _require_mcp()

    server = server_cls("notarize")

    @server.list_tools()
    async def list_tools() -> list[types.Tool]:
        return [
            types.Tool(
                name="verify_trace",
                description=(
                    "Verify an AgentTrace JSON dict for internal consistency. "
                    "Returns a VerificationResult with verdict and check details."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "trace": {
                            "type": "object",
                            "description": "AgentTrace as a JSON-compatible dict.",
                        },
                    },
                    "required": ["trace"],
                },
            ),
            types.Tool(
                name="scrub_trace",
                description=(
                    "Scrub PII from an AgentTrace. "
                    "Replaces emails, phone numbers, credit cards, SSNs, and IPs."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "trace": {
                            "type": "object",
                            "description": "AgentTrace as a JSON-compatible dict.",
                        },
                    },
                    "required": ["trace"],
                },
            ),
            types.Tool(
                name="list_traces",
                description="List all stored AgentTraces from the notarize database.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "db": {
                            "type": "string",
                            "description": "Path to the notarize database.",
                        },
                    },
                    "required": [],
                },
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[types.TextContent]:
        from notarize.scrubber import PrivacyScrubber
        from notarize.store import TraceStore
        from notarize.trace import AgentTrace
        from notarize.verifier import ConsistencyVerifier

        if name == "verify_trace":
            trace = AgentTrace.from_dict(arguments["trace"])
            verifier = ConsistencyVerifier()
            result = verifier.verify(trace)
            return [types.TextContent(type="text", text=json.dumps(result.to_dict(), indent=2))]

        if name == "scrub_trace":
            trace = AgentTrace.from_dict(arguments["trace"])
            scrubber = PrivacyScrubber()
            scrub_result = scrubber.scrub(trace)
            return [
                types.TextContent(
                    type="text",
                    text=json.dumps(
                        {
                            "original_trace_id": scrub_result.original_trace_id,
                            "scrubbed_trace": scrub_result.scrubbed_trace.to_dict(),
                            "replacements_count": scrub_result.replacements_count,
                            "patterns_matched": scrub_result.patterns_matched,
                        },
                        indent=2,
                    ),
                )
            ]

        if name == "list_traces":
            db = arguments.get("db", ".notarize/traces.db")
            with TraceStore(db) as store:
                traces = store.list_traces()
            return [
                types.TextContent(
                    type="text",
                    text=json.dumps([t.to_dict() for t in traces], indent=2),
                )
            ]

        raise ValueError(f"Unknown tool: {name}")

    import asyncio

    async def _main() -> None:
        async with mcp_mod.server.stdio.stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())

    asyncio.run(_main())


if __name__ == "__main__":
    run_server()
