# NoteAI

Minimal AI knowledge base for local Markdown workspaces.

NoteAI helps you collect PDFs, DOCX files, web pages, and Markdown notes, convert them into a local workspace, and keep them organized with lightweight AI assistance.

The product direction is inspired by local-first tools such as Tolaria: files first, Git-friendly, offline-friendly, and AI-agent-friendly. NoteAI's difference is that it focuses more on **source ingestion, Chinese content organization, topic summaries, and a simple maintenance Inbox**.

## What NoteAI Is

NoteAI is a desktop app for turning raw sources into a clean, maintainable knowledge base.

It is:

- Local-first: your knowledge lives in plain files.
- Markdown-first: notes and summaries remain readable outside the app.
- AI-assisted: AI suggests topics, tags, related notes, summaries, and rewrites.
- Minimal by design: relationships stay simple, and visualization stays secondary.

It is not:

- A full Obsidian replacement.
- A Notion/Tana-style object database.
- A formal LLM Wiki clone.
- A visualization-heavy graph product.
- An Electron app.

## Core Model

The workspace uses three main folders:

```text
<workspace>/
├── Notes/              # Markdown notes, organized by topic
├── wiki/               # WIKI.md, topic summaries, log.md
├── Raw/                # Original files such as PDF/DOCX/PPTX
├── schema.md           # Workspace rules
├── .noteai/            # Runtime state: memory, rag_index, ingest_state
└── .ai_memory/         # User profile and project rules
```

Runtime indexes and caches are derived data. The files are the source of truth.

## Minimal Relationships

NoteAI intentionally keeps relationships small:

```yaml
topic: AI工具 > 知识管理
source_url: https://example.com/article
source_file: Raw/example.pdf
related:
  - [[另一篇笔记]]
tags:
  - 知识管理
  - AI工具
```

Only three relationship concepts matter:

- `topic`: one primary topic per note, up to three levels.
- `source`: simple traceability to URL or raw file.
- `related`: lightweight related-note links, usually suggested and confirmed.

There is no complex relationship taxonomy.

## Features

### Capture

- Import PDF, DOCX, PPTX, HTML, TXT, and Markdown.
- Download web pages into Markdown.
- Archive original files in `Raw/`.
- Convert supported files into editable notes.

### Organize

- Suggest topics and tags.
- Move notes into topic folders.
- Maintain `wiki/WIKI.md`.
- Keep pending decisions in a unified Inbox.

### Maintain

- Generate and refresh topic summaries.
- Track conversion, summary, and lint failures.
- Retry or dismiss maintenance items from Inbox.
- Keep a workspace log in `wiki/log.md`.

### Read And Ask

- Edit Markdown with Tiptap.
- Preview PDF and DOCX files.
- Search notes and wiki content.
- Chat with Xiao Yi using classic retrieval or optional zvec-backed hybrid RAG.

### Graph

NoteAI keeps the existing knowledge graph, but graph visualization is optional. The main product surface is Inbox, notes, topics, wiki, search, and editor.

## Architecture

```text
Tauri v2 shell
  ├── webui/                 # HTML/CSS/vanilla JS
  └── Python sidecar         # JSON-RPC over stdin/stdout
        ├── handlers/        # workspace, files, topics, tags, links, RAG, ingest
        ├── rag/             # Vector search, BM25 lexical ranking, optional model reranker
        └── ingest_pipeline  # convert -> compile -> classify -> index -> cascade -> lint -> sync
```

Communication flow:

```text
Frontend JS -> Tauri invoke -> Rust allowlist -> Python sidecar -> handler -> filesystem / index / LLM
```

## Tech Stack

| Layer | Stack |
|---|---|
| Desktop | Tauri v2, Rust |
| Frontend | HTML, CSS, vanilla JS, Tiptap, D3, PDF.js |
| Backend | Python 3.10+ sidecar |
| Retrieval | Classic search by default; optional zvec-backed hybrid RAG |
| Embedding | fastembed, BAAI/bge-small-zh-v1.5 |
| Lexical Rank | BM25 over jieba tokens |
| Model Rerank | Disabled by default; local BGE reranker remains opt-in |
| NLP | jieba |
| Dependencies | uv, pyproject.toml |

## Why Not Electron

NoteAI stays on Tauri.

Electron would not solve the current product and engineering problems: RPC contract drift, topic/wiki service boundaries, UI simplification, and AI write review. It would also add another heavy runtime on top of Python and ML dependencies.

The preferred path is:

1. Keep Tauri + Python sidecar.
2. Tighten RPC contracts.
3. Simplify UI around Inbox and notes.
4. Add Git-backed review later.
5. Consider Vite + TypeScript only when frontend maintenance requires it.

## Quick Start

Requirements:

- Python 3.10+
- Rust
- Tauri CLI v2
- uv

```bash
uv sync
python run.py
```

For tests:

```bash
uv sync --extra dev
uv run --extra dev python -m pytest
```

`pytest` may use a system interpreter if invoked directly; prefer the `uv run --extra dev python -m pytest` command above.

## Development Layout

```text
NoteAI/
├── run.py
├── src-tauri/              # Tauri shell and Rust RPC bridge
├── webui/                  # Static frontend
├── python/sidecar/         # Python JSON-RPC server and handlers
├── modules/                # Download, convert, preview, integration
├── utils/                  # LLM, topics, links, logging, text utilities
├── prompts/                # Prompt constants and YAML prompt files
├── config/                 # App config and workspace constants
├── tests/                  # Unit and integration tests
└── docs/PRD.md             # Product requirements
```

## Roadmap

P0:

- Clean stale RPC/API contracts.
- Make Inbox the primary maintenance surface.
- Keep relationship minimal: topic, source, related.
- Simplify UI and hide experimental surfaces by default.
- Use lightweight hybrid RAG by default: vector recall + BM25 + heuristic ranking, no model reranker download.

P1:

- Git-backed AI write review.
- Diff and rollback for AI maintenance batches.
- Better summary citations and source lists.
- Milvus Lite compatibility as a fallback backend.
- External agent surface via MCP or CLI.

P2:

- Vite + TypeScript migration if needed.
- More robust multi-workspace and sync story.
- Optional custom views without becoming a database product.

## License

MIT License.
