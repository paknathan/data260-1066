"""HW7 Part 4 - UI + API for the Bay Wheels ReAct agent (served by main.py on PORT_BASE).

GET  /bikeshare              single-page UI (CSV upload, pricing URL, Run, timeline, results)
POST /api/bikeshare/run      {csv_text, pricing_url, label?} -> agent result (also saved under reports/hw07/raw/part4/)
"""

import json
import re
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from bikeshare.agent import run_bikeshare_agent

CODE_DIR = Path(__file__).resolve().parents[1]
RAW_DIR = CODE_DIR.parent / "reports" / "hw07" / "raw" / "part4"
MAX_CSV_BYTES = 5_000_000

router = APIRouter(tags=["HW7 Part 4 - Bay Wheels agent"])


class RunRequest(BaseModel):
    csv_text: str = Field(..., min_length=10)
    pricing_url: str = Field(..., min_length=4, max_length=500)
    label: str | None = Field(None, max_length=60)


def run_and_save(csv_text: str, pricing_url: str, label: str | None) -> dict:
    """Run the agent, then save result.json (+ snapshot, written by the tool) under raw/part4/<label>/."""
    slug = re.sub(r"[^A-Za-z0-9_-]+", "_", label or "") or datetime.now().strftime("run_%Y%m%d_%H%M%S")
    out_dir = RAW_DIR / slug
    result = run_bikeshare_agent(csv_text, pricing_url, snapshot_dir=out_dir)
    result["label"] = slug
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "result.json").write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    return result


@router.post("/api/bikeshare/run")
def run(req: RunRequest) -> dict:
    """Run the ReAct agent on the uploaded CSV text and pricing URL."""
    if len(req.csv_text.encode("utf-8")) > MAX_CSV_BYTES:
        raise HTTPException(status_code=413, detail="CSV too large (max 5 MB)")
    return run_and_save(req.csv_text, req.pricing_url.strip(), req.label)


@router.get("/bikeshare", response_class=HTMLResponse)
def page() -> str:
    """Serve the single-page UI."""
    return (CODE_DIR / "bikeshare" / "ui.html").read_text(encoding="utf-8")
