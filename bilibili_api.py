"""Bilibili metadata API — episode/season info using cookies (no browser needed)."""

import http.cookiejar
import re
from pathlib import Path

import requests

_COOKIES_FALLBACK = r"C:\Users\roland\cookies.txt"
_BASE_DIR = Path(__file__).parent

_SESSION: requests.Session | None = None


def _find_cookies() -> Path:
    local = _BASE_DIR / "cookies.txt"
    return local if local.exists() else Path(_COOKIES_FALLBACK)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Referer": "https://www.bilibili.com",
}


def _session() -> requests.Session:
    global _SESSION
    if _SESSION is None:
        s = requests.Session()
        s.headers.update(HEADERS)
        try:
            jar = http.cookiejar.MozillaCookieJar(str(_find_cookies()))
            jar.load(ignore_discard=True, ignore_expires=True)
            s.cookies.update(jar)
        except Exception:
            pass
        _SESSION = s
    return _SESSION


def parse_ep_id(text: str) -> str | None:
    """Extract ep_id from a full URL or return the raw digits if given a plain number."""
    m = re.search(r"ep(\d+)", text)
    if m:
        return m.group(1)
    if re.fullmatch(r"\d+", text.strip()):
        return text.strip()
    return None


def get_season_episodes(ep_id: str) -> dict:
    """
    Fetch all episodes for the season that contains ep_id.
    Returns {"title": str, "episodes": list[dict]}.
    Episodes: {ep_id, title, long_title, duration_s, cover}.
    """
    url = f"https://api.bilibili.com/pgc/view/web/season?ep_id={ep_id}"
    resp = _session().get(url, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    code = data.get("code")
    if code != 0:
        msg = data.get("message", "unknown error")
        raise RuntimeError(f"Bilibili season API error {code}: {msg}")

    result = data.get("result", {})
    show_title   = result.get("title", "")
    season_title = result.get("season_title", "")
    display_title = f"{show_title} {season_title}".strip() if season_title else show_title

    raw_eps = result.get("episodes", [])
    if not raw_eps:
        raise RuntimeError("Season API returned no episodes.")

    episodes = []
    for ep in raw_eps:
        episodes.append({
            "ep_id":      str(ep.get("ep_id") or ep.get("id", "")),
            "title":      ep.get("title", ""),
            "long_title": ep.get("long_title", ""),
            "duration_s": ep.get("duration", 0) // 1000,
            "cover":      ep.get("cover", ""),
        })
    return {"title": display_title, "episodes": episodes}
