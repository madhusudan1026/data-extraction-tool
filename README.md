# UAE Credit Card Data Extraction Tool

Automated extraction of credit card benefits, entitlements, fees, and conditions from UAE bank websites using LLM-powered pipelines with vector-based semantic search.

## Architecture Overview

```
┌────────────────────────────────────────────────────────────┐
│  Frontend (React + Vite)                                   │
│  ExtractionWizard.jsx → V4 step-by-step workflow           │
│  Tabs: Enhanced Extraction | Single Card | Stored | History│
└────────────────┬───────────────────────────────────────────┘
                 │ HTTP
┌────────────────▼───────────────────────────────────────────┐
│  FastAPI Backend                                           │
│  ┌─────────────────┐  ┌──────────────────┐                 │
│  │ /api/v4/extraction│  │ /api/v4/vector   │                │
│  │  Sessions        │  │  Index, Search   │                │
│  │  Cards, URLs     │  │  RAG (/ask)      │                │
│  │  Pipelines       │  │  Stats, Health   │                │
│  └────────┬────────┘  └────────┬─────────┘                 │
│           │                    │                            │
│  ┌────────▼────────────────────▼─────────┐                 │
│  │  11 Extraction Pipelines              │                 │
│  │  cashback | lounge | golf | dining    │                 │
│  │  travel | insurance | rewards | fee   │                 │
│  │  lifestyle | movie | (base class)     │                 │
│  └────────┬──────────────────────────────┘                 │
│           │                                                │
│  ┌────────▼───────┐  ┌──────────┐  ┌──────────┐           │
│  │ Ollama (LLM)   │  │ ChromaDB │  │ MongoDB  │           │
│  │ phi/llama3.2   │  │ Vectors  │  │ Sessions │           │
│  │ nomic-embed    │  │ Chunks   │  │ Raw Data │           │
│  └────────────────┘  └──────────┘  └──────────┘           │
└────────────────────────────────────────────────────────────┘
```

### Key Modules

| Module | Location | Purpose |
|--------|----------|---------|
| `core/config.py` | Settings | All env-configurable settings (MongoDB, Redis, Ollama, ChromaDB) |
| `core/banks.py` | Bank registry | 10 UAE banks with domains, URL patterns, names |
| `services/ollama_client.py` | LLM client | Unified Ollama client with retry, semaphore, JSON parsing |
| `services/vector_store.py` | Vector DB | ChromaDB chunking, embedding, RAG queries |
| `pipelines/base_pipeline.py` | Pipeline core | Abstract base with run(), source processing, LLM extraction |
| `pipelines/models.py` | Data models | ExtractedBenefit, PipelineResult, ConfidenceLevel |
| `utils/content_processor.py` | Content prep | Noise removal, section scoring, relevance calculation |
| `utils/benefit_merger.py` | Post-processing | Deduplication (L1/L2), scoring, confidence calculation |
| `utils/deduplication.py` | Dedup engine | Within-source and cross-source benefit deduplication |

## Prerequisites

- **Docker** and **Docker Compose** (recommended), or:
  - Python 3.11+
  - Node.js 18+
  - MongoDB 7+
  - Redis 7+
- **Ollama** with models:
  ```bash
  ollama pull phi          # or llama3.2 for better quality
  ollama pull nomic-embed-text  # for vector embeddings
  ```

## Quick Start

### Docker (recommended)

```bash
cd project
docker compose up -d
```

Services start on:
- Frontend: http://localhost:5173
- Backend API: http://localhost:8000
- API Docs: http://localhost:8000/api/docs
- MongoDB: localhost:27017
- Redis: localhost:6379

### Manual Setup

