"""
Neo4j Knowledge Graph layer for the Budget Tracker.

Graph schema
------------
Nodes   : (:Expense), (:Category), (:Month), (:Budget)
Edges   : (Expense)-[:BELONGS_TO]->(Category)
          (Expense)-[:RECORDED_IN]->(Month)
          (Budget)-[:FOR_CATEGORY]->(Category)
          (Budget)-[:FOR_MONTH]->(Month)
"""

import os
import time
import uuid
from datetime import date

from dotenv import load_dotenv
from neo4j import GraphDatabase
from neo4j.exceptions import ServiceUnavailable

load_dotenv()

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "budgettracker123")

MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


class Database:
    def __init__(self, max_retries: int = 10, retry_delay: int = 5):
        self.driver = None
        last_error = None
        for attempt in range(1, max_retries + 1):
            try:
                self.driver = GraphDatabase.driver(
                    NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD)
                )
                self.driver.verify_connectivity()
                self._init_schema()
                return
            except ServiceUnavailable as exc:
                last_error = exc
                if attempt < max_retries:
                    time.sleep(retry_delay)
            except Exception as exc:
                last_error = exc
                if attempt < max_retries:
                    time.sleep(retry_delay)

        raise ConnectionError(
            f"Could not connect to Neo4j at {NEO4J_URI} after {max_retries} attempts. "
            f"Last error: {last_error}"
        )

    def close(self):
        if self.driver:
            self.driver.close()

    # ------------------------------------------------------------------
    # Schema initialisation
    # ------------------------------------------------------------------

    def _init_schema(self):
        constraints = [
            "CREATE CONSTRAINT expense_id IF NOT EXISTS FOR (e:Expense) REQUIRE e.id IS UNIQUE",
            "CREATE CONSTRAINT category_name IF NOT EXISTS FOR (c:Category) REQUIRE c.name IS UNIQUE",
            "CREATE CONSTRAINT month_key IF NOT EXISTS FOR (m:Month) REQUIRE m.key IS UNIQUE",
            "CREATE CONSTRAINT budget_id IF NOT EXISTS FOR (b:Budget) REQUIRE b.id IS UNIQUE",
        ]
        with self.driver.session() as session:
            for cql in constraints:
                session.run(cql)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_or_create_category(self, session, name: str) -> str:
        norm = name.strip().title()
        session.run("MERGE (:Category {name: $name})", name=norm)
        return norm

    def _get_or_create_month(self, session, year: int, month: int) -> str:
        key = f"{year}-{month:02d}"
        session.run(
            """
            MERGE (m:Month {key: $key})
            ON CREATE SET m.year = $year, m.month = $month, m.name = $name
            """,
            key=key,
            year=year,
            month=month,
            name=f"{MONTH_NAMES[month - 1]} {year}",
        )
        return key

    # ------------------------------------------------------------------
    # Expenses
    # ------------------------------------------------------------------

    def add_expense(
        self,
        amount: float,
        category: str,
        description: str,
        expense_date: date,
    ) -> str:
        expense_id = str(uuid.uuid4())
        with self.driver.session() as session:
            cat_name = self._get_or_create_category(session, category)
            month_key = self._get_or_create_month(session, expense_date.year, expense_date.month)
            session.run(
                """
                MATCH (c:Category {name: $cat})
                MATCH (m:Month    {key:  $mkey})
                CREATE (e:Expense {
                    id:          $id,
                    amount:      $amount,
                    description: $desc,
                    date:        $date,
                    created_at:  datetime()
                })
                CREATE (e)-[:BELONGS_TO]->(c)
                CREATE (e)-[:RECORDED_IN]->(m)
                """,
                id=expense_id,
                amount=float(amount),
                desc=description.strip(),
                date=expense_date.isoformat(),
                cat=cat_name,
                mkey=month_key,
            )
        return expense_id

    def delete_expense(self, expense_id: str) -> bool:
        with self.driver.session() as session:
            result = session.run(
                "MATCH (e:Expense {id: $id}) DETACH DELETE e RETURN count(e) AS n",
                id=expense_id,
            )
            return result.single()["n"] > 0

    def get_expenses_for_month(self, year: int, month: int) -> list[dict]:
        key = f"{year}-{month:02d}"
        with self.driver.session() as session:
            result = session.run(
                """
                MATCH (e:Expense)-[:RECORDED_IN]->(m:Month {key: $key})
                MATCH (e)-[:BELONGS_TO]->(c:Category)
                RETURN e.id AS id, e.amount AS amount,
                       e.description AS description, e.date AS date,
                       c.name AS category
                ORDER BY e.date DESC, e.created_at DESC
                """,
                key=key,
            )
            return [dict(r) for r in result]

    def get_all_expenses(self, limit: int = 200) -> list[dict]:
        with self.driver.session() as session:
            result = session.run(
                """
                MATCH (e:Expense)-[:BELONGS_TO]->(c:Category)
                MATCH (e)-[:RECORDED_IN]->(m:Month)
                RETURN e.id AS id, e.amount AS amount,
                       e.description AS description, e.date AS date,
                       c.name AS category, m.name AS month_name,
                       m.year AS year, m.month AS month
                ORDER BY e.date DESC, e.created_at DESC
                LIMIT $limit
                """,
                limit=limit,
            )
            return [dict(r) for r in result]

    def get_monthly_summary(self, year: int, month: int) -> list[dict]:
        """Returns [{category, total, count}] sorted by total desc."""
        key = f"{year}-{month:02d}"
        with self.driver.session() as session:
            result = session.run(
                """
                MATCH (e:Expense)-[:RECORDED_IN]->(m:Month {key: $key})
                MATCH (e)-[:BELONGS_TO]->(c:Category)
                RETURN c.name AS category,
                       sum(e.amount)  AS total,
                       count(e)       AS count
                ORDER BY total DESC
                """,
                key=key,
            )
            return [dict(r) for r in result]

    # ------------------------------------------------------------------
    # Budgets
    # ------------------------------------------------------------------

    def set_budget(self, year: int, month: int, category: str, amount: float):
        with self.driver.session() as session:
            cat_name = self._get_or_create_category(session, category)
            month_key = self._get_or_create_month(session, year, month)
            budget_id = f"{month_key}::{cat_name}"
            session.run(
                """
                MATCH (c:Category {name: $cat})
                MATCH (m:Month    {key:  $mkey})
                MERGE (b:Budget {id: $bid})
                SET   b.amount = $amount, b.updated_at = datetime()
                MERGE (b)-[:FOR_CATEGORY]->(c)
                MERGE (b)-[:FOR_MONTH]->(m)
                """,
                cat=cat_name,
                mkey=month_key,
                bid=budget_id,
                amount=float(amount),
            )

    def get_budget_for_month(self, year: int, month: int) -> list[dict]:
        key = f"{year}-{month:02d}"
        with self.driver.session() as session:
            result = session.run(
                """
                MATCH (b:Budget)-[:FOR_MONTH]->(m:Month {key: $key})
                MATCH (b)-[:FOR_CATEGORY]->(c:Category)
                RETURN c.name AS category, b.amount AS budget
                ORDER BY c.name
                """,
                key=key,
            )
            return [dict(r) for r in result]

    def get_spending_vs_budget(self, year: int, month: int) -> list[dict]:
        """Merge budget and actual spending per category for a month."""
        budgets = {r["category"]: r["budget"] for r in self.get_budget_for_month(year, month)}
        actuals = {r["category"]: r["total"] for r in self.get_monthly_summary(year, month)}
        all_cats = set(budgets) | set(actuals)
        rows = []
        for cat in sorted(all_cats):
            b = budgets.get(cat, 0.0)
            s = actuals.get(cat, 0.0)
            rows.append(
                {
                    "category": cat,
                    "budget": b,
                    "spent": s,
                    "remaining": b - s,
                    "pct_used": round(s / b * 100, 1) if b > 0 else None,
                }
            )
        return sorted(rows, key=lambda x: x["spent"], reverse=True)

    # ------------------------------------------------------------------
    # Trend / analytics queries
    # ------------------------------------------------------------------

    def get_monthly_totals(self, limit: int = 12) -> list[dict]:
        """Returns [{year, month, month_name, total}] newest first."""
        with self.driver.session() as session:
            result = session.run(
                """
                MATCH (e:Expense)-[:RECORDED_IN]->(m:Month)
                RETURN m.year AS year, m.month AS month,
                       m.name AS month_name, sum(e.amount) AS total
                ORDER BY m.year DESC, m.month DESC
                LIMIT $limit
                """,
                limit=limit,
            )
            return [dict(r) for r in result]

    def get_category_trend(self) -> list[dict]:
        """Returns [{year, month, month_name, category, total}] for all time."""
        with self.driver.session() as session:
            result = session.run(
                """
                MATCH (e:Expense)-[:RECORDED_IN]->(m:Month)
                MATCH (e)-[:BELONGS_TO]->(c:Category)
                RETURN m.year AS year, m.month AS month,
                       m.name AS month_name, c.name AS category,
                       sum(e.amount) AS total
                ORDER BY m.year, m.month
                """
            )
            return [dict(r) for r in result]

    def get_daily_spending(self, year: int, month: int) -> list[dict]:
        key = f"{year}-{month:02d}"
        with self.driver.session() as session:
            result = session.run(
                """
                MATCH (e:Expense)-[:RECORDED_IN]->(m:Month {key: $key})
                MATCH (e)-[:BELONGS_TO]->(c:Category)
                RETURN e.date AS date, c.name AS category,
                       sum(e.amount) AS total
                ORDER BY e.date
                """,
                key=key,
            )
            return [dict(r) for r in result]

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def get_categories(self) -> list[str]:
        with self.driver.session() as session:
            result = session.run(
                "MATCH (c:Category) RETURN c.name AS name ORDER BY c.name"
            )
            return [r["name"] for r in result]

    def get_all_months(self) -> list[dict]:
        with self.driver.session() as session:
            result = session.run(
                """
                MATCH (m:Month) RETURN m.year AS year, m.month AS month,
                       m.name AS name, m.key AS key
                ORDER BY m.year DESC, m.month DESC
                """
            )
            return [dict(r) for r in result]
