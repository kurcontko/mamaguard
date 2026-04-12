# MamaGuard MCP Server -- Prompt Opinion Marketplace Setup

## Overview

The MCP server is MamaGuard's **second submission artifact** (Superpower track). It exposes all 14 FHIR tools via the Model Context Protocol, allowing any MCP client to invoke them. The BYO Agent is the primary artifact (Agent track); the MCP server provides the dual submission path.

## Prerequisites

1. MamaGuard repo cloned with dependencies installed (`pip install -r mamaguard/requirements.txt`)
2. Prompt Opinion account (free at https://promptopinion.ai)
3. A FHIR R4 server URL + bearer token (the PO workspace provides these via FHIR context)

## Option A: Attach MCP Server to a BYO Agent in PO

Prompt Opinion BYO Agents can attach MCP servers directly. This is the simplest path.

### 1. Run the MCP Server Locally (for testing)

```bash
cd mamaguard
python -m mamaguard.mcp_server.server          # stdio transport
# or
MCP_TRANSPORT=sse MCP_PORT=8080 python -m mamaguard.mcp_server.server  # SSE
```

### 2. Deploy MCP Server for Remote Access

For PO to reach the MCP server, deploy with SSE transport:

```bash
# Using the existing Dockerfile with agent module override:
docker build -t mamaguard-mcp -f mamaguard/Dockerfile mamaguard/
docker run -p 8080:8080 \
  -e AGENT_MODULE=mamaguard.mcp_server.server \
  -e MCP_TRANSPORT=sse \
  -e MCP_PORT=8080 \
  mamaguard-mcp

# Or deploy to Cloud Run:
gcloud run deploy mamaguard-mcp \
  --source mamaguard/ \
  --set-env-vars="MCP_TRANSPORT=sse,MCP_PORT=8080" \
  --port=8080 \
  --allow-unauthenticated
```

### 3. Register MCP Server in PO

1. In PO, go to **Agents > Create Agent** (or edit existing BYO Agent)
2. Under **MCP Servers**, click **Add MCP Server**
3. Enter the SSE endpoint URL: `https://YOUR-MCP-URL:8080/sse`
4. PO discovers all 14 tools automatically from the MCP protocol
5. The BYO Agent can now invoke MamaGuard FHIR tools directly

### 4. Configure SHARP Context

Each tool requires `fhir_url`, `fhir_token`, and `patient_id` as parameters. When PO sends FHIR context, the BYO Agent's system prompt should instruct it to pass these credentials to every tool call:

```
When calling MamaGuard MCP tools, always pass:
- fhir_url: the FHIR server URL from your workspace context
- fhir_token: the bearer token from your workspace context
- patient_id: the currently selected patient ID
```

## Option B: Publish as Standalone Marketplace Artifact

### 1. Deploy SSE Endpoint (as in Option A step 2)

### 2. Create a New BYO Agent

1. Go to **Agents > Create Agent**
2. Name: `MamaGuard FHIR Tools (MCP)`
3. Scope: **Patient**
4. Model: **Gemini 2.5 Flash**
5. System prompt: Instruct the agent to use the attached MCP tools for maternal-pediatric care coordination
6. Attach MCP server (SSE URL from step 1)
7. Enable FHIR context

### 3. Publish to Marketplace

1. Click **Publish to Marketplace**
2. Verify: agent appears on launchpad with MCP tools available

## Option C: Use with Claude Desktop / Cursor / Other MCP Clients

### Claude Desktop

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "mamaguard": {
      "command": "python",
      "args": ["-m", "mamaguard.mcp_server.server"],
      "cwd": "/path/to/repo/mamaguard",
      "env": {}
    }
  }
}
```

### Cursor

Add to MCP server settings:

```json
{
  "mamaguard": {
    "command": "python",
    "args": ["-m", "mamaguard.mcp_server.server"],
    "cwd": "/path/to/repo/mamaguard"
  }
}
```

### Remote SSE Client

Any MCP client that supports SSE transport can connect to:
```
MCP_TRANSPORT=sse MCP_PORT=8080 python -m mamaguard.mcp_server.server
# Connect at http://localhost:8080/sse
```

## Testing

```bash
# Run MCP server tests
python -m pytest mamaguard/tests/test_mcp_server.py -v

# Full test suite (269 tests)
python -m pytest mamaguard/tests/ -v
```

## Tool Reference

All 14 tools require `fhir_url`, `fhir_token`, `patient_id` as the first 3 parameters (SHARP context). See `mamaguard/mcp_server/README.md` for full tool documentation.
