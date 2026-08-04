/**
 * Vault tool implementations for NoteAI MCP Server.
 *
 * Operates directly on the workspace file system. Later iterations can
 * delegate to the Python sidecar for richer logic (RAG, topic inference,
 * frontmatter normalization, etc.).
 */
import fs from 'fs/promises';
import path from 'path';

const IGNORED_DIRS = new Set([
  '.git', '.noteai', '.ai_memory', 'node_modules', '.obsidian',
  'wiki', 'Raw',
]);

const NOTE_EXTS = new Set(['.md', '.markdown']);

function isNote(file) {
  return NOTE_EXTS.has(path.extname(file).toLowerCase());
}

async function* walkNotes(root) {
  const entries = await fs.readdir(root, { withFileTypes: true }).catch(() => []);
  for (const entry of entries) {
    if (entry.name.startsWith('.') || IGNORED_DIRS.has(entry.name)) continue;
    const full = path.join(root, entry.name);
    if (entry.isDirectory()) {
      yield* walkNotes(full);
    } else if (entry.isFile() && isNote(entry.name)) {
      yield full;
    }
  }
}

async function listTopicPaths(root, parts = []) {
  if (parts.length >= 3) return [];
  const entries = await fs.readdir(root, { withFileTypes: true }).catch(() => []);
  const topics = [];
  for (const entry of entries.sort((a, b) => a.name.localeCompare(b.name))) {
    if (!entry.isDirectory() || entry.name.startsWith('.')) continue;
    const nextParts = [...parts, entry.name];
    topics.push(nextParts.join(' > '));
    topics.push(...await listTopicPaths(path.join(root, entry.name), nextParts));
  }
  return topics;
}

function assertPathWithin(root, target) {
  const relative = path.relative(root, target);
  if (relative === '..' || relative.startsWith(`..${path.sep}`) || path.isAbsolute(relative)) {
    throw new Error('Access denied: path outside workspace');
  }
}

/**
 * Resolve a caller-supplied path inside the real workspace root.
 *
 * For new files, canonicalize the nearest existing ancestor so a symlinked
 * parent cannot redirect the eventual write outside the workspace.
 */
export async function resolveWorkspacePath(root, requestedPath, { allowMissing = false } = {}) {
  if (typeof requestedPath !== 'string' || !requestedPath || requestedPath.includes('\0')) {
    throw new Error('Access denied: invalid path');
  }

  const lexicalRoot = path.resolve(root);
  const lexicalTarget = path.resolve(lexicalRoot, requestedPath);
  assertPathWithin(lexicalRoot, lexicalTarget);

  const realRoot = await fs.realpath(lexicalRoot);
  if (!allowMissing) {
    const realTarget = await fs.realpath(lexicalTarget);
    assertPathWithin(realRoot, realTarget);
    return realTarget;
  }

  let ancestor = lexicalTarget;
  const missingParts = [];
  while (true) {
    try {
      await fs.lstat(ancestor);
      break;
    } catch (error) {
      if (!error || error.code !== 'ENOENT') throw error;
      const parent = path.dirname(ancestor);
      if (parent === ancestor) throw new Error('Access denied: no existing parent');
      missingParts.unshift(path.basename(ancestor));
      ancestor = parent;
    }
  }

  const realAncestor = await fs.realpath(ancestor);
  assertPathWithin(realRoot, realAncestor);
  const resolvedTarget = path.join(realAncestor, ...missingParts);
  assertPathWithin(realRoot, resolvedTarget);
  return resolvedTarget;
}

