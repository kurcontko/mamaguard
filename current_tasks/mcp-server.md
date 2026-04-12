# Task: Standalone MCP Server (mamaguard/mcp_server/)

**Claimed:** 2026-04-12T00:35:00Z
**Branch:** feat/mcp-server
**Worktree:** /workspace/mcp-server-worktree

## Description
Build `mamaguard/mcp_server/` exposing all 12 FHIR tools via MCP protocol.
Shares tool implementations with ADK agents. SHARP extension support.

## Files to touch
- mamaguard/mcp_server/__init__.py (new)
- mamaguard/mcp_server/server.py (new)
- mamaguard/mcp_server/context.py (new - SHARP context extraction)
- mamaguard/tests/test_mcp_server.py (new)
- requirements.txt (add mcp)
- PROGRESS.md
