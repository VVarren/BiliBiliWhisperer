# Bilibili Chinese Learning App

Extract audio from Bilibili official dubbed and subbed anime episodes and study Mandarin through an interactive transcript viewer — with pinyin, English translations, and dictionary lookups for every word.

---

## Features

- **Episode browser** — Paste any Bilibili episode URL, get the full season list, and download episodes in the background without closing your main browser; previously loaded seasons are saved as one-click chips
- **Bulk download & transcribe** — Queue a range of episodes (e.g. Ep 1–25) in one click; each episode downloads then transcribes sequentially with a live progress bar and per-row status (Queued → In Progress → Transcribing → Ready)
- **Audio extraction** — Downloads the audio track from any Bilibili bangumi episode, bypassing region locks via your Brave browser extensions (Unblock Youku / Unblock Boundary)
- **AI transcription** — Transcribes Chinese audio with OpenAI Whisper (`large-v3`) running on your GPU
- **English translation** — Automatically translates every sentence to English (contextual, via Whisper's translation mode)
- **Interactive transcript** — Sentences scroll and highlight in sync with the audio as it plays
- **Word lookup** — Click any Chinese word for instant pinyin and English definitions (CC-CEDICT, 198k entries, fully offline)
- **Search** — Filter the full transcript by any Chinese word or phrase
- **Volume control** — Slider + mute toggle in the player bar

---

## Requirements

- Windows 10/11
- Python 3.11–3.13
- NVIDIA GPU (recommended — RTX 4090 tested; CPU fallback works but is slow)
- [Brave browser](https://brave.com) with **Unblock Youku** and **All - Unblock Boundary** extensions installed and active
- A Bilibili account with VIP

---

## Setup

### 1. Install ffmpeg

```
winget install Gyan.FFmpeg
```

Restart your terminal after so `ffmpeg` is on your PATH.

### 2. Install PyTorch (CUDA)

```
pip install torch --index-url https://download.pytorch.org/whl/cu124
```

For CPU-only (much slower transcription):
```
pip install torch --index-url https://download.pytorch.org/whl/cpu
```

### 3. Install Python dependencies

```
pip install -r requirements.txt
```

### 4. Set up the dedicated downloader Brave profile

The downloader uses a **separate Brave data directory** so your main Brave window can stay open during downloads. This is a one-time setup.

Run the setup script — it uses Playwright to open the downloader profile correctly (your main Brave stays open):
```
python setup_downloader_profile.py
```

In the new Brave window that opens:

1. Install **Unblock Youku** and **All - Unblock Boundary** from the Chrome Web Store
2. Log in to Bilibili with your VIP account
3. Install **"Get cookies.txt LOCALLY"**, visit [bilibili.com](https://www.bilibili.com), export cookies, and save as `cookies_dl.txt` in the project folder:
```
C:\dev\Personal\BiliBiliWhisperer\cookies_dl.txt
```

Then press **Ctrl+C** in the terminal to close the setup script. The script confirms that `cookies_dl.txt` was found before exiting.

> **Why not just run `brave.exe --user-data-dir="..."`?** When Brave is already open, that command is intercepted by the running instance and opens a tab in your *existing* window instead of a new profile — the Downloader Data directory never gets set up.

### 5. Export cookies from your main Brave profile

The episode browser fetches the season episode list using your main Brave cookies (no region proxy needed for catalog data). Install **"Get cookies.txt LOCALLY"** in your main Brave, visit [bilibili.com](https://www.bilibili.com), export, and save as `cookies.txt` in the project folder:
```
C:\dev\Personal\BiliBiliWhisperer\cookies.txt
```

---

## Usage

### Starting the app

```
python app.py
```

Opens in **browse mode** — the episode browser tab is shown by default. The browser opens automatically at `http://localhost:8765`.

You can also launch directly into a specific episode if you already have its audio:
```
python app.py 691461
python app.py output/ep691461_audio.m4a
```

### Downloading and studying episodes

1. In the **Episodes** tab, paste any Bilibili bangumi URL or episode ID into the input and click **Load Season**.
2. The full season episode list appears. Episodes already downloaded show a **Study** button; others show **Download**.
3. Click **Download** on an individual episode — it downloads in the background. Your main Brave window stays open. A live progress bar appears in the row and updates every 2 seconds while the audio is streaming.
4. Once the status changes to **Ready**, click **Study** to load the transcript and begin.

Previously loaded seasons are saved automatically. Season name chips appear below the input on reload — click one to jump straight back without re-pasting the URL.

### Bulk download & transcribe

To download and transcribe a range of episodes in one go, use the **Bulk Download & Transcribe** panel below the episode list:

1. Set the **From** and **To** episode numbers (1-based index in the loaded season).
2. Choose a Whisper model size.
3. Click **Start** — episodes process sequentially: download first, then transcribe.

While the batch runs, each episode row updates in real time:

| Status | Meaning |
|--------|---------|
| **Queued** (blue) | Waiting in the batch queue |
| **In Progress...** (yellow) | Downloading audio |
| **Transcribing...** (yellow) | Running Whisper |
| **Ready** (green) | Done — Study button appears |

Episodes already downloaded skip straight to transcription. The progress bar and status text in the panel show overall progress.

### Model size

By default the app uses Whisper `large-v3`. On first run it downloads the model (~3 GB) and transcribes the episode — about 5–8 minutes on an RTX 4090 for a 30-minute episode. All subsequent runs load instantly from cache.

| Flag | Model | Speed (4090) | Accuracy |
|------|-------|-------------|----------|
| *(default)* | `large-v3` | ~5–8 min | Best |
| `--medium` | `medium` | ~2–3 min | Good |
| `--small` | `small` | ~1 min | Fair |

```
python app.py 691461 --small
```

### Downloading audio manually

If you prefer to run the downloader separately:
```
python extract_audio.py 691461
python extract_audio.py "https://www.bilibili.com/bangumi/play/ep691461"
```

The downloader Brave profile opens in a new window, fetches the audio stream, downloads it to `output/`, then closes. Main Brave is unaffected.

---

## App interface

### Transcript view

```
┌─────────────────────────────────────────────────────────┐
│  [中文学习]  [Episodes]    [Search: ____________]         │
├─────────────────────────────────────────────────────────┤
│ ▶ 0:12  我 不是 一个 普通 的 父亲   ← active             │
│         I'm not an ordinary father                      │
│   0:15  今天 的 任务 是 ...                              │
│         Today's mission is...                           │
│   ...                                                   │
├─────────────────────────────────────────────────────────┤
│  [⏮] [▶] [⏭]  ────●────  0:12 / 24:05   🔊 ──────     │
└─────────────────────────────────────────────────────────┘
```

| Action | Result |
|--------|--------|
| Click timestamp | Seek audio to that sentence |
| Click Chinese word | Show pinyin and definitions |
| Spacebar | Play / pause |
| Search bar | Filter sentences by word or phrase (Escape to clear) |
| Volume icon | Mute / unmute |

### Episode browser

```
┌─────────────────────────────────────────────────────────┐
│  [中文学习]  [Episodes]                                   │
├─────────────────────────────────────────────────────────┤
│  [paste episode URL or ID ________________] [Load Season]│
│  [间谍过家家 第一季]  [Re:Zero 第二季]  ← recent seasons │
│                                                         │
│  ┌ Bulk Download & Transcribe ──────────────────────┐   │
│  │ Episodes [1] to [25]  Model [large-v3]  [Start]  │   │
│  │ ████████████░░░░░░░  Transcribing ep 8 · 7/25    │   │
│  └──────────────────────────────────────────────────┘   │
│                                                         │
│  Ep 1   间谍过家家 第1话   ✓ Ready        [Study]        │
│  Ep 7   间谍过家家 第7话   ✓ Ready        [Study]        │
│  Ep 8   间谍过家家 第8话   Transcribing…                 │
│  Ep 9   间谍过家家 第9话   Queued                        │
│  Ep 10  间谍过家家 第10话  Downloading ▓▓░░ 43%          │
│  Ep 11  间谍过家家 第11话  – Not downloaded  [Download]  │
└─────────────────────────────────────────────────────────┘
```

---

## Project structure

```
BiliBiliWhisperer/
├── extract_audio.py             # Brave automation + Bilibili DASH audio download
├── app.py                       # FastAPI entry point, all API routes, browser launch
├── bilibili_api.py              # Bilibili season/episode metadata API (requests + cookies)
├── transcribe.py                # Whisper two-pass pipeline + jieba + JSON cache
├── dictionary.py                # CC-CEDICT offline dictionary (198k entries)
├── setup_downloader_profile.py  # One-time setup for the dedicated Brave downloader profile
├── requirements.txt
├── data/
│   └── cedict_ts.u8             # CC-CEDICT data file (downloaded on first run)
├── cache/                       # Whisper transcription cache (JSON, one file per episode)
├── logs/                        # Download logs (one per episode, shown in UI on error)
├── output/                      # Downloaded .m4a audio files
└── static/
    └── index.html               # Entire frontend — vanilla JS, no build step
```

---

## How it works

### Audio extraction
Bilibili locks bangumi content by region. Your Brave extensions (Unblock Youku / Unblock Boundary) handle the unblocking — but only for browser-originated requests. `extract_audio.py` launches a **dedicated Brave profile** (separate data directory) via Playwright, calls the Bilibili DASH playurl API from inside the browser page (`page.evaluate`), gets a signed CDN URL, then downloads the audio with Python. Because the downloader uses its own data directory, your main Brave window is never touched.

### Episode browser
`bilibili_api.py` calls the Bilibili public season API to fetch episode metadata (titles, durations, ep_ids). This endpoint is not region-locked, so it works via plain Python requests with your main Brave cookies. The app spawns `extract_audio.py` as a background subprocess for each requested download, writes its output to `logs/ep{id}_download.log`, and polls the file system for status. If a download fails, the last 20 lines of the log are shown directly below the episode row in the UI. Previously loaded season URLs are persisted in the browser's `localStorage` so they survive page reloads.

### Bulk download
The batch endpoint (`POST /api/batch`) accepts a list of ep_ids and runs `_run_batch()` in a background thread. Episodes are processed sequentially — download then transcribe — to avoid `SingletonLock` conflicts between Brave instances and GPU contention during Whisper. The frontend polls `/api/batch/status` every 2 seconds and updates each episode row in real time (Queued → In Progress → Transcribing → Ready).

### Transcription
`transcribe.py` runs two Whisper passes on the `.m4a` file:
1. **Transcribe** (`task="transcribe"`, `language="zh"`) → Chinese sentence segments with timestamps
2. **Translate** (`task="translate"`) → English translations, matched to Chinese segments by timestamp

`jieba` splits each Chinese segment into individual words; word-level timestamps are linearly interpolated across the segment duration. Results are cached as JSON — the app loads instantly on all subsequent runs. Switching episodes via the browser reloads from cache instantly if the episode was previously transcribed.

### Dictionary
CC-CEDICT is downloaded once from mdbg.net (~7 MB gzip), parsed into a Python dict keyed by simplified Chinese characters, and held in memory. Lookups are O(1). If a multi-character word isn't found, each character is looked up individually and the pinyins are combined.

---

## Troubleshooting

**`cublas64_12.dll` not found**
PyTorch CUDA was not installed correctly. Re-run:
```
pip install torch --index-url https://download.pytorch.org/whl/cu124
```

**SingletonLock error on the downloader**
A previous downloader run crashed and left a stale lock. The script clears it automatically on startup; if the script itself can't start, delete the files manually:
```
del "C:\Users\<you>\AppData\Local\BraveSoftware\Brave-Browser\Downloader Data\SingletonLock"
del "C:\Users\<you>\AppData\Local\BraveSoftware\Brave-Browser\Downloader Data\SingletonSocket"
```

**Download fails immediately / "cookies_dl.txt not found"**
The downloader profile hasn't been set up yet. Run:
```
python setup_downloader_profile.py
```
Follow the instructions to install extensions, log in to Bilibili, and export `cookies_dl.txt` into the project folder.

**Download fails with an error in the episode row**
The error log from `extract_audio.py` is shown directly below the episode. Common causes:
- Extensions didn't unblock the region in time — click Retry
- The downloader Brave profile lost its session — re-run `setup_downloader_profile.py` to log back in and export fresh cookies

**Season list won't load ("API error")**
Make sure `cookies.txt` (from your main Brave) is up to date. Export fresh cookies and save to the project folder as `cookies.txt`.

**No audio in browser**
Use Chrome or Edge — Firefox doesn't support AAC (`.m4a`) without codecs.

**Transcription looks wrong / gibberish**
Try `--medium` or `--small` — occasionally `large-v3` hallucinates on short silent segments. Delete the cache file in `cache/` to re-run.
