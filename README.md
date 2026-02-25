# UAE Credit Card Data Extraction Tool

Automated extraction of credit card benefits, entitlements, fees, and conditions from UAE bank websites using LLM-powered pipelines with vector-based semantic search.

## Architecture

```
Browser → :80 Nginx ─┬── /api/* ──→ FastAPI Backend (:8000)
                      └── /*     ──→ React Frontend (static)

Backend ──→ MongoDB    (sessions, cards, sections, approved data)
        ──→ Redis      (scrape + LLM response cache)
        ──→ Ollama     (phi LLM + nomic-embed-text embeddings)
        ──→ ChromaDB   (vectorized content chunks)
        ──→ Playwright (headless Chromium for JS-rendered bank sites)
```

### Services

| Service | Purpose |
|---------|---------|
| **Frontend** | React + Vite SPA — 4 tabs for extraction, data store, pipelines, and system admin |
| **Backend** | FastAPI — V5 structured extraction, vectorization, pipeline execution |
| **MongoDB** | Stores sessions, discovered cards, page sections, approved raw data, pipeline results |
| **Redis** | Caches scraped pages and LLM responses to avoid redundant work |
| **Ollama** | Local LLM inference (phi) and text embeddings (nomic-embed-text) |
| **ChromaDB** | Vector store embedded in backend — chunks indexed with hierarchical metadata |

## Quick Start

### Docker (Recommended)

```bash
# 1. Clone and enter the project
cd data-extraction-tool

# 2. Copy and edit config
cp .env.example .env

# 3. Deploy everything (builds images, pulls Ollama models)
chmod +x deploy.sh
./deploy.sh

# 4. Open in browser
open http://localhost
```

The deploy script builds all containers, starts MongoDB/Redis/Ollama, pulls the required LLM models (`phi` and `nomic-embed-text`), then starts the full stack.

### Manual / Local Development

**Prerequisites:** Python 3.11+, Node.js 18+, MongoDB 7+, Redis 7+, Ollama

```bash
# Backend
cd backend-python
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
playwright install chromium
uvicorn app.main:app --reload --port 8000

# Frontend (separate terminal)
cd frontend
npm install
npm run dev

# Ollama models (separate terminal)
ollama pull llama3.2
ollama pull nomic-embed-text
```

- Frontend: http://localhost:5173
- Backend API: http://localhost:8000
- API Docs: http://localhost:8000/docs

### Environment Variables

Create `backend-python/.env` for local dev, or set in `docker-compose.yml` for Docker:

```env
MONGODB_URL=mongodb://localhost:27017
MONGODB_DATABASE=credit_card_extraction
REDIS_URL=redis://localhost:6379
OLLAMA_BASE_URL=http://localhost:11434
DEFAULT_MODEL=llama3.2
CHROMA_PERSIST_DIR=./chroma_data
EMBED_MODEL=nomic-embed-text
CORS_ORIGINS=http://localhost:5173,http://localhost:3000
LOG_LEVEL=INFO
```

## UI Tabs

### 1. Structured Extraction (V5)

The primary extraction interface with two modes:

**Bank-Wide Discovery** — Select a preconfigured UAE bank (Emirates NBD, FAB, ADCB, Mashreq) or enter a custom bank URL. Depth 0 crawls the bank's cards listing page and discovers all credit cards with metadata.

**Single Card URL** — Paste a direct card page URL for targeted extraction. Auto-detects bank and card name from the page.

**Workflow:**
1. **Step 1** — Choose mode, select bank or enter URL, configure options (Playwright, max depth)
2. **Step 2** — Review discovered cards, select which to process → Depth 1 extracts page sections
3. **Step 3** — Review card sections, manage deep links → Depth 2-3 processes shared benefit pages (golf, lounge, etc.)
4. **Step 4** — Review all extracted sections, approve/reject → Store to DataStore

Each depth level caches results to avoid redundant scraping. Playwright handles JS-rendered pages with smart scrolling for lazy-loaded content.

### 2. Data Store & Vectorization

View all stored card data (`approved_raw_data` collection). For each record:

- **Preview chunks** — See how content will be split into vector chunks with metadata
- **Index into ChromaDB** — Embed chunks using Ollama's `nomic-embed-text` model
- **Clear old vectors** — Toggle to remove stale data from previous extractions before re-indexing
- **Browse by category** — View chunks grouped by benefit type (cashback, lounge, golf, etc.)

### 3. Pipeline Execution

Run specialized extraction pipelines on vectorized data:

1. Select a bank and card (auto-loads from V5, V4, and vectorized records)
2. View vector chunks grouped by category
3. Select pipelines to run (or run all)
4. Review extracted benefits with confidence scores, conditions, merchants

### 4. History

Browse all past extraction sessions with metadata.

### 5. System (Admin)

Full cleanup panel for fresh starts:

- Selective deletion by group (V5, V4, V2, DataStore, ChromaDB, Pipelines, Redis)
- Shows document counts per collection
- Requires typing "DELETE ALL" to confirm
- Detailed report of what was deleted

## Extraction Pipelines

| Pipeline | Type | What It Extracts |
|----------|------|------------------|
| `cashback` | cashback | Cashback rates, categories, caps, minimum spend |
| `lounge_access` | lounge | Airport lounge access, Priority Pass, guest policies |
| `golf` | golf | Golf privileges, courses, green fee waivers |
| `dining` | dining | Dining offers, BOGO deals, restaurant partnerships |
| `travel` | travel | Travel benefits, airline miles, hotel bookings |
| `insurance` | insurance | Travel/purchase/card protection coverage |
| `rewards_points` | rewards | Points earning rates, redemption options |
| `fee_waiver` | fee | Annual fee waivers, conditions, thresholds |
| `lifestyle` | lifestyle | Valet, concierge, spa, fitness benefits |
| `movie` | movie | Cinema offers, VOX/Reel/Novo partnerships |

