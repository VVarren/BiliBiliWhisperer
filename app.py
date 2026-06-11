"""
Bilibili Chinese Learning App — entry point.

Usage:
    python app.py output/ep691461_audio.m4a
    python app.py 691461
"""

import asyncio
import re
import subprocess
import sys
import threading
import time

# ProactorEventLoop (Windows default) raises WinError 10054 on browser disconnects.
# SelectorEventLoop handles this cleanly.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
import webbrowser
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import bilibili_api
import dictionary
import transcribe

BASE_DIR   = Path(__file__).parent
STATIC_DIR = BASE_DIR / "static"
PORT       = 8765

app = FastAPI()

# Runtime state populated at startup
_segments:      list[dict] = []
_audio_path:    Path | None = None
_download_jobs: dict[str, subprocess.Popen] = {}
_season_cache:  list[dict] = []

# Batch download+transcribe state
_batch: dict = {
    "running":     False,
    "ep_ids":      [],
    "done":        [],
    "current":     None,   # current ep_id being processed
    "phase":       None,   # "downloading" | "transcribing" | "done" | "error"
    "error":       None,
    "model":       "large-v3",
}
_batch_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/audio")
def audio():
    if _audio_path is None or not _audio_path.exists():
        raise HTTPException(status_code=404, detail="Audio file not found")
    return FileResponse(str(_audio_path), media_type="audio/mp4")


@app.get("/api/segments")
def segments():
    return _segments


@app.get("/api/dict/{word}")
def dict_lookup(word: str):
    entries = dictionary.lookup(word)
    if not entries:
        raise HTTPException(status_code=404, detail=f"'{word}' not found in dictionary")
    return entries


@app.get("/api/search")
def search(q: str = Query(..., min_length=1)):
    return [s for s in _segments if q in s["text"]]


@app.get("/api/season")
def season(ep_id: str = Query(...)):
    global _season_cache
    try:
        info = bilibili_api.get_season_episodes(ep_id)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))

    _season_cache = info["episodes"]

    # Annotate each episode with its local download/transcription status
    output_dir = BASE_DIR / "output"
    cache_dir  = BASE_DIR / "cache"
    for ep in _season_cache:
        eid = ep["ep_id"]
        audio_file  = output_dir / f"ep{eid}_audio.m4a"
        cache_file  = cache_dir  / f"ep{eid}_audio.json"
        ep["is_downloaded"]  = audio_file.exists()
        ep["is_transcribed"] = cache_file.exists()
    return {"title": info["title"], "episodes": _season_cache}


LOGS_DIR = BASE_DIR / "logs"

_DOWNLOADER_COOKIES_FALLBACK = r"C:\Users\roland\cookies_dl.txt"


def _find_downloader_cookies() -> Path:
    local = BASE_DIR / "cookies_dl.txt"
    return local if local.exists() else Path(_DOWNLOADER_COOKIES_FALLBACK)


def _log_path(ep_id: str) -> Path:
    LOGS_DIR.mkdir(exist_ok=True)
    return LOGS_DIR / f"ep{ep_id}_download.log"


def _tail_log(ep_id: str, lines: int = 20) -> str:
    p = _log_path(ep_id)
    if not p.exists():
        return ""
    text = p.read_text(encoding="utf-8", errors="replace")
    return "\n".join(text.splitlines()[-lines:])


@app.post("/api/download/{ep_id}")
def download_episode(ep_id: str):
    if ep_id in _download_jobs and _download_jobs[ep_id].poll() is None:
        return {"status": "downloading"}

    audio_file = BASE_DIR / "output" / f"ep{ep_id}_audio.m4a"
    if audio_file.exists():
        return {"status": "done"}

    cookies_path = _find_downloader_cookies()
    if not cookies_path.exists():
        raise HTTPException(
            status_code=400,
            detail=(
                f"Downloader cookies not found. Place cookies_dl.txt in the project folder "
                f"or at {_DOWNLOADER_COOKIES_FALLBACK}. Run setup_downloader_profile.py first."
            ),
        )

    log_file = open(_log_path(ep_id), "w", encoding="utf-8")
    proc = subprocess.Popen(
        [sys.executable, str(BASE_DIR / "extract_audio.py"), ep_id],
        cwd=BASE_DIR,
        stdout=log_file,
        stderr=subprocess.STDOUT,
    )
    _download_jobs[ep_id] = proc
    return {"status": "downloading"}


@app.get("/api/download/status/{ep_id}")
def download_status(ep_id: str):
    audio_file = BASE_DIR / "output" / f"ep{ep_id}_audio.m4a"

    proc = _download_jobs.get(ep_id)
    if proc is not None:
        rc = proc.poll()
        if rc is None:
            return {"status": "downloading"}
        if rc == 0 and audio_file.exists():
            return {"status": "done"}
        return {"status": "error", "log": _tail_log(ep_id)}

    if audio_file.exists():
        return {"status": "done"}
    return {"status": "idle"}


@app.get("/api/download/log/{ep_id}")
def download_log(ep_id: str):
    return {"log": _tail_log(ep_id)}


