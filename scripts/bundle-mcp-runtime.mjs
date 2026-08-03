import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import './build-mcp-bundle.mjs';

const projectRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const runtimeDir = path.join(projectRoot, 'src-tauri', 'resources', 'mcp-runtime');
const nodeName = process.platform === 'win32' ? 'node.exe' : 'node';
const nodeTarget = path.join(runtimeDir, 'bin', nodeName);
const serverTarget = path.join(runtimeDir, 'server', 'index.js');

await fs.mkdir(path.dirname(nodeTarget), { recursive: true });
await fs.mkdir(path.dirname(serverTarget), { recursive: true });
await fs.copyFile(process.execPath, nodeTarget);
await fs.copyFile(path.join(projectRoot, 'mcp-server', 'dist', 'index.js'), serverTarget);
if (process.platform !== 'win32') await fs.chmod(nodeTarget, 0o755);

console.log(`Bundled MCP runtime: ${runtimeDir}`);
