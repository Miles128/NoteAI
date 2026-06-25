# NoteAI PRD - Minimal AI Knowledge Base

**Version**: v3.0
**Date**: 2026-06-24
**Status**: Product direction and P0 execution plan

## 1. Positioning

NoteAI is a local-first, minimal AI knowledge base for collecting Chinese and mixed-language research materials, converting them into Markdown, and keeping them organized with lightweight AI assistance.

The primary product comparison is **Tolaria**: local Markdown, Git-friendly files, offline-first operation, and AI-agent-friendly workflows. NoteAI should not become a full LLM Wiki clone, a Notion/Tana-style object database, or a visualization-heavy graph tool.

One-line positioning:

> Tolaria manages your Markdown vault; NoteAI helps turn raw sources into a clean, maintainable knowledge base.

## 2. Product Principles

1. **Local files are the source of truth**
   Markdown, YAML frontmatter, `Raw/`, `Notes/`, and `wiki/` must remain readable without NoteAI.

2. **Relationship stays minimal**
   No complex property graph, no many relationship types, no nested object schema.

3. **Interface stays quiet**
   Keep the existing knowledge graph, but do not expand visualization as a main direction. Prefer Inbox, lists, editor, search, and review flows.

4. **Retrieval stays lightweight by default**
   Default RAG should use vector recall, BM25 lexical ranking, and simple heuristics. Do not download a model reranker unless the user explicitly opts in.

5. **AI writes are reviewable**
   AI can suggest, generate, and organize, but meaningful writes should be visible, reversible, and eventually Git-trackable.

6. **Derived data is disposable**
   Vector indexes, caches, state files, and memory are runtime data. The workspace should be recoverable from files.

## 3. Target Users

- Users who collect PDFs, DOCX files, web articles, newsletters, WeChat/Zhihu pages, and Markdown notes.
- Users who want a local knowledge base but do not want to manually classify every source.
- Users who prefer Markdown and files over SaaS databases.
- Users who need AI-assisted organization, summaries, and Q&A, especially in Chinese contexts.

## 4. Non-Goals

NoteAI should not prioritize:

- A full Obsidian replacement.
- A formal LLM Wiki implementation.
- A Notion/Tana-style typed object system.
- Complex relationship schemas.
- Large whiteboards, canvases, or visualization-first navigation.
- A full Git client.
- Electron migration.

## 5. Workspace Model

```text
<workspace>/
├── Notes/              # User-readable Markdown notes, organized by topic
├── wiki/               # AI-maintained summaries, WIKI.md, log.md
├── Raw/                # Original imported files
├── schema.md           # Workspace rules and AI behavior constraints
├── .noteai/            # Runtime state: memory, rag_index, ingest_state
└── .ai_memory/         # User profile and project rules
```

Current three-layer model remains:

- `Raw/`: original files.
- `Notes/`: converted and editable Markdown notes.
- `wiki/`: compiled summaries and indexes.

Do not introduce heavy `entities/`, `concepts/`, `relations/`, or database-like folders in P0/P1.

## 6. Minimal Relationship Model

Relationship in NoteAI means only three things:

### 6.1 Topic

One primary topic per note.

```yaml
topic: AI工具 > 知识管理
```

Rules:

- Maximum three levels.
- Default to one main topic per file.
- Used for folder placement, filtering, summaries, and WIKI sync.

### 6.2 Source

Simple source traceability.

```yaml
source_url: https://example.com/article
source_file: Raw/example.pdf
```

Rules:

- Used for audit and summary citations.
- Do not build a complex citation graph in P0.

### 6.3 Related

Lightweight related notes.

```yaml
related:
  - [[另一篇笔记]]
  - [[某个主题综述]]
```

Rules:

- AI may suggest related notes.
- Suggestions should enter Inbox when uncertain.
- No relationship type taxonomy such as `depends_on`, `blocks`, `mentions`, `contains`.

## 7. Core User Flows

### 7.1 Import

User imports PDF, DOCX, PPTX, HTML, TXT, web pages, or Markdown.

Expected result:

- Original file goes to `Raw/` when applicable.
- Markdown note is created under `Notes/`.
- Topic and tags are suggested.
- Failures enter Inbox.

### 7.2 Organize

AI suggests:

- Topic.
- 2-5 useful Chinese tags.
- Optional related notes.

User confirms uncertain changes in Inbox.

### 7.3 Maintain

When new notes enter a topic:

- `wiki/WIKI.md` stays aligned with `Notes/`.
- Affected topic summaries are marked stale or updated by the ingest pipeline.
- Failures and review items go to Inbox.

### 7.4 Read And Edit

User can:

- Open Markdown notes in the editor.
- Preview PDF/DOCX files.
- Edit frontmatter.
- Ask Xiao Yi about current workspace content.
- Save useful answers back to `Notes/` or `wiki/`.

