#!/usr/bin/env node
/**
 * NoteAI MCP Server
 *
 * Exposes NoteAI vault operations as MCP tools for external CLI agents.
 * Supports:
 * - stdio transport (default, for Claude Code / Cursor / OpenCode / Codex CLI)
 * - WebSocket transport on port 9710/9711 (for NoteAI frontend remote control)
 *
 * Usage:
 *   node src/index.js --workspace /path/to/workspace [--port 9710]
 */
import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import { CallToolRequestSchema, ListToolsRequestSchema } from '@modelcontextprotocol/sdk/types.js';
import { WebSocketServer } from 'ws';
import { createTools } from './tools.js';

/**
 * Minimal MCP Transport wrapper over a WebSocket.
 *
 * Note: this is intentionally lightweight; the primary transport is stdio.
 * WebSocket is exposed for future frontend remote-control use cases.
 */
class WebSocketServerTransport {
  constructor(ws) {
    this._ws = ws;
    this.onMessage = undefined;
    this.onClose = undefined;
    this._setup();
  }

  _setup() {
    this._ws.on('message', (data) => {
      if (this.onMessage) {
        try {
          this.onMessage(JSON.parse(data.toString()));
        } catch (err) {
          console.error('WebSocket message parse error:', err);
        }
      }
    });
    this._ws.on('close', () => {
      if (this.onClose) this.onClose();
    });
  }

  async start() {
    // WebSocket is already open when this transport is constructed.
  }

  async send(message) {
    return new Promise((resolve, reject) => {
      this._ws.send(JSON.stringify(message), (err) => {
        if (err) reject(err);
        else resolve();
      });
    });
  }

  async close() {
    return new Promise((resolve) => {
      if (this._ws.readyState === 3) { // CLOSED
        resolve();
      } else {
        this._ws.once('close', resolve);
        this._ws.close();
      }
    });
  }
}

function parseArgs() {
  const args = process.argv.slice(2);
  let workspace = process.env.NOTEAI_WORKSPACE || '';
  let port = 9710;
  let transport = 'stdio';
  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--workspace' && i + 1 < args.length) {
      workspace = args[++i];
    } else if (args[i] === '--port' && i + 1 < args.length) {
      port = parseInt(args[++i], 10);
    } else if (args[i] === '--transport' && i + 1 < args.length) {
      transport = args[++i];
    }
  }
  return { workspace, port, transport };
}

function createMcpServer(workspacePath) {
  const tools = createTools(workspacePath);

  const toolDefinitions = [
    {
      name: 'vault_read_note',
      description: 'Read a Markdown note from the vault, including its YAML frontmatter.',
      inputSchema: {
        type: 'object',
        properties: {
          file_path: { type: 'string', description: 'Relative or absolute path to the note' }
        },
        required: ['file_path']
      }
    },
    {
      name: 'vault_list_notes',
      description: 'List Markdown notes in the vault, optionally filtered by topic substring.',
      inputSchema: {
        type: 'object',
        properties: {
          topic: { type: 'string', description: 'Optional topic/path substring filter' },
          limit: { type: 'number', description: 'Maximum number of notes to return', default: 50 }
        }
      }
    },
    {
      name: 'vault_search_notes',
      description: 'Search notes by filename and content.',
      inputSchema: {
        type: 'object',
        properties: {
          query: { type: 'string', description: 'Search query' },
          limit: { type: 'number', description: 'Maximum number of results', default: 20 }
        },
        required: ['query']
      }
    },
    {
      name: 'vault_list_topics',
      description: 'Return the vault topic guide (wiki/GUIDE.md).',
      inputSchema: { type: 'object', properties: {} }
    },
    {
      name: 'vault_write_note',
      description: 'Create or overwrite a Markdown note in the vault.',
      inputSchema: {
        type: 'object',
        properties: {
          file_path: { type: 'string' },
          content: { type: 'string' }
        },
        required: ['file_path', 'content']
      }
    },
    {
      name: 'vault_update_frontmatter',
      description: 'Update YAML frontmatter keys of an existing note.',
      inputSchema: {
        type: 'object',
        properties: {
          file_path: { type: 'string' },
          updates: { type: 'object', description: 'Key/value pairs to set in frontmatter' }
        },
        required: ['file_path', 'updates']
      }
    },
    {
      name: 'vault_append_log',
      description: 'Append a line to wiki/log.md.',
      inputSchema: {
        type: 'object',
        properties: { message: { type: 'string' } },
        required: ['message']
      }
    },
    {
      name: 'vault_move_note',
      description: 'Move or rename a note within the vault.',
      inputSchema: {
        type: 'object',
        properties: {
          from_path: { type: 'string' },
          to_path: { type: 'string' }
        },
        required: ['from_path', 'to_path']
      }
    },
    {
      name: 'vault_raw_archive',
      description: 'Move a file into the Raw/ archive directory.',
      inputSchema: {
        type: 'object',
        properties: { file_path: { type: 'string' } },
        required: ['file_path']
      }
    },
    {
      name: 'vault_ingest_url',
      description: 'Request ingestion of a URL into the vault. (placeholder)',
      inputSchema: {
        type: 'object',
        properties: { url: { type: 'string' } },
        required: ['url']
      }
    }
  ];

  const server = new Server(
    { name: 'noteai-vault', version: '0.1.0' },
    { capabilities: { tools: {} } }
  );

  server.setRequestHandler(ListToolsRequestSchema, async () => {
    return { tools: toolDefinitions };
  });

  server.setRequestHandler(CallToolRequestSchema, async (request) => {
    const { name, arguments: args } = request.params;
    const handler = tools[name];
    if (!handler) {
      throw new Error(`Unknown tool: ${name}`);
    }
    return await handler(args || {});
  });

  return server;
}

async function main() {
  const { workspace, port, transport } = parseArgs();
  if (!workspace) {
    console.error('Error: --workspace is required');
    process.exit(1);
  }

  const server = createMcpServer(workspace);

  if (transport === 'websocket') {
    const wss = new WebSocketServer({ port });
    wss.on('connection', (ws) => {
      const transport = new WebSocketServerTransport(ws);
      server.connect(transport).catch((err) => {
        console.error('MCP WebSocket transport error:', err);
      });
    });
    console.error(`NoteAI MCP server listening on ws://localhost:${port}`);
  } else {
    const stdioTransport = new StdioServerTransport();
    await server.connect(stdioTransport);
  }
}

main().catch((err) => {
  console.error('Fatal error:', err);
  process.exit(1);
});
