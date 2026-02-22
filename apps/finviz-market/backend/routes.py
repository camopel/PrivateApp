"""Finviz — Private App backend.

Routes (mounted at /api/app/finviz):
  GET  /stats               — DB statistics
  GET  /summary/:period     — Get or generate summary (12h, 24h, weekly)
  GET  /headlines            — Raw headlines for a time range
  GET  /article              — Full article content by URL
  GET  /tickers              — Get ticker list from DB
  POST /tickers              — Add tickers (batch)
  DELETE /tickers            — Remove tickers (batch)
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import hashlib
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Body

router = APIRouter()

DEFAULT_DB = os.path.expanduser("~/Downloads/Finviz/finviz.db")
DEFAULT_ARTICLES_DIR = os.path.expanduser("~/Downloads/Finviz/articles")
FINVIZ_DIR = Path(os.path.expanduser("~/Downloads/Finviz"))
SUMMARY_CACHE_DIR = FINVIZ_DIR / "summaries"
APP_SETTINGS_DIR = Path.home() / ".local" / "share" / "privateapp"

LLM_ENDPOINT = os.environ.get("LLM_ENDPOINT", "http://localhost:4000")
LLM_MODEL = os.environ.get("LLM_MODEL", "claude-sonnet-4-6")

_generating: dict[str, bool] = {}


def _get_db() -> str:
    return os.environ.get("FINVIZ_DB", DEFAULT_DB)


def _get_articles_dir() -> str:
    return os.environ.get("FINVIZ_ARTICLES_DIR", DEFAULT_ARTICLES_DIR)


def _db_conn() -> sqlite3.Connection:
    db_path = _get_db()
    if not os.path.exists(db_path):
        raise HTTPException(404, detail="Finviz database not found.")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _tickers_db() -> sqlite3.Connection:
    FINVIZ_DIR.mkdir(parents=True, exist_ok=True)
    db_path = FINVIZ_DIR / "finviz.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("""CREATE TABLE IF NOT EXISTS tickers (
        symbol TEXT PRIMARY KEY,
        keywords TEXT NOT NULL DEFAULT '[]',
        added_at TEXT NOT NULL
    )""")
    conn.commit()
    return conn


def _get_preferences() -> dict:
    db_path = APP_SETTINGS_DIR / "privateapp.db"
    if not db_path.exists():
        return {"timezone": "America/Los_Angeles", "language": "English"}
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        prefs = {}
        for row in conn.execute("SELECT key, value FROM preferences").fetchall():
            prefs[row["key"]] = row["value"]
        conn.close()
        return {
            "timezone": prefs.get("timezone", "America/Los_Angeles"),
            "language": prefs.get("language", "English"),
        }
    except Exception:
        return {"timezone": "America/Los_Angeles", "language": "English"}


# ── Tickers ──

@router.get("/tickers")
async def get_tickers():
    """Get all tracked tickers from DB."""
    conn = _tickers_db()
    try:
        rows = conn.execute("SELECT symbol, keywords FROM tickers ORDER BY symbol").fetchall()
        items = [{"symbol": r["symbol"], "keywords": json.loads(r["keywords"])} for r in rows]
        return {"items": items}
    finally:
        conn.close()


@router.post("/tickers")
async def add_tickers(data: dict = Body(...)):
    """Add tickers (batch). Body: {"tickers": [{"symbol": "NVDA", "keywords": ["nvidia"]}]}"""
    tickers = data.get("tickers", [])
    if not tickers:
        raise HTTPException(400, "No tickers provided")

    conn = _tickers_db()
    try:
        added = []
        for t in tickers:
            sym = t.get("symbol", "").strip().upper()
            if not sym or sym == "MARKET":
                continue
            kw = t.get("keywords", [sym.lower()])
            conn.execute(
                "INSERT OR REPLACE INTO tickers (symbol, keywords, added_at) VALUES (?, ?, ?)",
                (sym, json.dumps(kw), datetime.now(timezone.utc).isoformat()),
            )
            added.append(sym)
        conn.commit()
        return {"ok": True, "added": added}
    finally:
        conn.close()


@router.delete("/tickers")
async def remove_tickers(symbols: str = Query(...)):
    """Remove tickers (batch). ?symbols=NVDA,TSLA"""
    syms = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    conn = _tickers_db()
    try:
        for sym in syms:
            conn.execute("DELETE FROM tickers WHERE symbol = ?", (sym,))
        conn.commit()
        return {"ok": True, "removed": syms}
    finally:
        conn.close()


# ── Articles & Summaries ──

def _period_to_hours(period: str) -> int:
    return {"12h": 12, "24h": 24, "weekly": 168}.get(period, 24)


def _get_articles_for_period(hours: int, topic: str = "Market", limit: int = 200) -> list[dict]:
    """Fetch articles filtered strictly by ticker column."""
    conn = _db_conn()
    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        articles_dir = _get_articles_dir()

        # Market = articles with no ticker (general headlines)
        if topic == "Market":
            rows = conn.execute(
                """SELECT title, url, publish_at, article_path
                   FROM articles WHERE publish_at >= ? AND (ticker IS NULL OR ticker = '')
                   AND status = 'done'
                   ORDER BY publish_at DESC LIMIT ?""",
                (cutoff, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT title, url, publish_at, article_path
                   FROM articles WHERE publish_at >= ? AND ticker = ?
                   AND status = 'done'
                   ORDER BY publish_at DESC LIMIT ?""",
                (cutoff, topic, limit),
            ).fetchall()

        articles = []
        for r in rows:
            content = None
            if r["article_path"]:
                fp = os.path.join(articles_dir, r["article_path"])
                if os.path.exists(fp):
                    content = Path(fp).read_text(errors="replace")[:3000]
            articles.append({"title": r["title"], "url": r["url"], "date": r["publish_at"], "content": content})
        return articles
    finally:
        conn.close()