## 8. Interface Direction

The main screen should converge toward:

```text
┌───────────┬──────────────┬──────────────────────┐
│ Sidebar   │ List         │ Reader / Editor       │
│           │              │                      │
│ Inbox     │ Inbox items  │ Markdown / Preview    │
│ Notes     │ Notes        │ AI suggestions / Diff │
│ Topics    │ Search hits  │                      │
│ Wiki      │              │                      │
│ Graph     │              │                      │
└───────────┴──────────────┴──────────────────────┘
```

Navigation priority:

1. Inbox.
2. Notes.
3. Topics.
4. Wiki.
5. Search.
6. Graph as optional view.

Hide or de-emphasize:

- Cloud sync until it is production-ready.
- Agent mode by default.
- Advanced RAG controls.
- Large dashboard-style metrics.

## 9. Inbox

Inbox is the product's main maintenance surface.

It should contain:

- Pending topic decisions.
- Pending related-note suggestions.
- Conversion failures.
- Stale or failed summaries.
- Lint issues.
- Risky AI writes awaiting confirmation.

Each item should have a clear action:

- Accept.
- Reject.
- Retry.
- Open source.
- Open generated diff.

## 10. AI Behavior

AI may:

- Suggest topic, tags, and related notes.
- Generate or refresh topic summaries.
- Rewrite selected text.
- Answer questions grounded in notes and wiki.
- Propose file moves.

AI should not silently:

- Delete files.
- Merge topics.
- Overwrite summaries.
- Bulk-move notes.
- Rewrite large parts of a workspace.

## 11. Technical Direction

### 11.1 Keep Tauri

Do not migrate to Electron.

Reasons:

- Tolaria itself uses Tauri.
- NoteAI's heavy work is already in the Python sidecar.
- Electron would not solve the current core problems: RPC contract drift, topic/wiki service fragmentation, UI complexity, and AI write review.
- Electron would increase package size and memory cost on top of Python and ML dependencies.

### 11.2 Modernize Gradually

Preferred path:

1. Keep Tauri + Python sidecar.
2. Keep vanilla JS in the short term.
3. Introduce stricter RPC contract tests.
4. Keep zvec as the default vector-store backend and retain Milvus Lite as a compatibility fallback.
5. Keep BM25 as the default lexical ranking layer.
6. Keep local model rerankers disabled by default; no cloud rerankers and no LLM-as-reranker.
7. Later migrate frontend modules to Vite + TypeScript if UI refactoring becomes necessary.
8. Extract Python services around stable boundaries:
   - `TopicService`
   - `WikiService`
   - `InboxService`
   - `IngestService`
   - `RelationshipService` as minimal topic/source/related only

### 11.3 Git As P1

Minimal Git support:

- Detect whether workspace is a Git repository.
- Show modified file count.
- Let users inspect AI-generated changes.
- Offer one-click commit for AI maintenance batches.
- Support rollback of one AI batch.

Do not build:

- Full branch UI.
- Remote sync UI.
- Conflict editor.

## 12. P0 Development Plan

### P0.1 Contract Cleanup

- Remove stale frontend RPC calls.
- Add missing thin RPCs for still-visible UI actions.
- Add tests that compare frontend calls against Rust allowlist.

### P0.2 Lightweight RAG Default

- Disable local model reranker by default.
- Replace simplified TF-IDF sparse scoring with BM25.
- Use zvec as the default local vector store while keeping Milvus Lite available via configuration.
- Avoid cloud rerankers and LLM rerankers.

### P0.3 Inbox First

- Make Inbox the default landing view when items exist.
- Merge pending topics, related suggestions, conversion failures, cascade failures, and lint issues.
- Ensure every item has one obvious next action.

### P0.4 Relationship Minimalization

- Normalize frontmatter around `topic`, `source_url`, `source_file`, `related`, and `tags`.
- Keep link discovery as "related note suggestions".
- Avoid exposing relationship type management UI.

### P0.5 UI Simplification

- Reduce dashboard and metrics prominence.
- Keep Graph as optional.
- Hide experimental cloud sync and Agent mode behind settings.

## 13. P1 Roadmap

- Git-backed AI write review.
- Summary citation/source list.
- Diff review for topic changes and summary updates.
- MCP or CLI surface for external agents.
- Vite + TypeScript migration only if UI maintenance cost justifies it.

## 14. Success Metrics

- A new user can import sources and get organized notes within 10 minutes.
- Most files are auto-classified or placed in Inbox with clear decisions.
- Users spend most maintenance time in Inbox, not hunting through settings.
- AI-generated writes are visible and reversible.
- The workspace remains useful as plain Markdown even without NoteAI.
