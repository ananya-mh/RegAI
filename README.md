# RegAI

AI regulatory compliance automation engine. Multi-agent system that ingests regulatory documents (GDPR, SOC 2, HIPAA), performs gap analysis via RAG, and generates audit-ready compliance reports with citations.

## Architecture

```mermaid
graph LR
    FE[Next.js Frontend] --> API[FastAPI Backend]
    API --> SV[Supervisor Agent]
    SV --> INT[Interpreter]
    INT --> GA[Gap Analyzer]
    GA --> RP[Remediation Planner]
    RP --> RW[Report Writer]
    
    INT --> MCP[MCP Server]
    GA --> MCP
    RP --> MCP
    RW --> MCP
    
    MCP --> PG[(PostgreSQL)]
    MCP --> FAISS[(FAISS)]
    MCP --> CH[(Chroma)]
    
    GA --> Gemini[Gemini 2.0 Flash]
    INT --> Gemini
    SV --> Ollama[Ollama / Llama 3]
    RP --> Ollama
    
    API -->|SSE| FE
```

## Features

- Multi-agent compliance pipeline (Supervisor, Interpreter, Gap Analyzer, Remediation Planner, Report Writer)
- Dual RAG pipeline: FAISS (regulations) + Chroma (policies) with cross-encoder re-ranking
- Legal-structure-aware chunking preserving regulation hierarchy
- Semantic policy chunking with topic-shift detection
- DOCX and PDF report generation with citations
- Streaming chat via SSE with real-time gap assessments
- MCP server with 6 tools, 3 resources, 3 prompt templates
- Dual LLM routing: Gemini (primary) + Ollama/Llama 3 (fallback)
- Per-call cost tracking and usage analytics
- Evaluation harness with 30 ground truth pairs and faithfulness scoring

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | FastAPI, Python 3.12, Pydantic v2 |
| Agents | LangGraph StateGraph, LangChain |
| RAG | FAISS + Chroma, bge-base-en-v1.5, bge-reranker-base |
| MCP | TypeScript, @modelcontextprotocol/sdk, Streamable HTTP |
| Frontend | Next.js 15, React 19, TailwindCSS, shadcn/ui |
| Database | PostgreSQL 16 |
| LLMs | Gemini 2.0 Flash, Ollama + Llama 3 8B |
| Reports | python-docx, WeasyPrint |
| Observability | LangSmith, Prometheus, custom eval harness |
| CI/CD | GitHub Actions, Docker Compose |

## Quick Start

### Prerequisites

- Docker and Docker Compose
- (Optional) Gemini API key for primary LLM

### Run with Docker

```bash
cp .env.example .env
# Edit .env — add GEMINI_API_KEY if available
docker compose -f docker/docker-compose.yml up
```

Services start at:
- Frontend: http://localhost:3001
- API: http://localhost:8000
- MCP Server: http://localhost:3000
- API Docs: http://localhost:8000/docs

### Local Development

```bash
# Backend
pip install -e ".[dev]"
uvicorn backend.main:app --reload --port 8000

# Frontend
cd frontend && npm install && npm run dev

# MCP Server
cd mcp-server && npm install && npm run dev
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL async connection | `postgresql+asyncpg://postgres:postgres@localhost:5432/complianceforge` |
| `GEMINI_API_KEY` | Google Gemini API key | (empty) |
| `GEMINI_MODEL` | Gemini model name | `gemini-2.0-flash` |
| `OLLAMA_BASE_URL` | Ollama server URL | `http://localhost:11434` |
| `OLLAMA_MODEL` | Ollama model name | `llama3:8b` |
| `CHROMA_HOST` | Chroma server host | `localhost` |
| `CHROMA_PORT` | Chroma server port | `8001` |
| `MCP_SERVER_URL` | MCP server URL | `http://localhost:3000` |
| `LLM_MAX_RETRIES` | Retry count before fallback | `1` |
| `LLM_TIMEOUT_SECONDS` | LLM call timeout | `60` |

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check |
| `POST` | `/api/chat` | Chat with SSE streaming |
| `POST` | `/api/policies/upload` | Upload PDF/DOCX policy |
| `GET` | `/api/policies` | List uploaded policies |
| `GET` | `/api/frameworks` | List regulatory frameworks |
| `GET` | `/api/frameworks/{id}/status` | Framework compliance status |
| `GET` | `/api/gaps` | List compliance gaps (filterable) |
| `POST` | `/api/gaps/{id}/remediation` | Create remediation task |
| `GET` | `/api/gaps/remediation` | List remediation tasks |
| `GET` | `/api/usage` | LLM cost tracking summary |
| `POST` | `/api/internal/analyze-gap` | Cross-index gap analysis (MCP) |
| `POST` | `/api/internal/search-policies` | Semantic policy search (MCP) |
| `POST` | `/api/internal/generate-report-section` | Report generation (MCP) |

## Project Structure

```
backend/
  api/          Route handlers (chat, frameworks, gaps, policies, usage, internal)
  agents/       LangGraph agents (supervisor, interpreter, gap_analyzer, remediation_planner, report_writer)
  evals/        Evaluation harness (ground truth, faithfulness, citation accuracy, metrics)
  ingestion/    Regulatory text parsers (GDPR, SOC 2)
  models/       SQLAlchemy ORM models
  rag/          Chunking, embedding, retrieval, re-ranking, vector stores
  services/     Database, config, LLM service, MCP client, report renderer
mcp-server/     TypeScript MCP server (tools, resources, prompts)
frontend/       Next.js app (dashboard, gaps, chat, policies, remediation)
docker/         Dockerfiles and docker-compose.yml
tests/          Unit and integration tests
```

## Testing

```bash
# Run all tests (skip model-loading tests without GPU)
pytest tests/ -v --ignore=tests/unit/test_chunking.py --ignore=tests/unit/test_retrieval.py

# Run only integration tests
pytest tests/integration/ -v

# Run only unit tests
pytest tests/unit/test_schemas.py tests/unit/test_llm_service.py tests/unit/test_mcp_client.py -v
```

---

*AI-generated compliance assessments are for informational purposes only and do not constitute legal advice.*
