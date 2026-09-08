# OmniRAG 🚀

> **Enterprise-Grade Multi-Source Agentic RAG Platform**

OmniRAG is an advanced, production-ready Retrieval-Augmented Generation (RAG) framework built with **LangGraph**, **FastAPI**, **PostgreSQL/pgvector**, **Redis**, and **Next.js**. It orchestrates multi-source evidence retrieval across unstructured documents, live web content, GitHub repositories, and relational databases with self-correcting agent loops, conflict detection, and grounded answer generation.

---

## 🌟 Key Features

- 🧠 **LangGraph Agentic Orchestration**: Multi-step stateful decision graph (`Analyze Query` ➔ `Plan & Route` ➔ `Retrieve Evidence` ➔ `Evaluate Sufficiency` ➔ `Conflict Detection & Answer Generation`).
- 🔎 **Hybrid Search & Reranking**: Combines dense vector search (`pgvector` / OpenAI embeddings) with BM25 lexical search and cross-encoder reranking for maximum precision.
- 🗄️ **Read-Only PostgreSQL SQL Agent**: Automatically discovers DB schemas and executes safe, sanitized read-only SQL queries to answer analytical questions directly from database records.
- ⚡ **Multi-Source Connectors**:
  - **Documents**: PDF, TXT, Markdown, Docx semantic chunking and indexing.
  - **PostgreSQL**: Dynamic schema discovery and safe read query execution.
  - **GitHub**: Repository file structure ingestion and code search.
  - **Web**: Web content scraping and vectorization.
- ⚔️ **Conflict Detection**: Detects contradicting evidence across heterogeneous data sources prior to answer generation.
- 🏷️ **Grounded Generation & Citation Validation**: Produces answers strictly backed by retrieved evidence with inline document/source citations.
- 📊 **Evaluation & Monitoring Framework**: Built-in endpoints to run RAG benchmark evaluations (faithfulness, answer relevance, context recall).
- 🎨 **Modern Next.js Dashboard**: Complete UI for chatting, managing data sources, and inspecting agent execution trace logs.

---

## 🏗️ System Architecture & Workflow

```
[ User Query ]
      │
      ▼
┌───────────────────────────────┐
│ 1. Analyze Query Node         │
│ (Intent, Entities, Type)      │
└──────────────┬────────────────┘
               │
               ▼
┌───────────────────────────────┐
│ 2. Plan & Route Node          │
│ (Select Connectors)           │
└──────────────┬────────────────┘
               │
               ▼
┌───────────────────────────────┐ ◄────────────────┐
│ 3. Retrieve Evidence Node     │                  │
│ (Vector, BM25, SQL Agent)     │                  │ (Query Reformulation Loop)
└──────────────┬────────────────┘                  │
               │                                   │
               ▼                                   │
┌───────────────────────────────┐                  │
│ 4. Evaluate Sufficiency Node  ├─[ Insufficient ]─┘
└──────────────┬────────────────┘
               │
          [ Sufficient ]
               ▼
┌───────────────────────────────┐
│ 5. Conflict Detector          │
│ (Identify Contradictions)     │
└──────────────┬────────────────┘
               │
               ▼
┌───────────────────────────────┐
│ 6. Grounded Answer Generator  │
│ (Inline Citations & Output)   │
└───────────────────────────────┘
```

---

## 📁 Repository Structure

```
.
├── agents/                   # LangGraph state machine & agent nodes
│   ├── answer/               # Grounded answer generation & citation formatting
│   ├── conflict/             # Cross-source contradiction detection
│   ├── query_analyzer/       # Query intent, type, and entity extraction
│   ├── router/               # Multi-source query router
│   └── orchestrator.py       # LangGraph state graph definition
├── apps/
│   ├── api/                  # FastAPI backend (chat, sources, evaluation endpoints)
│   └── web/                  # Next.js frontend application & dashboard
├── connectors/               # Source connectors (PostgreSQL, GitHub, Web, Files)
├── database/                 # SQLAlchemy models, db session, and Alembic migrations
├── evaluation/               # RAG evaluation metrics & test harness
├── ingestion/                # File parsing, semantic chunking, embeddings & indexing
├── retrieval/                # Hybrid vector + lexical search & reranking modules
├── shared/                   # Global configuration settings and logging
├── tests/                    # Unit & integration tests
├── workers/                  # Background worker tasks (Celery/Redis)
├── docker-compose.yml        # Multi-container orchestration (API, Web, Postgres, Redis)
└── requirements.txt          # Python dependencies
```

---

## 🚀 Quick Start with Docker

### Prerequisites

- **Docker** and **Docker Compose** installed.
- (Optional) **OpenAI API Key** for LLM query synthesis & embeddings (mock fallbacks available for local testing).

### Run Containers

1. **Clone the repository**:
   ```bash
   git clone https://github.com/Jee123van456/Omni-RAG.git
   cd Omni-RAG
   ```

2. **Configure Environment Variables**:
   Copy `.env.example` to `.env` and fill in your keys:
   ```bash
   cp .env.example .env
   ```

3. **Start the Platform**:
   ```bash
   docker-compose up --build
   ```

4. **Access Applications**:
   - **Frontend UI**: [http://localhost:3000](http://localhost:3000)
   - **FastAPI API Documentation**: [http://localhost:8000/docs](http://localhost:8000/docs)
   - **API Health Check**: `GET http://localhost:8000/api/health`

---

## 🛠️ Manual Development Setup

### Backend Setup

1. **Create Virtual Environment**:
   ```bash
   python -m venv venv
   source venv/bin/activate
   ```

2. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Database Migrations**:
   ```bash
   alembic upgrade head
   ```

4. **Start API Server**:
   ```bash
   uvicorn apps.api.main:app --reload --port 8000
   ```

### Frontend Setup

1. **Navigate to Web directory**:
   ```bash
   cd apps/web
   ```

2. **Install & Run**:
   ```bash
   npm install
   npm run dev
   ```

---

## 🧪 Running Tests

Execute the full unit and integration test suite with `pytest`:

```bash
pytest tests/ -v
```

---

## 📡 Key API Endpoints

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/health` | Basic API uptime check |
| `GET` | `/api/health` | Comprehensive DB & Redis connectivity status |
| `POST` | `/api/chat` | Send question to LangGraph Agent pipeline |
| `GET` | `/api/sources` | List connected data sources |
| `POST` | `/api/sources` | Register a new data source (document, database, repo) |
| `POST` | `/api/evaluations/run` | Execute RAG benchmark evaluation suite |

---

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.
