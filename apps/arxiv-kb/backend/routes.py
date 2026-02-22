"""Science KB — Private App backend.

Routes (mounted at /api/app/akb):
  GET /stats           — DB statistics
  GET /categories      — All arXiv categories with enabled flag
  GET /paper/{id}      — Paper detail with translated abstract
  GET /pdf/{id}        — Serve PDF file
  GET /search          — Text search across papers and chunks
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

router = APIRouter()

DEFAULT_DATA_DIR = os.path.expanduser("~/workspace/arxivkb")

# ---------------------------------------------------------------------------
# LLM config cache (auto-expires after 5 min)
# ---------------------------------------------------------------------------
_llm_cache: dict = {"ts": 0, "endpoint": "", "model": ""}
_LLM_CACHE_TTL = 300  # 5 minutes


def _get_llm_config() -> dict:
    """Read LLM endpoint/model from OpenClaw config, cached 5 min."""
    now = time.time()
    if now - _llm_cache["ts"] < _LLM_CACHE_TTL and _llm_cache["endpoint"]:
        return _llm_cache

    # Find OpenClaw config
    oc_config = os.path.expanduser("~/.openclaw/openclaw.json")
    if not os.path.exists(oc_config):
        # Fallback: check OPENCLAW_CONFIG env
        oc_config = os.environ.get("OPENCLAW_CONFIG", oc_config)

    endpoint = "http://localhost:4000"
    model = "claude-sonnet-4-6"

    try:
        cfg = json.loads(Path(oc_config).read_text())
        providers = cfg.get("models", {}).get("providers", {})
        # Pick first provider with a baseUrl
        for name, p in providers.items():
            base = p.get("baseUrl", "")
            if base:
                endpoint = base
                # Pick a non-reasoning model (prefer sonnet for translation)
                for m in p.get("models", []):
                    mid = m.get("id", "")
                    if "sonnet" in mid.lower():
                        model = mid
                        break
                    model = mid  # fallback to first
                break
    except Exception:
        pass

    _llm_cache.update(ts=now, endpoint=endpoint, model=model)
    return _llm_cache


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_data_dir() -> str:
    return os.environ.get("ARXIVKB_DATA_DIR", DEFAULT_DATA_DIR)


def _db_conn() -> sqlite3.Connection:
    db_path = os.path.join(_get_data_dir(), "arxivkb.db")
    if not os.path.exists(db_path):
        raise HTTPException(404, detail="ArXivKB database not found. Run: skb ingest")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _get_translate_language() -> str:
    """Read translate language from PrivateApp settings DB."""
    settings_db = os.environ.get(
        "PRIVATEAPP_SETTINGS_DB",
        os.path.expanduser("~/.local/share/privateapp/privateapp.db"),
    )
    if not os.path.exists(settings_db):
        return ""
    try:
        conn = sqlite3.connect(settings_db)
        row = conn.execute("SELECT value FROM preferences WHERE key = 'language'").fetchone()
        conn.close()
        return row[0].strip() if row and row[0] else ""
    except Exception:
        return ""


def _translate(text: str, target_lang: str) -> str | None:
    """Translate text via LLM endpoint (auto-discovered from OpenClaw config)."""
    llm = _get_llm_config()
    try:
        resp = requests.post(
            f"{llm['endpoint']}/v1/chat/completions",
            json={
                "model": llm["model"],
                "messages": [
                    {"role": "system", "content": f"Translate the following academic abstract to {target_lang}. Return ONLY the translation, no preamble."},
                    {"role": "user", "content": text},
                ],
                "max_tokens": 2000,
                "temperature": 0.1,
            },
            timeout=30,
        )
        if resp.ok:
            return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/stats")
async def science_stats():
    conn = _db_conn()
    try:
        papers = conn.execute("SELECT COUNT(*) FROM papers").fetchone()[0]
        try:
            chunks = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        except Exception:
            chunks = 0
        try:
            categories = conn.execute("SELECT COUNT(*) FROM categories WHERE enabled = 1").fetchone()[0]
        except Exception:
            categories = 0

        last_row = conn.execute(
            "SELECT DATE(created_at) as d, COUNT(*) as cnt FROM papers GROUP BY DATE(created_at) ORDER BY d DESC LIMIT 1"
        ).fetchone()

        return {
            "papers": papers,
            "chunks": chunks,
            "categories": categories,
            "last_crawl": last_row[0] if last_row else None,
            "last_crawl_count": last_row[1] if last_row else 0,
        }
    finally:
        conn.close()


@router.get("/categories")
async def science_categories():
    conn = _db_conn()
    try:
        try:
            rows = conn.execute("SELECT code, description, group_name, enabled FROM categories ORDER BY group_name, code").fetchall()
            return {"categories": [{"code": r["code"], "description": r["description"] or "", "group": r["group_name"] or "", "enabled": bool(r["enabled"])} for r in rows]}
        except Exception:
            return {"categories": []}
    finally:
        conn.close()


def _pdf_path(arxiv_id: str) -> str:
    """Derive PDF path from arxiv_id — no DB lookup needed."""
    return os.path.join(_get_data_dir(), "pdfs", f"{arxiv_id}.pdf")


@router.get("/paper/{arxiv_id}")
async def science_paper(arxiv_id: str):
    """Paper detail — returns immediately, no translation blocking."""
    conn = _db_conn()
    try:
        row = conn.execute(
            "SELECT id, arxiv_id, title, abstract, published FROM papers WHERE arxiv_id = ?",
            (arxiv_id,),
        ).fetchone()
        if not row:
            raise HTTPException(404, "Paper not found")

        has_pdf = os.path.exists(_pdf_path(row["arxiv_id"]))
        target_lang = _get_translate_language()

        # Check if translation already cached
        abstract_translated = None
        if target_lang and row["abstract"]:
            tr = conn.execute(
                "SELECT abstract FROM translations WHERE paper_id = ? AND language = ?",
                (row["id"], target_lang),
            ).fetchone()
            if tr:
                abstract_translated = tr[0]

        return {
            "arxiv_id": row["arxiv_id"],
            "title": row["title"],
            "abstract": row["abstract"],
            "abstract_translated": abstract_translated,
            "translate_language": target_lang or None,
            "published": row["published"],
            "has_pdf": has_pdf,
        }
    finally:
        conn.close()


@router.get("/paper/{arxiv_id}/translate")
async def science_paper_translate(arxiv_id: str):
    """Translate abstract on demand — called async by frontend."""
    conn = _db_conn()
    try:
        row = conn.execute(
            "SELECT id, abstract FROM papers WHERE arxiv_id = ?", (arxiv_id,),
        ).fetchone()
        if not row or not row["abstract"]:
            return {"translated": None}

        target_lang = _get_translate_language()
        if not target_lang:
            return {"translated": None}

        # Check cache
        tr = conn.execute(
            "SELECT abstract FROM translations WHERE paper_id = ? AND language = ?",
            (row["id"], target_lang),
        ).fetchone()
        if tr:
            return {"translated": tr[0], "language": target_lang}

        # Translate
        translated = _translate(row["abstract"], target_lang)
        if translated:
            try:
                conn.execute(
                    "INSERT INTO translations (paper_id, language, abstract) VALUES (?, ?, ?)",
                    (row["id"], target_lang, translated),
                )
                conn.commit()
            except Exception:
                pass
        return {"translated": translated, "language": target_lang}
    finally:
        conn.close()


@router.get("/pdf/{arxiv_id}")
async def science_pdf(arxiv_id: str):
    """Serve PDF file for inline viewing."""
    pdf_file = _pdf_path(arxiv_id)
    if not os.path.exists(pdf_file):
        raise HTTPException(404, "PDF not found")
    return FileResponse(
        pdf_file,
        media_type="application/pdf",
        filename=f"{arxiv_id}.pdf",
        headers={"Content-Disposition": "inline"},
    )


@router.get("/search")
async def science_search(
    q: str = Query(..., min_length=2),
    top_k: int = Query(10, ge=1, le=50),
):
    """Semantic search over paper abstracts via FAISS, fallback to text search."""
    data_dir = _get_data_dir()
    db_path = os.path.join(data_dir, "arxivkb.db")

    # Try semantic search first
    try:
        import sys
        scripts_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "scripts")
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        # Also add the skill scripts dir
        skill_dir = os.path.expanduser("~/.openclaw/workspace/skills/arxivkb/scripts")
        if skill_dir not in sys.path:
            sys.path.insert(0, skill_dir)
        from search import search as semantic_search
        results = semantic_search(q, db_path, data_dir, top_k=top_k)
        if results:
            return {"count": len(results), "method": "semantic", "results": results}
    except Exception:
        pass

    # Fallback: text search
    conn = _db_conn()
    try:
        rows = conn.execute(
            """SELECT arxiv_id, title, published
               FROM papers
               WHERE title LIKE ? OR abstract LIKE ?
               ORDER BY published DESC LIMIT ?""",
            (f"%{q}%", f"%{q}%", top_k),
        ).fetchall()
        return {
            "count": len(rows),
            "method": "text",
            "results": [
                {"arxiv_id": r["arxiv_id"], "title": r["title"], "published": r["published"]}
                for r in rows
            ],
        }
    finally:
        conn.close()


if __name__ == "__main__":
    from fastapi import FastAPI
    import uvicorn

    app = FastAPI(title="Science KB")
    app.include_router(router, prefix="/api/app/akb")

    dist = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
    if os.path.isdir(dist):
        from fastapi.staticfiles import StaticFiles
        app.mount("/", StaticFiles(directory=dist, html=True))

    uvicorn.run(app, host="0.0.0.0", port=8803)
