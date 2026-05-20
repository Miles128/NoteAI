# NoteAI

**AI-Powered Personal Knowledge Base + AI Assistant Desktop App** — Collect, organize, link, search, and chat. Turn scattered information into structured knowledge, and let the AI assistant answer questions based on your knowledge base.

[中文](./README.md)

Inspired by [Karpathy's LLM Wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f): instead of re-deriving answers from raw documents every time, let LLMs "compile" scattered materials into a structured knowledge base that compounds over time.

## Core Philosophy

> **Stop re-deriving, start compiling.**

Traditional RAG searches raw documents on every query, assembling answers from scratch with no accumulation. NoteAI inserts a "compilation layer" between raw materials and final answers — a structured Markdown knowledge base actively maintained by AI. Knowledge is compiled once and grows in value, rather than being re-derived every time.

At the same time, NoteAI deeply integrates the personal knowledge base with an AI assistant: the assistant not only possesses general knowledge but can also answer questions and provide insights based on your knowledge base, with both short-term and long-term memory, truly becoming a personal assistant that "understands you."

## Features

### 📥 Collection

| Feature | Description |
|---------|-------------|
| Web Article Download | Batch URL input, auto-extract body text to Markdown; optimized for WeChat Official Accounts, Zhihu, etc. |
| Multi-format Conversion | PDF / DOCX / PPTX / HTML / TXT → Markdown; auto-convert pending files on startup |
| AI-assisted Formatting | LLM smart formatting, clean up garbled text, normalize headings and lists |

### 🗂️ Organization

| Feature | Description |
|---------|-------------|
| Hierarchical Topics | Unlimited topic depth (paths separated by `/`), tree view in sidebar, breadcrumb navigation |
| Tag System | jieba tokenization + word frequency auto-tagging; YAML front matter management |
| Note Integration | Concatenate files by topic → LLM generates integrated notes → save to Organized directory |
| AI Topic Analysis | LLM reviews existing topic structure, suggests new/adjusted/merged topics |

### 🔗 Linking

| Feature | Description |
|---------|-------------|
| Bidirectional Link Discovery | Local coarse filtering (same topic / shared tags / filename overlap) → AI fine-grained relevance judgment |
| Relationship Graph | File-topic-tag-bilink graph visualization, Canvas force-directed layout |
| WIKI.md Index | Auto-generate and maintain hierarchical topic directory, file outlines, source lists |

### ✍️ Editing

| Feature | Description |
|---------|-------------|
| Markdown Editor | Tiptap rich-text Markdown editing with autosave and a basic formatting toolbar |
| Live Preview | marked.js + highlight.js rendering, edit/preview split-pane mode |
| AI Rewrite | Select content → LLM streaming rewrite → preview comparison → apply or discard |
| Topic Survey | LLM writes a survey article for a specified topic |

### 🤖 AI Assistant (RAG)

| Feature | Description |
|---------|-------------|
| Knowledge Base Q&A | RAG retrieval-augmented generation based on workspace knowledge base, evidence-backed answers |
| HyDE Query Optimization | Hypothetical Document Embedding — LLM generates a hypothetical answer first, then retrieves, improving recall |
| Flashrank Reranking | Local reranking model for secondary sorting of retrieval results, improving precision |
| Parent-Child Document Retrieval | Auto-expand from retrieved child chunks to parent documents for full context |
| Short-term Memory | In-session dialogue summaries, maintaining contextual coherence |
| Long-term Memory | Auto-extract user self-description info, persist across sessions (≤1500 chars, auto-compress when exceeded) |
| Personalized Assistant | "Xiao Yi" — a caring personal assistant, concise yet warm |
| Resizable Panel | Assistant panel expandable/collapsible, width adjustable by dragging |

### 🔍 Search & Browsing

| Feature | Description |
|---------|-------------|
| Full-text Search | Case-insensitive search across workspace, returns matching files, titles, context snippets |
| Sidebar Views | File tree / Topics / Tags / Bidirectional Links — four switchable views |
| File Preview | Markdown, TXT, PDF (page-by-page rendering), Word documents |

## Architecture

```
┌─────────────────────────────────────────────┐
│                  Tauri v2 Shell              │
│  ┌─────────────────────────────────────────┐ │
│  │          Frontend (HTML/CSS/JS)          │ │
│  │  sidebar · editor · preview · graph     │ │
│  │  assistant (RAG chat panel)              │ │
│  └──────────────┬──────────────────────────┘ │
│                 │ window.api (JSON-RPC)       │
│  ┌──────────────▼──────────────────────────┐ │
│  │        Python Sidecar (stdin/stdout)     │ │
│  │  ┌─────────────────────────────────┐    │ │
│  │  │  SidecarServer (10 Mixins)      │    │ │
│  │  │  Config · Workspace · Transfer  │    │ │
│  │  │  Files · Tags · Topics · Links  │    │ │
│  │  │  Intel · Paths · RAG            │    │ │
│  │  └─────────────────────────────────┘    │ │
│  │  rag/ · modules/ · utils/ · prompts/    │ │
│  └─────────────────────────────────────────┘ │
└─────────────────────────────────────────────┘
```

**RAG Retrieval Pipeline**:

```
User Query → HyDE hypothetical answer generation
           → Milvus Lite hybrid retrieval (dense + sparse, bge-small-zh-v1.5)
           → Topic/tag filtering
           → FlagReranker reranking (bge-reranker-v2-m3)
           → MMR deduplication
           → LLM generates answer (streaming output)
```

**Three-layer Knowledge Architecture** (aligned with Karpathy LLM Wiki):

```
Workspace/
├── Notes/               ← Raw layer: original Markdown (immutable, source of truth)
├── Organized/           ← Wiki layer: AI-compiled structured knowledge (LLM-owned, continuously updated)
├── Raw/                 ← Original file archive (PDF/DOCX/PPTX)
├── WIKI.md              ← Global index (hierarchical topic directory + file outlines)
├── tags.md              ← Tag index (bidirectional link index aggregated by tag)
└── .links.json          ← Bidirectional link data (pending / confirmed)
```

## Tech Stack

| Category | Technology |
|----------|------------|
| Desktop Shell | Tauri v2 + Rust |
| Frontend | HTML5 / CSS3 / JS, marked.js, highlight.js, PDF.js, Tiptap |
| Backend | Python 3.10+, LangChain + LangChain-OpenAI |
| RAG | Milvus Lite, fastembed (BAAI/bge-small-zh-v1.5), FlagEmbedding (BAAI/bge-reranker-v2-m3) |
| Document Parsing | PyMuPDF, mammoth, python-docx, html2text, readability-lxml |
| NLP | jieba tokenization |
| File Watching | watchdog |
| Dependency Management | uv + pyproject.toml |

## Getting Started

### Prerequisites

- **Python 3.10+**
- **Rust** and [Tauri CLI v2](https://v2.tauri.app/)
- [uv](https://docs.astral.sh/uv/) recommended for dependency management

### Installation

```bash
cd NoteAI
uv venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
uv sync
```

### Running

```bash
python run.py
```

This checks dependencies and runs `cargo tauri dev`, launching the Python sidecar subprocess alongside.

## Directory Structure

```
NoteAI/
├── run.py                  # Launcher
├── src-tauri/              # Tauri shell (Rust)
├── webui/                  # Frontend static assets
│   ├── index.html
│   ├── css/                # variables · layout · components · tree · editor · preview
│   └── js/                 # state · sidebar · tree · topic · tags · links · graph
│                          # editor · assistant · preview · search · settings · ...
├── python/
│   ├── main.py             # Sidecar process entry point
│   └── sidecar/            # RPC routing + 10 Mixin business modules
│       ├── mixins/         # Config · Workspace · Transfer · Files · Tags
│       │                   # Topics · Links · Intel · Paths · RAG
│       └── rag/            # chunker · embedder · index · retriever · memory · web_search
├── modules/                # Business modules (download · convert · integrate · preview · topic extraction)
├── utils/                  # Utility libraries (LLM · tags · links · text processing · logging)
├── prompts/                # LLM prompts (independently managed, imported by business code)
├── config/                 # Configuration (settings.py + config.json)
└── tests/                  # Tests
```

## Roadmap

### 🔥 Cascade Updates

When new material enters the knowledge base, don't just create new pages — actively find and update all affected existing pages. One new paper triggers updates across 5 existing pages. This is the soul of LLM Wiki; without it, the knowledge base is a stagnant pool that only grows, never evolves.

### 🔥 Contradiction Detection

During ingestion, let the LLM compare new content against existing wiki content and flag conflicts. When two articles contradict each other, help you notice.

### 🔥 Lint Self-check

Manually trigger a knowledge base health check: find contradictions, stale claims, broken links (related articles that don't reference each other), and gaps (concepts referenced multiple times without a dedicated page).

### 🟡 Operation Log

Maintain `wiki/log.md` recording every Ingest/Lint/cascade update change, enabling traceability of the knowledge base's evolution.

### 🟡 Topic Drag-and-drop Reordering

Support drag-and-drop in the sidebar topic tree to adjust order and hierarchy. Dragging a subtopic under a different parent automatically updates the path prefix.

## Testing

```bash
uv sync --extra dev
pytest
```

## Author

Sihai (四海)

## License

MIT