# ---------------------------------------------------------------------------
# Batch download + transcribe
# ---------------------------------------------------------------------------

class BatchRequest(BaseModel):
    ep_ids: list[str]
    model:  str = "large-v3"


def _run_batch(ep_ids: list[str], model: str) -> None:
    """Background thread: download then transcribe each episode in sequence."""
    try:
        for ep_id in ep_ids:
            _batch["current"] = ep_id
            audio_file = BASE_DIR / "output" / f"ep{ep_id}_audio.m4a"

            # ── Download ──────────────────────────────────────────────────
            if not audio_file.exists():
                _batch["phase"] = "downloading"
                log_f = open(_log_path(ep_id), "w", encoding="utf-8")
                proc  = subprocess.Popen(
                    [sys.executable, str(BASE_DIR / "extract_audio.py"), ep_id],
                    cwd=BASE_DIR,
                    stdout=log_f,
                    stderr=subprocess.STDOUT,
                )
                proc.wait()
                log_f.close()
                if proc.returncode != 0 or not audio_file.exists():
                    _batch["phase"] = "error"
                    _batch["error"] = f"Download failed for ep {ep_id} — see logs/ep{ep_id}_download.log"
                    _batch["running"] = False
                    return

            # ── Transcribe ────────────────────────────────────────────────
            cache_file = BASE_DIR / "cache" / f"ep{ep_id}_audio.json"
            if not cache_file.exists():
                _batch["phase"] = "transcribing"
                transcribe.get_segments(audio_file, model_size=model)

            _batch["done"].append(ep_id)

        _batch["phase"]   = "done"
        _batch["current"] = None
        _batch["running"] = False

    except Exception as exc:
        _batch["phase"]   = "error"
        _batch["error"]   = str(exc)
        _batch["running"] = False


@app.post("/api/batch")
def start_batch(req: BatchRequest):
    with _batch_lock:
        if _batch["running"]:
            raise HTTPException(status_code=409, detail="A batch job is already running.")

        cookies_path = _find_downloader_cookies()
        if not cookies_path.exists():
            raise HTTPException(
                status_code=400,
                detail=(
                    "Downloader cookies not found. "
                    "Run setup_downloader_profile.py first."
                ),
            )

        _batch.update({
            "running": True,
            "ep_ids":  req.ep_ids,
            "done":    [],
            "current": None,
            "phase":   None,
            "error":   None,
            "model":   req.model,
        })

    threading.Thread(target=_run_batch, args=(req.ep_ids, req.model), daemon=True).start()
    return {"status": "started", "count": len(req.ep_ids)}


@app.get("/api/batch/status")
def batch_status():
    return {
        "running":    _batch["running"],
        "total":      len(_batch["ep_ids"]),
        "done_count": len(_batch["done"]),
        "done":       list(_batch["done"]),
        "current":    _batch["current"],
        "phase":      _batch["phase"],
        "error":      _batch["error"],
        "model":      _batch["model"],
    }


@app.post("/api/switch/{ep_id}")
def switch_episode(ep_id: str):
    global _audio_path, _segments
    audio_file = BASE_DIR / "output" / f"ep{ep_id}_audio.m4a"
    if not audio_file.exists():
        raise HTTPException(status_code=404, detail="Episode not downloaded yet")
    try:
        segs = transcribe.get_segments(audio_file)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    _audio_path = audio_file
    _segments   = segs
    return {"ok": True, "ep_id": ep_id, "segments": len(segs)}


# ---------------------------------------------------------------------------
# Startup helpers
# ---------------------------------------------------------------------------

def _resolve_audio(arg: str) -> Path:
    # Accept ep_id (digits only) or a direct path
    if re.fullmatch(r"\d+", arg):
        return BASE_DIR / "output" / f"ep{arg}_audio.m4a"
    return Path(arg)


def _open_browser_delayed(url: str, delay: float = 1.5) -> None:
    def _open():
        time.sleep(delay)
        webbrowser.open(url)
    threading.Thread(target=_open, daemon=True).start()


def main():
    global _segments, _audio_path

    # Load dictionary regardless of mode
    dictionary.build_index()

    if len(sys.argv) >= 2 and not sys.argv[1].startswith("--"):
        _audio_path = _resolve_audio(sys.argv[1])
        if not _audio_path.exists():
            print(f"Audio file not found: {_audio_path}")
            sys.exit(1)

        model = "large-v3"
        if "--small" in sys.argv:
            model = "small"
        elif "--medium" in sys.argv:
            model = "medium"
        _segments = transcribe.get_segments(_audio_path, model_size=model)
        start_url = f"http://localhost:{PORT}"
    else:
        # Browse mode — no episode pre-loaded; open episode browser tab
        print("No episode specified — starting in browse mode.")
        start_url = f"http://localhost:{PORT}/#episodes"

    print(f"\nStarting server at http://localhost:{PORT}")
    _open_browser_delayed(start_url)

    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")


if __name__ == "__main__":
    main()
