import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';

import { createTools, resolveWorkspacePath } from '../src/tools.js';

async function withWorkspace(run) {
  const parent = await fs.mkdtemp(path.join(os.tmpdir(), 'noteai-mcp-test-'));
  const workspace = path.join(parent, 'vault');
  const outside = path.join(parent, 'vault-outside');
  await fs.mkdir(path.join(workspace, 'Notes'), { recursive: true });
  await fs.mkdir(outside, { recursive: true });
  try {
    await run({ parent, workspace, outside });
  } finally {
    await fs.rm(parent, { recursive: true, force: true });
  }
}

test('rejects traversal and same-prefix sibling paths', async () => {
  await withWorkspace(async ({ workspace, outside }) => {
    await assert.rejects(
      resolveWorkspacePath(workspace, path.join('..', path.basename(outside), 'secret.md'), { allowMissing: true }),
      /outside workspace/
    );
    await assert.rejects(
      resolveWorkspacePath(workspace, path.join(outside, 'secret.md'), { allowMissing: true }),
      /outside workspace/
    );
  });
});

test('rejects writes through a symlinked parent', async () => {
  await withWorkspace(async ({ workspace, outside }) => {
    await fs.symlink(outside, path.join(workspace, 'Notes', 'external'));
    const tools = createTools(workspace);

    await assert.rejects(
      tools.vault_write_note({ file_path: 'Notes/external/escaped.md', content: '# escaped' }),
      /outside workspace/
    );
    await assert.rejects(fs.access(path.join(outside, 'escaped.md')));
  });
});

test('reports note paths relative to the workspace', async () => {
  await withWorkspace(async ({ workspace }) => {
    const notePath = path.join(workspace, 'Notes', 'example.md');
    await fs.writeFile(notePath, '---\ntopic: Test\n---\n# Example\n', 'utf-8');
    const tools = createTools(workspace);

    const result = await tools.vault_read_note({ file_path: 'Notes/example.md' });

    assert.match(result.content[0].text, /^File: Notes\/example\.md/m);
  });
});