def _cache_key(period: str, language: str, topic: str = "Market") -> str:
    now = datetime.now(timezone.utc)
    if period == "weekly":
        bucket = f"{now.year}-W{now.isocalendar()[1]}"
    elif period == "24h":
        bucket = f"{now.strftime('%Y-%m-%d')}-{now.hour // 6}"
    else:
        bucket = f"{now.strftime('%Y-%m-%d')}-{now.hour // 3}"
    raw = f"{period}:{language}:{topic}:{bucket}"
    return hashlib.md5(raw.encode()).hexdigest()[:12]


def _get_cached_summary(period: str, language: str, topic: str = "Market") -> dict | None:
    SUMMARY_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    key = _cache_key(period, language, topic)
    cache_file = SUMMARY_CACHE_DIR / f"{key}.json"
    if cache_file.exists():
        try:
            return json.loads(cache_file.read_text())
        except Exception:
            pass
    return None


def _save_cached_summary(period: str, language: str, summary: str, article_count: int, topic: str = "Market") -> dict:
    SUMMARY_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    key = _cache_key(period, language, topic)
    data = {
        "period": period,
        "language": language,
        "topic": topic,
        "summary": summary,
        "article_count": article_count,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    (SUMMARY_CACHE_DIR / f"{key}.json").write_text(json.dumps(data, ensure_ascii=False))
    return data


def _generate_summary_llm(articles: list[dict], period: str, language: str, topic: str = "Market") -> str:
    import urllib.request

    digest_parts = []
    for i, a in enumerate(articles[:80], 1):
        snippet = ""
        if a["content"]:
            snippet = f"\n   Content: {a['content'][:500]}"
        digest_parts.append(f"{i}. [{a['date']}] {a['title']}{snippet}")

    digest = "\n".join(digest_parts)
    period_label = {"12h": "last 12 hours", "24h": "last 24 hours", "weekly": "past week"}.get(period, period)

    topic_instruction = ""
    if topic != "Market":
        topic_instruction = f"\nFocus specifically on {topic} and related news. "

    lang_instruction = ""
    if language != "English":
        lang_instruction = f"\n\nIMPORTANT: Write the entire summary in {language}. All text must be in {language}."

    prompt = f"""Summarize the following financial news from the {period_label} into a concise briefing.
{topic_instruction}
Group by major themes. For each theme:
- Key developments and their market impact
- Notable stock movements mentioned
- Forward-looking implications

Be concise but informative. Use bullet points.{lang_instruction}

---
{digest}
---

{"" if topic == "Market" else topic + " "}Briefing ({period_label}):"""

    payload = json.dumps({
        "model": LLM_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
        "max_tokens": 2000,
    }).encode()

    req = urllib.request.Request(
        f"{LLM_ENDPOINT}/chat/completions",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        result = json.loads(resp.read())
        return result["choices"][0]["message"]["content"]


def _do_generate(period: str, language: str, topic: str = "Market"):
    key = f"{period}:{language}:{topic}"
    try:
        hours = _period_to_hours(period)
        articles = _get_articles_for_period(hours, topic=topic)
        if not articles:
            _save_cached_summary(period, language, f"No articles found for {topic} in this period. The crawler may not have ingested articles for this ticker yet — try again after the next crawl cycle.", 0, topic)
            return
        summary = _generate_summary_llm(articles, period, language, topic)
        _save_cached_summary(period, language, summary, len(articles), topic)
    except Exception as e:
        _save_cached_summary(period, language, f"Error: {e}", 0, topic)
    finally:
        _generating.pop(key, None)


@router.get("/article-counts")
async def finviz_article_counts(hours: int = Query(0, ge=0, le=8760)):
    """Article counts per ticker. hours=0 (default) means all time."""
    conn = _db_conn()
    try:
        if hours > 0:
            cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
            market_count = conn.execute(
                "SELECT COUNT(*) FROM articles WHERE publish_at >= ? AND (ticker IS NULL OR ticker = '') AND status = 'done'",
                (cutoff,),
            ).fetchone()[0]
            rows = conn.execute(
                "SELECT ticker, COUNT(*) as cnt FROM articles WHERE publish_at >= ? AND ticker IS NOT NULL AND ticker != '' AND status = 'done' GROUP BY ticker ORDER BY ticker",
                (cutoff,),
            ).fetchall()
        else:
            market_count = conn.execute(
                "SELECT COUNT(*) FROM articles WHERE (ticker IS NULL OR ticker = '') AND status = 'done'",
            ).fetchone()[0]
            rows = conn.execute(
                "SELECT ticker, COUNT(*) as cnt FROM articles WHERE ticker IS NOT NULL AND ticker != '' AND status = 'done' GROUP BY ticker ORDER BY ticker",
            ).fetchall()
        counts = {"Market": market_count}
        for r in rows:
            counts[r["ticker"]] = r["cnt"]
        return counts
    finally:
        conn.close()


@router.get("/stats")
async def finviz_stats():
    conn = _db_conn()
    try:
        total = conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
        with_content = conn.execute(
            "SELECT COUNT(*) FROM articles WHERE article_path IS NOT NULL"
        ).fetchone()[0]
        cutoff_24h = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
        last_24h = conn.execute(
            "SELECT COUNT(*) FROM articles WHERE publish_at >= ?", (cutoff_24h,)
        ).fetchone()[0]
        return {"total": total, "with_content": with_content, "last_24h": last_24h}
    finally:
        conn.close()


@router.get("/summary/{period}")
async def finviz_summary(period: str, regenerate: int = 0, topic: str = "Market"):
    if period not in ("12h", "24h", "weekly"):
        raise HTTPException(400, "Period must be 12h, 24h, or weekly")

    prefs = _get_preferences()
    language = prefs["language"]
    key = f"{period}:{language}:{topic}"

    if regenerate:
        ck = _cache_key(period, language, topic)
        cf = SUMMARY_CACHE_DIR / f"{ck}.json"
        if cf.exists():
            cf.unlink()

    cached = _get_cached_summary(period, language, topic)
    if cached and not regenerate:
        return {**cached, "status": "ready", "generating": key in _generating}

    if key in _generating:
        return {"status": "generating", "period": period, "language": language, "topic": topic}

    _generating[key] = True
    thread = threading.Thread(target=_do_generate, args=(period, language, topic), daemon=True)
    thread.start()
    return {"status": "generating", "period": period, "language": language, "topic": topic}


@router.get("/headlines")
async def finviz_headlines(
    hours: int = Query(24, ge=1, le=720),
    limit: int = Query(100, ge=1, le=500),
):
    conn = _db_conn()
    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        rows = conn.execute(
            """SELECT title, url, publish_at, article_path
               FROM articles WHERE publish_at >= ?
               ORDER BY publish_at DESC LIMIT ?""",
            (cutoff, limit),
        ).fetchall()
        return {
            "count": len(rows),
            "headlines": [
                {"title": r["title"], "url": r["url"], "date": r["publish_at"],
                 "has_content": r["article_path"] is not None}
                for r in rows
            ],
        }
    finally:
        conn.close()


@router.get("/article")
async def finviz_article(url: str = Query(...)):
    conn = _db_conn()
    try:
        row = conn.execute(
            "SELECT title, url, publish_at, article_path FROM articles WHERE url = ?", (url,)
        ).fetchone()
        if not row:
            raise HTTPException(404, "Article not found")
        content = None
        if row["article_path"]:
            fp = os.path.join(_get_articles_dir(), row["article_path"])
            if os.path.exists(fp):
                content = Path(fp).read_text(errors="replace")
        return {"title": row["title"], "url": row["url"], "date": row["publish_at"], "content": content}
    finally:
        conn.close()


if __name__ == "__main__":
    from fastapi import FastAPI
    import uvicorn
    app = FastAPI(title="Finviz")
    app.include_router(router, prefix="/api/app/finviz")
    uvicorn.run(app, host="0.0.0.0", port=8802)
