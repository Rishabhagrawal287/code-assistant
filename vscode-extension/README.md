# AI Code Assistant — Local VS Code Extension

> A fully local, privacy-first AI-powered coding assistant built as a VS Code extension with a FastAPI backend. Zero cloud dependencies, zero cost — everything runs on your machine.

![Python](https://img.shields.io/badge/Python-3.11-blue?logo=python)
![FastAPI](https://img.shields.io/badge/FastAPI-0.111-green?logo=fastapi)
![TypeScript](https://img.shields.io/badge/TypeScript-5.3-blue?logo=typescript)
![Ollama](https://img.shields.io/badge/LLM-Ollama-orange)
![ChromaDB](https://img.shields.io/badge/VectorDB-ChromaDB-purple)
![License](https://img.shields.io/badge/License-MIT-yellow)

---

## What It Does

This project brings AI code assistance directly into VS Code using only free, locally-running tools. No data ever leaves your machine.

| Feature | Description |
|---|---|
| **Inline Completions** | Ghost-text code suggestions as you type, powered by a local LLM |
| **Code Explanation** | Right-click any selected code → get a plain-English explanation with improvement suggestions |
| **Semantic Code Search** | Find similar code across your entire codebase using vector embeddings |
| **Chat Panel** | Sidebar chat that understands your active file and answers questions about your code |
| **Auto-Indexing** | Workspace files are automatically indexed on open and re-indexed on every save |

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    VS Code Extension                     │
│  ┌──────────────┐  ┌────────────────┐  ┌─────────────┐ │
│  │  Completion  │  │  Chat Sidebar  │  │   Commands  │ │
│  │  Provider    │  │  (Webview)     │  │  Explain/   │ │
│  │  (ghost text)│  │                │  │  Search     │ │
│  └──────┬───────┘  └───────┬────────┘  └──────┬──────┘ │
│         └──────────────────┼───────────────────┘        │
│                    TypeScript API Client                 │
└────────────────────────────┼────────────────────────────┘
                             │ HTTP (localhost:8000)
┌────────────────────────────▼────────────────────────────┐
│                   FastAPI Backend                        │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────┐ │
│  │  /completion│  │  /explanation│  │    /search     │ │
│  │  /inline    │  │  /explain    │  │    /similar    │ │
│  │             │  │  /chat       │  │    /index/files│ │
│  └──────┬──────┘  └──────┬───────┘  └───────┬────────┘ │
│         │                │                   │          │
│  ┌──────▼──────┐  ┌──────▼───────┐  ┌───────▼────────┐ │
│  │  LLM Client │  │   Embedder   │  │   Retriever    │ │
│  │  (Ollama)   │  │(sentence-    │  │  (ChromaDB)    │ │
│  │             │  │transformers) │  │                │ │
│  └──────┬──────┘  └──────────────┘  └────────────────┘ │
└─────────┼───────────────────────────────────────────────┘
          │
┌─────────▼──────────┐
│   Ollama Daemon    │
│  llama3.2 / deepseek-coder  │
│  (runs locally)    │
└────────────────────┘
```

---

## Tech Stack

### Backend
| Tool | Purpose | Why Free |
|---|---|---|
| **Python 3.11** | Runtime | Open source |
| **FastAPI** | REST API framework | Open source |
| **Ollama** | Local LLM server | Free, runs offline |
| **llama3.2 / deepseek-coder** | Language model | Free weights |
| **ChromaDB** | Vector database | Open source, local |
| **sentence-transformers** | Text embeddings | Open source, local |
| **all-MiniLM-L6-v2** | Embedding model | Free HuggingFace model |

### VS Code Extension
| Tool | Purpose |
|---|---|
| **TypeScript** | Extension language |
| **VS Code Extension API** | Editor integration |
| **Fetch API** | HTTP client (built-in) |

---

## Project Structure

```
code-assistant/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app, lifespan, CORS, health endpoint
│   │   ├── config.py            # Pydantic-Settings config from .env
│   │   ├── models/
│   │   │   └── schemas.py       # All Pydantic request/response models
│   │   ├── routes/
│   │   │   ├── completion.py    # POST /completion/inline
│   │   │   ├── search.py        # POST /search/similar, /search/index/files
│   │   │   └── explanation.py   # POST /explanation/explain, /chat, /chat/stream
│   │   └── services/
│   │       ├── llm_client.py    # Ollama async wrapper + prompt builders
│   │       ├── embedder.py      # sentence-transformers wrapper + chunking
│   │       └── retriever.py     # ChromaDB wrapper (upsert, query, delete)
│   ├── requirements.txt
│   └── .env.example
└── vscode-extension/
    ├── package.json             # Extension manifest, commands, sidebar config
    ├── tsconfig.json
    └── src/
        ├── extension.ts         # Entry point, commands, status bar, auto-index
        ├── services/
        │   └── apiClient.ts     # Typed HTTP client for all backend endpoints
        ├── providers/
        │   └── completionProvider.ts  # InlineCompletionItemProvider
        └── views/
            └── sidebarProvider.ts     # Chat panel WebviewView
```

---

## Prerequisites

- **Python 3.11+**
- **Node.js 18+** and npm
- **VS Code 1.85+**
- **Ollama** — download from [ollama.com](https://ollama.com)
- **8 GB RAM** recommended (4 GB minimum for 1.3b models)

---

## Setup & Installation

### 1. Clone the repository

```bash
git clone https://github.com/YOUR_USERNAME/code-assistant.git
cd code-assistant
```

### 2. Install Ollama and pull a model

Download Ollama from [ollama.com](https://ollama.com), then pull a model:

```bash
# Recommended — fast, good at code (776 MB)
ollama pull deepseek-coder:1.3b

# Alternative — good general model (2 GB)
ollama pull llama3.2:latest
```

### 3. Set up the Python backend

```bash
cd backend
python -m venv .venv

# Windows
.venv\Scripts\Activate.ps1
# Mac/Linux
source .venv/bin/activate

pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` and set `OLLAMA_MODEL` to your pulled model name.

### 4. Start the backend

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Verify at: `http://127.0.0.1:8000/docs`

### 5. Build the VS Code extension

```bash
cd ../vscode-extension
npm install
npm run compile
```

### 6. Launch the extension

Open the `vscode-extension` folder in VS Code and press **F5**.

---

## Usage

### Chat Panel
Click the 🤖 robot icon in the Activity Bar. The assistant can see your currently open file for context.

### Explain Code
Select any code → right-click → **AI: Explain This Code**

The explanation opens in a side panel as a Markdown document with:
- Plain-English explanation
- Improvement suggestions

### Search Similar Code
Right-click anywhere → **AI: Search Similar Code**

Or press `Ctrl+Shift+P` → `AI: Search Similar Code` and type a natural language query like *"function that reads a config file"*.

### Index Your Workspace
Press `Ctrl+Shift+P` → **AI: Index Workspace Files**

This embeds all source files in your workspace into ChromaDB. Files are also re-indexed automatically on every save.

### Inline Completions
Just start typing — ghost-text suggestions appear automatically. Press **Tab** to accept.

---

## Configuration

All backend settings are in `backend/.env`:

| Setting | Default | Description |
|---|---|---|
| `OLLAMA_MODEL` | `llama3.2:latest` | Model to use for generation |
| `OLLAMA_NUM_PREDICT` | `400` | Max tokens per response |
| `OLLAMA_CONTEXT_WINDOW` | `8192` | Context length |
| `OLLAMA_TEMPERATURE` | `0.1` | Creativity (0=deterministic) |
| `EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | Embedding model |
| `SEARCH_TOP_K` | `5` | Number of search results |
| `CHUNK_SIZE` | `200` | Lines per indexed chunk |

The extension's backend URL can be changed in VS Code Settings → search `AI Code Assistant`.

---

## API Reference

The full interactive API docs are available at `http://127.0.0.1:8000/docs` when the backend is running.

| Endpoint | Method | Description |
|---|---|---|
| `/health` | GET | Backend + service health status |
| `/completion/inline` | POST | Generate inline code completion |
| `/explanation/explain` | POST | Explain selected code |
| `/explanation/chat` | POST | Multi-turn chat |
| `/explanation/chat/stream` | POST | Streaming chat (SSE) |
| `/search/similar` | POST | Semantic code search |
| `/search/index/files` | POST | Index files into ChromaDB |

---

## How It Works

### RAG Pipeline for Code Completion
1. User pauses typing (debounced 600ms)
2. Extension sends `prefix` + `suffix` to `/completion/inline`
3. Backend runs semantic search on ChromaDB using the last 200 chars of prefix
4. Top 3 matching chunks are injected into the LLM prompt as context
5. LLM generates the completion using both local context and indexed codebase
6. Ghost text appears in the editor

### Semantic Search Pipeline
1. Source files are chunked into overlapping 200-line windows
2. Each chunk is embedded using `all-MiniLM-L6-v2` (384-dim vectors)
3. Vectors are stored in ChromaDB with metadata (filepath, line numbers, language)
4. At query time, the query is embedded and cosine similarity is computed
5. Top-k most similar chunks are returned with similarity scores

---

## How to Test

Follow these steps in order every time you start the project.

### Step 1 — Start the backend
```bash
cd backend
.venv\Scripts\Activate.ps1        # Windows
# source .venv/bin/activate       # Mac/Linux
uvicorn app.main:app --host 127.0.0.1 --port 8000
```
**Expected:** You see `🟢 Backend listening on http://127.0.0.1:8000` and `Application startup complete.`

### Step 2 — Pre-warm the model
In a separate terminal:
```bash
ollama run llama3.2:latest "hello"
```
**Expected:** The model responds with a greeting. This loads it into RAM so the first chat request doesn't time out.

### Step 3 — Launch the extension
```bash
cd vscode-extension
code .
```
Press **F5** in VS Code.

**Expected:** A second VS Code window opens titled `[Extension Development Host]`. The bottom-right status bar shows `AI: ready (0 chunks)` within 10 seconds.

### Step 4 — Test the Chat Panel
In the Extension Development Host window, click the 🤖 robot icon in the left Activity Bar. Type:
```
What is a Python decorator?
```
Press Enter.

**Expected:** A response appears within 10–30 seconds explaining decorators.

### Step 5 — Test Code Explanation
Open any source file in the Extension Development Host window. Select a function with your mouse. Right-click → **AI: Explain This Code**.

**Expected:** A new Markdown tab opens beside your file with a plain-English explanation and improvement suggestions.

### Step 6 — Test Workspace Indexing
Press `Ctrl+Shift+P` → type `AI: Index Workspace Files` → press Enter.

**Expected:** A progress notification appears, then a message like `Indexed 12 files, 47 chunks.` The status bar updates to `AI: ready (47 chunks)`.

### Step 7 — Test Semantic Search
After indexing, select a code snippet, right-click → **AI: Search Similar Code**.

**Expected:** A Quick Pick dropdown appears showing similar code chunks from your codebase with file names, line numbers, and similarity scores. Selecting one opens the file at that line.

### Step 8 — Test Inline Completions
Open a Python or TypeScript file and start typing a function. Pause for 1 second.

**Expected:** Ghost text (grey suggestion) appears. Press **Tab** to accept it.

---

## Troubleshooting

### Status bar shows `AI: offline`
The backend is not running. Start it with:
```bash
cd backend && .venv\Scripts\Activate.ps1 && uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### Status bar shows `AI: degraded`
Ollama is running but slow to respond. Run `ollama run <model> "hello"` to pre-warm the model, then wait 60 seconds for the status bar to refresh.

### Chat shows `Error: Request timed out after 60s`
The model is not loaded in RAM. Run `ollama run llama3.2:latest "hello"` in a terminal first. If it still times out, reduce `OLLAMA_NUM_PREDICT` in `.env` to `200` and restart the backend.

### Chat shows `Error: 'dict' object has no attribute 'message'`
The Ollama SDK version doesn't match. The backend's `llm_client.py` already handles this — make sure you're running the latest version of the backend code.

### `npm run compile` fails with WSL errors
VS Code is using WSL as the terminal. Fix it: `Ctrl+Shift+P` → `Terminal: Select Default Profile` → select **PowerShell**. Then run `npm run compile` from an external PowerShell window.

### Explanation returns empty or garbled text
The selected code is too long for the model's context window. Select a smaller snippet (one function at a time works best).

### Search returns no results
You haven't indexed your workspace yet. Run `Ctrl+Shift+P` → **AI: Index Workspace Files** first.

### `ollama pull` fails with "no such host"
Your machine is offline or Ollama can't reach the internet. Use a model you already have (`ollama list` shows available models).

### ChromaDB telemetry errors in the backend log
```
Failed to send telemetry event: capture() takes 1 positional argument
```
This is a harmless ChromaDB bug. It does not affect functionality — ignore it.

### Port 8000 already in use
Another process is using port 8000. Either stop it, or change `PORT=8001` in `.env` and restart.

---

## Cost

**$0.00** — now and forever.

All components run locally on your machine:
- Ollama: free, open source, runs offline
- ChromaDB: free, open source, stores data locally
- sentence-transformers: free, runs on CPU
- No API keys required
- No usage limits
- No internet connection required after initial model download

---

## Resume Talking Points

- Built a **RAG (Retrieval-Augmented Generation)** pipeline for code completion using ChromaDB vector search
- Implemented a **VS Code extension** with TypeScript integrating inline completions, semantic search, and a chat panel
- Designed a **FastAPI backend** with async services for LLM inference, vector embeddings, and document retrieval
- Used **sentence-transformers** to generate 384-dimensional embeddings for semantic code search
- Integrated **Ollama** for fully local LLM inference with zero cloud dependency
- Applied **Server-Sent Events (SSE)** for streaming chat responses

---

## License

MIT — free to use, modify, and distribute.