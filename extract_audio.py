#!/usr/bin/env python3
"""
Extract audio from a Bilibili bangumi episode.

Launches your real Brave browser (with Unblock Youku / Unblock Boundary active)
to get properly signed, region-unblocked stream URLs, then downloads the audio track.

Usage:
    python extract_audio.py <bilibili-url>

Example:
    python extract_audio.py "https://www.bilibili.com/bangumi/play/ep691461"

Requirements:
    pip install playwright requests yt-dlp
    python -m playwright install chromium
    ffmpeg on PATH (for mp3 conversion; .m4a always saved regardless)
"""

import json
import re
import subprocess
import sys
import time
from pathlib import Path

import requests
from playwright.sync_api import sync_playwright

BRAVE_EXE           = r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe"
DOWNLOADER_DATA_DIR = r"C:\Users\roland\AppData\Local\BraveSoftware\Brave-Browser\Downloader Data"
_COOKIES_FALLBACK   = r"C:\Users\roland\cookies_dl.txt"

BASE_DIR   = Path(__file__).parent
OUTPUT_DIR = BASE_DIR / "output"


def _find_cookies() -> Path:
    """Project dir first (cookies_dl.txt next to this script), then home fallback."""
    local = BASE_DIR / "cookies_dl.txt"
    return local if local.exists() else Path(_COOKIES_FALLBACK)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_ep_id(url: str) -> str:
    m = re.search(r"ep(\d+)", url)
    if not m:
        raise ValueError(f"Cannot parse ep_id from: {url}")
    return m.group(1)


def clear_downloader_lock() -> None:
    """Clear Playwright/Chromium singleton lock files from the downloader data dir.

    We do NOT kill brave.exe — the user's main Brave window stays open.
    We only clean up the dedicated downloader profile's lock, which is stale
    only if a previous downloader run crashed without releasing it.
    """
    for name in ("SingletonLock", "SingletonSocket", "SingletonCookie"):
        p = Path(DOWNLOADER_DATA_DIR) / name
        p.unlink(missing_ok=True)
    print("Downloader profile lock cleared (main Brave untouched).")


def load_cookies(session: requests.Session) -> None:
    import http.cookiejar
    jar = http.cookiejar.MozillaCookieJar(str(_find_cookies()))
    jar.load(ignore_discard=True, ignore_expires=True)
    session.cookies.update(jar)


# ---------------------------------------------------------------------------
# Step 1 – get the DASH audio URL from inside Brave (extensions active)
# ---------------------------------------------------------------------------

def get_audio_url_via_browser(ep_id: str) -> dict | None:
    """
    Navigate to the episode in Brave, then call Bilibili's playurl API
    via page.evaluate() so that Unblock Youku/Boundary can proxy it.
    Returns the best audio stream dict from the DASH manifest, or None.
    """
    clear_downloader_lock()
    print("\nLaunching Brave with downloader profile (extensions active)...")
    print("(Main Brave window is unaffected.)")

    ep_url = f"https://www.bilibili.com/bangumi/play/ep{ep_id}"

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            DOWNLOADER_DATA_DIR,
            executable_path=BRAVE_EXE,
            headless=False,
            args=["--no-first-run", "--no-default-browser-check",
                  "--disable-blink-features=AutomationControlled"],
            ignore_default_args=[
                "--enable-automation",
                "--disable-extensions",
                "--disable-component-extensions-with-background-pages",
            ],
        )

        page = ctx.new_page()
        print("Waiting 5 s for extensions to initialise...")
        time.sleep(5)

        print(f"Navigating to {ep_url} ...")
        try:
            page.goto(ep_url, wait_until="domcontentloaded", timeout=30_000)
        except Exception as e:
            print(f"Navigation warning: {e}")

        # Wait for the player to initialise and pick up the session
        time.sleep(4)

        # Call the DASH playurl API from inside the browser page.
        # Credentials are included automatically; extensions handle region routing.
        print("Fetching DASH manifest from inside browser...")
        result = page.evaluate(f"""async () => {{
            const params = new URLSearchParams({{
                ep_id:        '{ep_id}',
                fnval:        '4048',   // DASH
                qn:           '64',     // 720p (audio quality is always highest)
                fourk:        '0',
                platform:     'pc',
                high_quality: '1',
            }});
            const url = 'https://api.bilibili.com/pgc/player/web/playurl?' + params;
            const r = await fetch(url, {{ credentials: 'include' }});
            return await r.json();
        }}""")

        ctx.close()

    if not result:
        print("Empty response from playurl API.")
        return None

    code = result.get("code")
    if code != 0:
        print(f"playurl API error {code}: {result.get('message')}")
        print("Full response:", json.dumps(result, ensure_ascii=False, indent=2)[:800])
        return None

    dash = result.get("result", {}).get("dash") or result.get("data", {}).get("dash")
    if not dash:
        print("No DASH manifest in response.")
        print("Response:", json.dumps(result, ensure_ascii=False, indent=2)[:800])
        return None

    audios = dash.get("audio", [])
    if not audios:
        print("No audio streams in DASH manifest.")
        return None

    # Pick the highest-bandwidth audio track
    best = max(audios, key=lambda a: a.get("bandwidth", 0))
    print(f"Found {len(audios)} audio track(s). Best: id={best.get('id')} "
          f"bandwidth={best.get('bandwidth')} codec={best.get('codecs')}")
    return best


