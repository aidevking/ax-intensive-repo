from __future__ import annotations

import argparse
import json
import sqlite3
import time

from backend.services import db_service
from backend.services.generate_service import DEFAULT_LLM_MODEL, GenerateService


def _connect() -> sqlite3.Connection:
    con = sqlite3.connect(str(db_service._DB_PATH), check_same_thread=False)
    con.row_factory = sqlite3.Row
    return con


def _load_rows(app_key: str | None, limit: int, only_existing_fallback: bool) -> list[sqlite3.Row]:
    where = []
    params: list[object] = []
    if app_key:
        where.append("a.app_key=?")
        params.append(app_key)
    if only_existing_fallback:
        where.append("COALESCE(ra.reply_tone, '') != 'llm_generated'")
    where_sql = "WHERE " + " AND ".join(where) if where else ""
    with _connect() as con:
        return con.execute(
            f"""
            SELECT r.id review_id,
                   r.content review_text,
                   r.rating,
                   a.app_name,
                   ra.sentiment_label,
                   ra.pain_points
            FROM reviews r
            JOIN apps a ON a.id = r.app_id
            JOIN review_analysis ra ON ra.review_id = r.id
            {where_sql}
            ORDER BY r.created_at DESC, r.id
            LIMIT ?
            """,
            [*params, limit],
        ).fetchall()


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh stored manager reply suggestions with OpenAI.")
    parser.add_argument("--app-key", default=None, help="Optional app_key filter, e.g. shinhan-sol-bank")
    parser.add_argument("--limit", type=int, default=20, help="Maximum rows to refresh")
    parser.add_argument("--model", default=DEFAULT_LLM_MODEL, help="OpenAI model to use")
    parser.add_argument("--all", action="store_true", help="Also refresh rows already marked llm_generated")
    parser.add_argument("--sleep", type=float, default=0.2, help="Delay between requests in seconds")
    args = parser.parse_args()

    rows = _load_rows(
        app_key=args.app_key,
        limit=max(1, args.limit),
        only_existing_fallback=not args.all,
    )
    service = GenerateService()
    updated = 0
    failed = 0

    for row in rows:
        try:
            pain_points = [
                str(item.get("label") or item.get("category") or "")
                for item in json.loads(row["pain_points"] or "[]")
                if isinstance(item, dict)
            ]
            result = service.generate_reply(
                review=row["review_text"],
                model=args.model,
                app_name=row["app_name"],
                rating=row["rating"],
                sentiment=row["sentiment_label"],
                pain_points=pain_points,
            )
            db_service.update_review_reply(
                review_id=row["review_id"],
                tone="llm_generated",
                message=result["reply"],
            )
            updated += 1
            print(json.dumps({
                "review_id": row["review_id"],
                "status": "updated",
                "category": result.get("category", ""),
            }, ensure_ascii=False))
            if args.sleep > 0:
                time.sleep(args.sleep)
        except Exception as exc:
            failed += 1
            print(json.dumps({
                "review_id": row["review_id"],
                "status": "failed",
                "error": str(exc),
            }, ensure_ascii=False))

    print(json.dumps({
        "requested": len(rows),
        "updated": updated,
        "failed": failed,
        "model": args.model,
    }, ensure_ascii=False))
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
