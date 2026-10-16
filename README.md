# StoryGraph

A knowledge-graph narrative and mystery platform powered by **FalkorDB**, Cypher queries, spoiler-boundary validation, and interactive graph exploration.

---

## Architecture & Directory Structure

```text
storygraph/
├── README.md                   # Project overview & quickstart
├── docker-compose.yml          # FalkorDB service
├── .env.example                # FALKORDB_HOST/PORT & LLM key placeholders
├── .gitignore                  # Environment, cache, and artifact exclusions
├── data/
│   └── stories/
│       └── glass_orchard.json  # Original mystery graph specification (Part 2)
├── backend/
│   ├── pyproject.toml          # Packaging and backend dependencies
│   ├── requirements.txt        # Direct pip requirements
│   ├── app/
│   │   ├── config.py           # Environment variable loader
│   │   ├── db.py               # FalkorDB client & graph management
│   │   ├── models.py           # Pydantic entity and edge models
│   │   ├── graph/
│   │   │   ├── seed.py         # JSON → FalkorDB seeder
│   │   │   ├── queries.py      # Controlled Cypher query operations
│   │   │   └── spoiler.py      # Reveal-boundary rules & validation
│   │   ├── api/                # FastAPI routers (Phase 4)
│   │   └── llm/                # LLM agent integration (Phase 5)
│   └── tests/
│       ├── test_db_connection.py # Connection and smoke tests
├── frontend/                   # React + Vite + Cytoscape UI (Phase 6)
└── docs/
    ├── schema.md               # Node labels & edge specifications
    └── cypher_queries.md       # Cypher query references
```

---

## Prerequisites

- **Python**: 3.11+ (Current: Python 3.13)
- **Docker**: Docker Desktop with Compose support
- **Node.js**: v18+ (for upcoming Phase 6 frontend)

---

## FalkorDB Setup & Verification

### 1. Launch FalkorDB via Docker Compose
```bash
docker compose up -d
```
FalkorDB runs on `localhost:6379`.

### 2. Verify FalkorDB Module
Verify the container is healthy and the `graph` module is active:
```bash
docker exec storygraph-falkordb redis-cli PING
# Expected: PONG

docker exec storygraph-falkordb redis-cli MODULE LIST
# Expected: graph (/var/lib/falkordb/bin/falkordb.so)
```

### 3. Run Backend Smoke Test
Install backend dependencies and run pytest:
```bash
pip install -r backend/requirements.txt
pytest backend/tests -v
```
This runs `test_falkordb_ping` and `test_db_connection` (creates a throwaway graph, writes a node, queries it, and deletes the test graph).

---

## Cloud Deployment Target (Optional)
To use FalkorDB Cloud instead of local Docker, provide your credentials in `.env`:
```env
FALKORDB_HOST=your-cluster.falkordb.cloud
FALKORDB_PORT=6379
FALKORDB_PASSWORD=your_password
FALKORDB_USERNAME=default
```
