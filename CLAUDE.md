# CLAUDE.md — Budget Tracker

## What this project is

A personal budget tracker for Nidhi. Expenses are stored in a **Neo4j knowledge graph**. The UI is a **Streamlit** web dashboard. Everything runs via Docker.

## How to run

```bash
# Full Docker (recommended — starts Neo4j + app together)
docker-compose up --build

# Local dev (Neo4j in Docker, Streamlit on host)
docker-compose up -d neo4j
pip install -r requirements.txt
python run.py
```

Dashboard → http://localhost:8501  
Neo4j Browser → http://localhost:7474 (login: `neo4j` / `budgettracker123`)

## Project layout

```
app/
  database.py   — all Neo4j queries (the only file that touches the DB)
  main.py       — Streamlit UI, five pages, no business logic beyond formatting
Dockerfile
docker-compose.yml
requirements.txt
.env.example    — copy to .env for local dev; Docker uses env vars directly
run.py          — `python run.py` entry point (just launches streamlit)
```

## Key constants — change these first if needed

| Constant | File | Default | Purpose |
|----------|------|---------|---------|
| `CURRENCY` | `app/main.py:25` | `₹` | Symbol prepended to every amount |
| `DEFAULT_CATEGORIES` | `app/main.py:27` | Food, Education, Skincare… | Pre-populated category dropdown |
| `NEO4J_PASSWORD` | `.env` / `docker-compose.yml` | `budgettracker123` | Must match in both places |

## Neo4j credentials

Defined in two places — keep them in sync:
- `docker-compose.yml` → `NEO4J_AUTH` and `app.environment`
- `.env` (local dev only) → copied from `.env.example`

## Database layer rules

- **All** Cypher lives in `app/database.py`. Never write queries in `main.py`.
- `Database.__init__` retries the connection up to 10 times with a 5-second delay — needed because Neo4j takes ~30s to start in Docker.
- `_get_or_create_category` normalises category names with `.title()` — "food", "Food", "FOOD" all become the same node.
- Budget IDs are deterministic: `"{year}-{month:02d}::{CategoryName}"` — so `set_budget` is idempotent (safe to call multiple times).
- `get_spending_vs_budget` is computed in Python (two queries merged), not a single Cypher JOIN — keeps the query simple and handles categories that have expenses but no budget and vice versa.

## Streamlit patterns used

- `@st.cache_resource` on `get_db()` — creates one `Database` instance for the whole session.
- `get_db.clear()` is called after writing an expense to bust the cache so the dashboard reflects the new data immediately.
- Global `sel_year` / `sel_month` come from the sidebar and are used by every page function — they are module-level, not passed as arguments.
- No `st.session_state` is used for data; the DB is the single source of truth.

## Adding a new page

1. Write a `def show_yourpage():` function in `main.py`.
2. Add the page name to the `st.radio(...)` list in the sidebar section.
3. Add an `elif page == "Your Page": show_yourpage()` at the bottom router.

## Adding a new database query

1. Add a method to the `Database` class in `app/database.py`.
2. Call it from `main.py` — do not put Cypher inline in `main.py`.

## Docker notes

- Neo4j data is persisted in the `neo4j_data` Docker volume — expenses survive container restarts.
- The `app` service has `depends_on: neo4j: condition: service_healthy` so it won't start until Neo4j's HTTP port is reachable.
- To reset all data: `docker-compose down -v` (drops the volume).