async function readNote(root, notePath) {
  const content = await fs.readFile(notePath, 'utf-8');
  const rel = path.relative(root, notePath);
  const frontmatter = {};
  const match = content.match(/^---\s*\n([\s\S]*?)\n---\s*\n/);
  if (match) {
    const yaml = match[1];
    for (const line of yaml.split('\n')) {
      const idx = line.indexOf(':');
      if (idx > 0) {
        const key = line.slice(0, idx).trim();
        const value = line.slice(idx + 1).trim().replace(/^["']|["']$/g, '');
        frontmatter[key] = value;
      }
    }
  }
  return { path: rel, frontmatter, content };
}

export function createTools(workspacePath) {
  const root = path.resolve(workspacePath);

  return {
    vault_read_note: async ({ file_path }) => {
      const target = await resolveWorkspacePath(root, file_path);
      const note = await readNote(await fs.realpath(root), target);
      return {
        content: [
          { type: 'text', text: `File: ${note.path}\n---\n${note.frontmatter.topic ? `topic: ${note.frontmatter.topic}\n` : ''}${note.frontmatter.tags ? `tags: ${note.frontmatter.tags}\n` : ''}---\n${note.content}` }
        ]
      };
    },

    vault_list_notes: async ({ topic, limit = 50 }) => {
      const notes = [];
      for await (const p of walkNotes(root)) {
        const rel = path.relative(root, p);
        if (topic && !rel.includes(topic)) continue;
        notes.push({ path: rel });
        if (notes.length >= limit) break;
      }
      return {
        content: [
          { type: 'text', text: `Found ${notes.length} notes:\n${notes.map(n => `- ${n.path}`).join('\n')}` }
        ]
      };
    },

    vault_search_notes: async ({ query, limit = 20 }) => {
      const q = query.toLowerCase();
      const hits = [];
      for await (const p of walkNotes(root)) {
        const content = await fs.readFile(p, 'utf-8').catch(() => '');
        const rel = path.relative(root, p);
        if (rel.toLowerCase().includes(q) || content.toLowerCase().includes(q)) {
          const preview = content.slice(0, 300).replace(/\s+/g, ' ');
          hits.push({ path: rel, preview });
        }
        if (hits.length >= limit) break;
      }
      return {
        content: [
          { type: 'text', text: `Search results for "${query}":\n${hits.map(h => `- ${h.path}\n  ${h.preview}`).join('\n')}` }
        ]
      };
    },

    vault_list_topics: async () => {
      const topics = await listTopicPaths(path.join(root, 'Notes'));
      const text = topics.length
        ? `Topic paths from Notes/:\n${topics.map(topic => `- ${topic}`).join('\n')}`
        : 'No topic folders found under Notes/.';
      return {
        content: [{ type: 'text', text }]
      };
    },

    vault_write_note: async ({ file_path, content }) => {
      const target = await resolveWorkspacePath(root, file_path, { allowMissing: true });
      await fs.mkdir(path.dirname(target), { recursive: true });
      await fs.writeFile(target, content, 'utf-8');
      return {
        content: [{ type: 'text', text: `Wrote ${path.relative(root, target)}` }]
      };
    },

    vault_update_frontmatter: async ({ file_path, updates }) => {
      const target = await resolveWorkspacePath(root, file_path);
      let content = await fs.readFile(target, 'utf-8').catch(() => '');
      const fmMatch = content.match(/^---\s*\n([\s\S]*?)\n---\s*\n/);
      let fm = {};
      let body = content;
      if (fmMatch) {
        const yaml = fmMatch[1];
        body = content.slice(fmMatch[0].length);
        for (const line of yaml.split('\n')) {
          const idx = line.indexOf(':');
          if (idx > 0) {
            fm[line.slice(0, idx).trim()] = line.slice(idx + 1).trim().replace(/^["']|["']$/g, '');
          }
        }
      }
      Object.assign(fm, updates);
      const lines = Object.entries(fm).map(([k, v]) => `${k}: ${v}`);
      content = `---\n${lines.join('\n')}\n---\n${body}`;
      await fs.writeFile(target, content, 'utf-8');
      return {
        content: [{ type: 'text', text: `Updated frontmatter in ${path.relative(root, target)}` }]
      };
    },

    vault_append_log: async ({ message }) => {
      const logPath = await resolveWorkspacePath(root, 'wiki/log.md', { allowMissing: true });
      const line = `\n- ${new Date().toISOString()} ${message}`;
      await fs.mkdir(path.dirname(logPath), { recursive: true });
      await fs.appendFile(logPath, line, 'utf-8');
      return {
        content: [{ type: 'text', text: `Appended to wiki/log.md` }]
      };
    },

    vault_move_note: async ({ from_path, to_path }) => {
      const src = await resolveWorkspacePath(root, from_path);
      const dst = await resolveWorkspacePath(root, to_path, { allowMissing: true });
      await fs.mkdir(path.dirname(dst), { recursive: true });
      await fs.rename(src, dst);
      return {
        content: [{ type: 'text', text: `Moved ${from_path} -> ${to_path}` }]
      };
    },

    vault_raw_archive: async ({ file_path }) => {
      const src = await resolveWorkspacePath(root, file_path);
      const rawDir = await resolveWorkspacePath(root, 'Raw', { allowMissing: true });
      const dst = await resolveWorkspacePath(root, path.join('Raw', path.basename(file_path)), { allowMissing: true });
      await fs.mkdir(rawDir, { recursive: true });
      await fs.rename(src, dst);
      return {
        content: [{ type: 'text', text: `Archived ${file_path} -> Raw/${path.basename(file_path)}` }]
      };
    },

    vault_ingest_url: async ({ url }) => {
      return {
        content: [{ type: 'text', text: `URL ingestion is not yet implemented in the MCP server. Please use the NoteAI app to ingest: ${url}` }]
      };
    },
  };
}