# ---------------------------------------------------------------------------
# Step 2 – download the audio stream
# ---------------------------------------------------------------------------

def download_audio(audio: dict, ep_id: str) -> Path:
    url = audio.get("base_url") or audio.get("baseUrl")
    backup = audio.get("backup_url") or audio.get("backupUrl") or []

    session = requests.Session()
    session.headers.update({
        "User-Agent":  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Referer":     "https://www.bilibili.com",
        "Origin":      "https://www.bilibili.com",
    })
    load_cookies(session)

    OUTPUT_DIR.mkdir(exist_ok=True)
    out_path = OUTPUT_DIR / f"ep{ep_id}_audio.m4a"

    urls_to_try = [url] + (backup if isinstance(backup, list) else [backup])

    for attempt_url in urls_to_try:
        if not attempt_url:
            continue
        print(f"\nDownloading audio from:\n  {attempt_url[:100]}...")
        try:
            r = session.get(attempt_url, stream=True, timeout=30)
            r.raise_for_status()
            total = int(r.headers.get("content-length", 0))
            downloaded = 0
            with open(out_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=1 << 16):
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total:
                        pct = downloaded / total * 100
                        print(f"\r  {pct:5.1f}%  {downloaded/1024/1024:.2f} MB", end="", flush=True)
            print(f"\nSaved -> {out_path}  ({out_path.stat().st_size / 1024 / 1024:.2f} MB)")
            return out_path
        except Exception as e:
            print(f"  Failed ({e}), trying backup URL...")

    raise RuntimeError("All audio URLs failed.")


# ---------------------------------------------------------------------------
# Step 3 – optional mp3 conversion via ffmpeg
# ---------------------------------------------------------------------------

def convert_to_mp3(m4a_path: Path) -> Path | None:
    mp3_path = m4a_path.with_suffix(".mp3")
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(m4a_path), "-q:a", "0", str(mp3_path)],
            check=True, capture_output=True,
        )
        print(f"Converted -> {mp3_path}")
        return mp3_path
    except FileNotFoundError:
        print("ffmpeg not found on PATH — skipping mp3 conversion. .m4a is playable in VLC/foobar2000.")
        return None
    except subprocess.CalledProcessError as e:
        print(f"ffmpeg conversion failed: {e.stderr.decode()[:300]}")
        return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    arg = sys.argv[1]
    # Accept a plain ep_id (digits) or a full Bilibili URL
    if re.fullmatch(r"\d+", arg):
        ep_id = arg
    else:
        ep_id = get_ep_id(arg)
    print(f"Episode ID: {ep_id}")

    audio = get_audio_url_via_browser(ep_id)

    if not audio:
        print("\nCould not obtain audio URL. Possible reasons:")
        print("  - Extension did not unblock the region in time (try again)")
        print("  - Content requires purchase beyond VIP")
        sys.exit(1)

    m4a = download_audio(audio, ep_id)
    convert_to_mp3(m4a)

    print("\nDone.")


if __name__ == "__main__":
    main()
