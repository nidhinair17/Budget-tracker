# Architecture — Budget Tracker

## Overview

```
┌─────────────────────────────────────────────────────────────────┐
│  Browser  (http://localhost:8501)                               │
└────────────────────────┬────────────────────────────────────────┘
                         │  HTTP
┌────────────────────────▼────────────────────────────────────────┐
│  Streamlit app  (app/main.py)                                   │
│  • 5 pages: Dashboard, Add Expense, Set Budget, Analytics,      │
│    History                                                       │
│  • Plotly charts, pandas DataFrames                             │
│  • Single cached Database instance (@st.cache_resource)        │
└────────────────────────┬────────────────────────────────────────┘
                         │  Python calls
┌────────────────────────▼────────────────────────────────────────┐
│  Database layer  (app/database.py)                              │
│  • Class: Database                                              │
│  • All Cypher queries live here                                 │
│  • Connection retry loop (10 × 5s) for Docker startup delay    │
└────────────────────────┬────────────────────────────────────────┘
                         │  Bolt protocol  (port 7687)
┌────────────────────────▼────────────────────────────────────────┐
│  Neo4j 5.15  (Docker container: budget_neo4j)                  │
│  • Knowledge graph database                                     │
│  • Data persisted to Docker volume: neo4j_data                 │
│  • Browser UI at http://localhost:7474                         │
└─────────────────────────────────────────────────────────────────┘
```

## Knowledge Graph Schema

Neo4j stores data as **nodes** (entities) and **relationships** (edges). This is better than a relational DB here because expenses naturally form a graph: they connect categories, months, and budgets in multiple directions — all traversable without JOINs.

### Nodes

| Label | Properties | Unique constraint |
|-------|-----------|-------------------|
| `Expense` | `id` (UUID), `amount` (float), `description` (str), `date` (ISO string), `created_at` (datetime) | `id` |
| `Category` | `name` (title-cased string, e.g. `"Food"`) | `name` |
| `Month` | `key` (e.g. `"2026-04"`), `year` (int), `month` (int), `name` (e.g. `"April 2026"`) | `key` |
| `Budget` | `id` (e.g. `"2026-04::Food"`), `amount` (float), `updated_at` (datetime) | `id` |

### Relationships

```
(:Expense)-[:BELONGS_TO]->(:Category)
(:Expense)-[:RECORDED_IN]->(:Month)
(:Budget)-[:FOR_CATEGORY]->(:Category)
(:Budget)-[:FOR_MONTH]->(:Month)
```

### Visual graph for one month

```
         ┌──────────┐
         │  April   │◄──RECORDED_IN──┐
         │  2026    │                │
         └──────────┘                │
              ▲                      │
          FOR_MONTH               (:Expense amount=450)
              │                      │
         ┌──────────┐                │ BELONGS_TO
         │  Budget  │            FOR_CATEGORY
         │ amount=  │                ▼
         │  3000    ├──FOR_CATEGORY──►(:Category name="Food")
         └──────────┘                ▲
                                     │ BELONGS_TO
                              (:Expense amount=200)
                                     │
                              RECORDED_IN
                                     │
                               (:Month "April 2026")
```

### Why a graph for this?

- Querying "all Food expenses in April" is a natural graph traversal, not a multi-table JOIN.
- Adding a new dimension (e.g. linking expenses to a `:Merchant` node) requires zero schema migration.
- The Category node is shared across all months — renaming a category propagates everywhere automatically.

## Data flow per operation

### Add Expense
```
User fills form
  → main.py: db.add_expense(amount, category, description, date)
    → database.py: MERGE Category node (create if first time)
    → database.py: MERGE Month node (create if first time)
    → database.py: CREATE Expense node
    → database.py: CREATE (Expense)-[:BELONGS_TO]->(Category)
    → database.py: CREATE (Expense)-[:RECORDED_IN]->(Month)
  → main.py: st.cache_resource cleared → DB reconnects fresh
```

### Dashboard load
```
Sidebar: sel_year, sel_month chosen
  → show_dashboard() called
    → db.get_spending_vs_budget(year, month)
        → db.get_budget_for_month()    → Cypher: Budget→Month + Budget→Category
        → db.get_monthly_summary()     → Cypher: Expense→Month + Expense→Category
        → Python merge: union of all categories, compute remaining + pct_used
    → db.get_daily_spending(year, month) → Cypher aggregation by date
    → db.get_expenses_for_month(year, month) → recent 10 rows
  → Plotly renders donut chart, horizontal bar chart, bar chart
```

### Analytics — Increasing Expenses
```
sel_year / sel_month selected
  → db.get_monthly_summary(year, month)      → current month totals
  → db.get_monthly_summary(prev_year, prev_month) → previous month totals
  → Python: compute pct_change per category
  → Alert boxes for categories with >20% increase
  → Plotly bar chart coloured red (increase) / green (decrease)
```

## File responsibilities

| File | Responsibility | Must NOT do |
|------|---------------|-------------|
| `app/database.py` | All Cypher, connection management, schema init | Streamlit imports, UI logic |
| `app/main.py` | UI layout, charts, form handling, routing | Write Cypher directly |
| `run.py` | Entry point, prints startup message | Application logic |
| `docker-compose.yml` | Service wiring, volume mapping, health checks | — |
| `Dockerfile` | Build the Python image | — |

## Docker services

```
docker-compose.yml
├── neo4j          image: neo4j:5.15
│   ├── ports:     7474 (HTTP browser), 7687 (Bolt)
│   ├── volumes:   neo4j_data (persists graph), neo4j_logs
│   └── healthcheck: wget http://localhost:7474 every 10s
│
└── app            build: . (Dockerfile)
    ├── ports:     8501 (Streamlit)
    ├── env:       NEO4J_URI / USER / PASSWORD
    └── depends_on: neo4j (waits for healthy status)
```

## Technology choices

| Technology | Version | Why |
|-----------|---------|-----|
| Python | 3.11 | Type hint syntax (`list[dict]`, `X \| Y`) requires ≥3.10 |
| Neo4j | 5.15 | LTS release; `IF NOT EXISTS` constraint syntax |
| neo4j driver | 5.18 | Matches Neo4j 5.x server protocol |
| Streamlit | 1.32 | `@st.cache_resource`, `st.progress(text=...)` available |
| Plotly | 5.20 | Interactive charts with minimal code via `plotly.express` |
| pandas | 2.2 | DataFrame manipulation for chart data prep |
| python-dotenv | 1.0 | `.env` file support for local dev |

## Extending the app

### Add a new category permanently
Edit `DEFAULT_CATEGORIES` list in `app/main.py:27`. No DB change needed — categories are created on first use.

### Change currency symbol
Edit `CURRENCY = "₹"` in `app/main.py:25`.

### Add a new chart / analytic
1. Add a query method to `Database` in `app/database.py`.
2. Call it inside the relevant `show_*()` function in `app/main.py`.

### Add a new page
1. Write `def show_newpage(): ...` in `app/main.py`.
2. Add the name to `st.radio(...)` in the sidebar block.
3. Add `elif page == "New Page": show_newpage()` at the bottom router.

### Connect to a remote Neo4j (e.g. Neo4j Aura)
Change `NEO4J_URI` in `.env` to your Aura connection string. No code changes needed.
