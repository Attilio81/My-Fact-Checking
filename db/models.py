import json
import sqlite3

from bot.models import ClaimResult

_SCHEMA = """
CREATE TABLE IF NOT EXISTS checks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    input_type TEXT NOT NULL,
    input_ref TEXT NOT NULL,
    source_title TEXT,
    report_text TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_checks_ref ON checks(input_ref, created_at);
CREATE TABLE IF NOT EXISTS claims (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    check_id INTEGER NOT NULL REFERENCES checks(id),
    claim_text TEXT NOT NULL,
    verdict TEXT NOT NULL,
    confidence TEXT NOT NULL,
    sources TEXT NOT NULL DEFAULT '[]'
);
"""


class Database:
    def __init__(self, path: str):
        self._path = path
        with self._conn() as c:
            c.executescript(_SCHEMA)

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self._path)

    def save_check(
        self,
        input_type: str,
        input_ref: str,
        source_title: str | None,
        report_text: str,
        results: list[ClaimResult],
    ) -> int:
        with self._conn() as c:
            cur = c.execute(
                "INSERT INTO checks (input_type, input_ref, source_title, report_text) VALUES (?,?,?,?)",
                (input_type, input_ref, source_title, report_text),
            )
            check_id = cur.lastrowid
            c.executemany(
                "INSERT INTO claims (check_id, claim_text, verdict, confidence, sources) VALUES (?,?,?,?,?)",
                [
                    (check_id, r.claim, r.verdict, r.confidence, json.dumps(r.sources))
                    for r in results
                ],
            )
        return check_id

    def get_check(self, check_id: int) -> dict | None:
        with self._conn() as c:
            row = c.execute(
                "SELECT id, created_at, input_type, input_ref, source_title "
                "FROM checks WHERE id = ?",
                (check_id,),
            ).fetchone()
        if row is None:
            return None
        keys = ["id", "created_at", "input_type", "input_ref", "source_title"]
        return dict(zip(keys, row))

    def list_checks_summary(self) -> list[dict]:
        """Tutti i check (più recenti prima) con conteggio verdetti, per l'indice wiki."""
        with self._conn() as c:
            rows = c.execute(
                "SELECT c.id, c.created_at, c.input_type, c.input_ref, c.source_title, "
                "COALESCE(SUM(cl.verdict = 'true'), 0), "
                "COALESCE(SUM(cl.verdict = 'false'), 0), "
                "COALESCE(SUM(cl.verdict = 'unverifiable'), 0) "
                "FROM checks c LEFT JOIN claims cl ON cl.check_id = c.id "
                "GROUP BY c.id ORDER BY c.created_at DESC, c.id DESC"
            ).fetchall()
        keys = [
            "id", "created_at", "input_type", "input_ref", "source_title",
            "true_n", "false_n", "unv_n",
        ]
        return [dict(zip(keys, r)) for r in rows]

    def get_recent_check(self, input_ref: str, days: int = 7) -> str | None:
        with self._conn() as c:
            row = c.execute(
                "SELECT report_text FROM checks WHERE input_ref = ? "
                "AND created_at >= datetime('now', ?) ORDER BY created_at DESC LIMIT 1",
                (input_ref, f"-{days} days"),
            ).fetchone()
        return row[0] if row else None
