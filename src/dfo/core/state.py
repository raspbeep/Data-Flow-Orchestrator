import sqlite3
from pathlib import Path

from dfo.core.models import ExecutionResult, FlowResult


class StateStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._init_db()

    def _init_db(self) -> None:
        self.db_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    flow_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    start_time TEXT,
                    end_time TEXT,
                    result_json TEXT NOT NULL
                )
                """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS step_results (
                    run_id TEXT NOT NULL,
                    step_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    PRIMARY KEY (run_id, step_id)
                )
                """)

    def save_run(self, result: FlowResult) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO runs (
                    run_id,
                    flow_name,
                    status,
                    start_time,
                    end_time,
                    result_json
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    result.run_id,
                    result.flow_name,
                    result.status.value,
                    result.start_time.isoformat() if result.start_time else None,
                    result.end_time.isoformat() if result.end_time else None,
                    result.model_dump_json(),
                ),
            )

    def save_step(
        self,
        run_id: str,
        result: ExecutionResult,
    ) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO step_results (
                    run_id,
                    step_id,
                    status,
                    result_json
                )
                VALUES (?, ?, ?, ?)
                """,
                (
                    run_id,
                    result.step_id,
                    result.status.value,
                    result.model_dump_json(),
                ),
            )

    def get_run(self, run_id: str) -> FlowResult | None:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                """
                SELECT result_json
                FROM runs
                WHERE run_id = ?
                """,
                (run_id,),
            ).fetchone()

        if row is None:
            return None

        return FlowResult.model_validate_json(row[0])

    def get_step_result(
        self,
        run_id: str,
        step_id: str,
    ) -> ExecutionResult | None:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                """
                SELECT result_json
                FROM step_results
                WHERE run_id = ? AND step_id = ?
                """,
                (run_id, step_id),
            ).fetchone()

        if row is None:
            return None

        return ExecutionResult.model_validate_json(row[0])
