#!/usr/bin/env python3
"""
One-time setup for the dedicated Brave downloader profile.

Launches Brave at the downloader data directory using Playwright,
which bypasses the singleton mechanism — your main Brave stays open.

Steps:
  1. Run this script
  2. In the new Brave window, install Unblock Youku and All - Unblock Boundary
  3. Log in to Bilibili with your VIP account
  4. Install "Get cookies.txt LOCALLY", visit bilibili.com, export cookies,
     and save as cookies_dl.txt in this project folder (or C:\\Users\\roland\\cookies_dl.txt)
  5. Press Ctrl+C in this terminal when done
"""

import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

BRAVE_EXE           = r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe"
DOWNLOADER_DATA_DIR = r"C:\Users\roland\AppData\Local\BraveSoftware\Brave-Browser\Downloader Data"

BASE_DIR             = Path(__file__).parent
_COOKIES_FALLBACK    = r"C:\Users\roland\cookies_dl.txt"


def _find_cookies() -> Path:
    local = BASE_DIR / "cookies_dl.txt"
    return local if local.exists() else Path(_COOKIES_FALLBACK)


def main():
    # Clear any stale lock from a previous run
    for name in ("SingletonLock", "SingletonSocket", "SingletonCookie"):
        Path(DOWNLOADER_DATA_DIR, name).unlink(missing_ok=True)

    print("Opening Brave with the downloader profile...")
    print("(Your main Brave window is unaffected.)\n")
    print("Complete these steps in the new Brave window:")
    print("  1. Install Unblock Youku — https://chromewebstore.google.com/detail/unblock-youku/pdnfnkhpgegpcingjbfihlkjeighnddk")
    print("  2. Install All - Unblock Boundary — search Chrome Web Store")
    print("  3. Log in to bilibili.com with your VIP account")
    print("  4. Install 'Get cookies.txt LOCALLY' extension")
    print("  5. Visit bilibili.com, export cookies, save as:")
    print(f"       {BASE_DIR / 'cookies_dl.txt'}  (project folder — recommended)")
    print(f"       {_COOKIES_FALLBACK}  (fallback)")
    print("\nPress Ctrl+C here when you are done.\n")

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            DOWNLOADER_DATA_DIR,
            executable_path=BRAVE_EXE,
            headless=False,
            args=["--no-first-run", "--no-default-browser-check"],
            ignore_default_args=[
                "--enable-automation",
                "--disable-extensions",
                "--disable-component-extensions-with-background-pages",
                # Restore normal network behaviour so the browser feels like a real browser
                "--disable-background-networking",
                "--disable-sync",
                "--metrics-recording-only",
                "--safebrowsing-disable-auto-update",
                "--use-mock-keychain",
                "--password-store=basic",
            ],
        )

        page = ctx.new_page()
        page.goto("https://www.bilibili.com")

        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nClosing downloader profile.")
        finally:
            ctx.close()

    found = _find_cookies()
    cookies_ok = found.exists()
    print(f"\nSetup {'complete' if cookies_ok else 'incomplete'}.")
    if not cookies_ok:
        print(f"  cookies_dl.txt not found in project folder or at {_COOKIES_FALLBACK}")
        print("  Re-run this script and export cookies before pressing Ctrl+C.")
        sys.exit(1)
    print(f"  cookies_dl.txt found at: {found}")
    print("  Downloader profile is ready. You can now use the episode browser.")


if __name__ == "__main__":
    main()