Each pipeline uses a hybrid approach: LLM extraction (Ollama) combined with regex pattern matching, followed by deduplication and confidence scoring.

## API Reference

### V5 Structured Extraction (`/api/v5/extraction`)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/sessions` | Create session (bank-wide or single card mode) |
| GET | `/sessions/{id}` | Get session status |
| POST | `/sessions/{id}/select-cards` | Select cards for processing |
| POST | `/sessions/{id}/process-depth1` | Extract depth 1 card page sections |
| POST | `/sessions/{id}/process-depth2` | Process depth 2-3 shared benefit pages |
| POST | `/sessions/{id}/store-approved` | Store approved data to DataStore |
| GET | `/sessions/{id}/depth2-sections` | View depth 2-3 extracted sections |
| POST | `/system/cleanup` | Full system cleanup (selective) |
| GET | `/system/stats` | Document counts for all collections |

### Vector Store (`/api/v4/vector`)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/index-record` | Index approved data into ChromaDB |
| GET | `/record-data/{id}` | View indexed chunks for a record |
| GET | `/card-chunks/{name}` | Get all chunks for a card (multi-strategy match) |
| GET | `/banks` | List all banks with discovered cards |
| POST | `/search` | Semantic search chunks |
| POST | `/ask` | RAG query (retrieve + LLM answer) |
| GET | `/stats` | Collection statistics |
| POST | `/reset` | Reset entire vector collection |

### Pipeline Execution (`/api/v2/extraction`)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/pipelines/run-all/{id}` | Run selected pipelines on a record |
| GET | `/pipelines/results/{id}` | Get stored pipeline results |
| GET | `/pipelines` | List available pipelines |
| GET | `/approved-raw` | List all approved raw data records |

## Supported Banks

| Bank | Key | JS Required |
|------|-----|-------------|
| Emirates NBD | `emirates_nbd` | Yes |
| First Abu Dhabi Bank | `fab` | Yes |
| Abu Dhabi Commercial Bank | `adcb` | Yes |
| Mashreq Bank | `mashreq` | Yes |
| Custom URL | `custom` | Configurable |

## Project Structure

```
project/
├── docker-compose.yml              # All 6 services
├── deploy.sh                       # One-command deployment
├── setup-ssl.sh                    # HTTPS with Let's Encrypt
├── .env.example                    # Config template
├── nginx/
│   └── default.conf                # Reverse proxy config
│
├── backend-python/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── app/
│   │   ├── main.py                 # FastAPI app + lifespan
│   │   ├── api/routes/
│   │   │   ├── extraction_structured.py  # V5 endpoints + system cleanup
│   │   │   ├── extraction_v2.py          # Pipeline execution endpoints
│   │   │   └── vector_routes.py          # ChromaDB indexing + search
│   │   ├── core/
│   │   │   ├── config.py           # All env-configurable settings
│   │   │   ├── banks.py            # UAE bank registry + card metadata detection
│   │   │   └── database.py         # MongoDB connection
│   │   ├── services/
│   │   │   ├── playwright_scraper.py     # Shared Playwright utility
│   │   │   ├── interactive_scraper.py    # Click-through scraping with expandables
│   │   │   ├── structured_scraper.py     # Card discovery + page sectioning
│   │   │   ├── vector_store.py           # ChromaDB chunking + embedding
│   │   │   └── ollama_client.py          # LLM client with retry + JSON parsing
│   │   ├── pipelines/
│   │   │   ├── base_pipeline.py    # Abstract pipeline with LLM + regex extraction
│   │   │   ├── models.py           # ExtractedBenefit, PipelineResult, ConfidenceLevel
│   │   │   ├── pipeline_registry.py # Pipeline orchestrator + deduplication
│   │   │   └── (10 pipeline modules)
│   │   └── utils/
│   │       ├── benefit_merger.py   # Cross-pipeline deduplication + scoring
│   │       └── content_processor.py # Text cleaning + relevance scoring
│   └── chroma_data/                # ChromaDB persistence (Docker volume)
│
└── frontend/
    ├── Dockerfile
    ├── nginx-frontend.conf         # SPA routing
    ├── src/
    │   ├── config.js               # API URL configuration
    │   ├── App.jsx                 # Tab layout (all tabs stay mounted)
    │   └── components/
    │       ├── StructuredExtractionWizard.jsx  # V5 extraction flow
    │       ├── DataStoreVectorization.jsx      # Data store + ChromaDB indexing
    │       ├── PipelineExecution.jsx           # Pipeline runner
    │       ├── ExtractionsList.jsx             # History browser
    │       └── SystemCleanup.jsx               # Admin cleanup panel
    └── package.json
```

## Production Deployment

### VPS with Docker Compose

```bash
# On a VPS (Ubuntu recommended, 4+ vCPU, 8+ GB RAM)
./deploy.sh

# Add HTTPS
./setup-ssl.sh yourdomain.com
```

### GPU Support (faster Ollama)

Uncomment the GPU section in `docker-compose.yml` under the `ollama` service:

```yaml
deploy:
  resources:
    reservations:
      devices:
        - driver: nvidia
          count: all
          capabilities: [gpu]
```

### Useful Commands

```bash
docker compose logs -f backend      # Follow backend logs
docker compose logs -f ollama       # Follow Ollama logs
docker compose exec mongo mongosh   # MongoDB shell
docker compose down                 # Stop all services
docker compose down -v              # Stop + delete all data
docker compose up -d --build        # Rebuild and restart
```