**Backend:**
```bash
cd backend-python
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

**Frontend:**
```bash
cd frontend
npm install
npm run dev
```

### Environment Variables

Create `backend-python/.env`:
```env
MONGODB_URL=mongodb://localhost:27017
MONGODB_DB_NAME=credit_card_extraction
REDIS_URL=redis://localhost:6379
OLLAMA_BASE_URL=http://localhost:11434
DEFAULT_MODEL=phi
CHROMA_PERSIST_DIR=./chroma_data
VECTOR_AUTO_INDEX=true
```

## Extraction Workflow (V4)

The V4 workflow is a step-by-step process:

1. **Create Session** — `POST /api/v4/extraction/sessions`
2. **Discover Cards** — `POST /sessions/{id}/discover-cards` (auto-detects cards from bank URL)
3. **Select Cards** — `POST /sessions/{id}/select-cards`
4. **Discover URLs** — `POST /sessions/{id}/discover-urls` (finds benefit pages, T&C, PDFs)
5. **Select URLs** — `POST /sessions/{id}/select-urls`
6. **Fetch Content** — `POST /sessions/{id}/fetch-content` (scrapes and cleans content)
7. **Review & Approve** — `POST /sessions/{id}/approve-all-sources`
8. **Save Raw Data** — `POST /sessions/{id}/save-approved-raw` (also auto-indexes to vector store)
9. **Run Pipelines** — `POST /sessions/{id}/run-pipelines` (LLM + regex extraction per benefit type)
10. **View Results** — `GET /sessions/{id}/results`

## Vector Store / RAG

After Step 8, content is automatically chunked and embedded into ChromaDB. You can then:

- **Semantic search**: `POST /api/v4/vector/search` — find relevant chunks by natural language
- **RAG query**: `POST /api/v4/vector/ask` — ask questions and get LLM-synthesized answers

Example RAG query:
```json
POST /api/v4/vector/ask
{
  "question": "Which Emirates NBD cards offer airport lounge access?",
  "bank_key": "emirates_nbd",
  "n_chunks": 10
}
```

## API Reference

### Extraction Endpoints (`/api/v4/extraction`)
| Method | Path | Description |
|--------|------|-------------|
| POST | `/sessions` | Create new extraction session |
| POST | `/sessions/{id}/discover-cards` | Auto-detect cards from bank URL |
| POST | `/sessions/{id}/select-cards` | Select cards for extraction |
| POST | `/sessions/{id}/discover-urls` | Find related benefit pages |
| POST | `/sessions/{id}/select-urls` | Select URLs to scrape |
| POST | `/sessions/{id}/fetch-content` | Scrape and clean content |
| POST | `/sessions/{id}/approve-all-sources` | Approve all fetched sources |
| POST | `/sessions/{id}/save-approved-raw` | Save to DB + auto-index vectors |
| POST | `/sessions/{id}/run-pipelines` | Run extraction pipelines |
| GET | `/sessions/{id}/results` | View extraction results |
| GET | `/banks` | List supported banks |
| GET | `/pipelines` | List available pipelines |

### Vector Store Endpoints (`/api/v4/vector`)
| Method | Path | Description |
|--------|------|-------------|
| POST | `/index` | Index approved raw data |
| POST | `/index-session/{id}` | Index by session ID |
| POST | `/search` | Semantic search chunks |
| POST | `/ask` | RAG query (retrieve + generate) |
| GET | `/stats` | Collection statistics |
| GET | `/health` | ChromaDB + embedding health |
| POST | `/reset` | Reset vector collection |
| DELETE | `/card/{name}` | Delete card vectors |

## Pipeline Reference

| Pipeline | Benefit Type | Description |
|----------|-------------|-------------|
| cashback | cashback | Cashback rates, categories, caps |
| lounge_access | lounge | Airport lounge access, Priority Pass |
| golf | golf | Golf privileges, courses, green fees |
| dining | dining | Dining offers, BOGO, restaurant partnerships |
| travel | travel | Travel benefits, airline miles, hotel bookings |
| insurance | insurance | Travel/purchase/card protection coverage |
| rewards_points | rewards | Points earning rates, redemption options |
| fee_waiver | fee | Fee waivers, annual fee conditions |
| lifestyle | lifestyle | Valet, concierge, spa, fitness benefits |
| movie | movie | Cinema offers, VOX/Reel/Novo partnerships |

## Project Structure

```
project/
├── backend-python/
│   ├── app/
│   │   ├── api/routes/          # API endpoints (V2, V4, vector)
│   │   ├── core/                # Config, database, banks, exceptions
│   │   ├── middleware/          # Error handling, rate limiting
│   │   ├── models/              # MongoDB document models
│   │   ├── pipelines/           # 10 extraction pipelines + base class
│   │   ├── schemas/             # Pydantic request/response schemas
│   │   ├── services/            # Business logic (LLM, scraping, vector store)
│   │   └── utils/               # Deduplication, content processing, sanitization
│   ├── requirements.txt
│   └── .env
├── frontend/
│   ├── src/
│   │   ├── components/          # React components
│   │   ├── services/            # API client
│   │   └── App.jsx
│   └── package.json
├── docker-compose.yml
└── README.md
```
