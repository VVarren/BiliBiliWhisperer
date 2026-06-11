"""Whisper transcription pipeline with jieba word segmentation and JSON caching."""

import json
from pathlib import Path

import jieba

CACHE_DIR = Path(__file__).parent / "cache"


def _cache_path(audio_path: Path) -> Path:
    return CACHE_DIR / (audio_path.stem + ".json")


def _interpolate_words(text: str, start: float, end: float) -> list[dict]:
    tokens = [t for t in jieba.cut(text) if t.strip()]
    if not tokens:
        return []
    duration = end - start
    n = len(tokens)
    return [
        {
            "word":  tok,
            "start": round(start + (i / n) * duration, 3),
            "end":   round(start + ((i + 1) / n) * duration, 3),
        }
        for i, tok in enumerate(tokens)
    ]


def _run_whisper(audio_path: Path, model, task: str) -> list:
    """Run a single Whisper pass and return a flat list of segments."""
    segments_iter, _ = model.transcribe(
        str(audio_path),
        language="zh",
        task=task,
        beam_size=5,
        vad_filter=True,
    )
    return list(segments_iter)


def _load_model(model_size: str):
    import ctranslate2
    import torch  # registers torch's CUDA DLL directory on Windows

    device = "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
    compute_type = "float16" if device == "cuda" else "int8"
    print(f"  Device: {device.upper()} | compute_type: {compute_type}")

    from faster_whisper import WhisperModel
    return WhisperModel(model_size, device=device, compute_type=compute_type)


def _add_translations(segments: list[dict], audio_path: Path, model_size: str, cache: Path) -> list[dict]:
    """Add English translations to an existing segment list and update the cache."""
    print(f"Running Whisper translation pass ({model_size})...")
    model = _load_model(model_size)
    en_segs = _run_whisper(audio_path, model, task="translate")

    # Match English segments to Chinese by closest start time
    for zh_seg in segments:
        best = min(en_segs, key=lambda s: abs(s.start - zh_seg["start"]), default=None)
        zh_seg["translation"] = best.text.strip() if best else ""

    cache.write_text(json.dumps(segments, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  Translations added and cache updated.")
    return segments


def get_segments(audio_path: Path, model_size: str = "large-v3") -> list[dict]:
    cache = _cache_path(audio_path)

    if cache.exists():
        data = json.loads(cache.read_text(encoding="utf-8"))
        # Migrate old cache that has no translations yet
        if data and "translation" not in data[0]:
            print("Cache found but missing translations — running translation pass...")
            return _add_translations(data, audio_path, model_size, cache)
        print(f"Loaded transcription from cache: {cache}")
        return data

    print(f"Transcription cache not found. Running Whisper {model_size}...")
    model = _load_model(model_size)

    print("  Pass 1/2: Chinese transcription...")
    zh_segs = _run_whisper(audio_path, model, task="transcribe")
    print(f"  Got {len(zh_segs)} segments.")

    print("  Pass 2/2: English translation...")
    en_segs = _run_whisper(audio_path, model, task="translate")

    result = []
    for i, zh in enumerate(zh_segs):
        # Match the closest English segment by start time
        best_en = min(en_segs, key=lambda s: abs(s.start - zh.start), default=None)
        words = _interpolate_words(zh.text, zh.start, zh.end)
        result.append({
            "id":          i,
            "start":       round(zh.start, 3),
            "end":         round(zh.end, 3),
            "text":        zh.text.strip(),
            "translation": best_en.text.strip() if best_en else "",
            "words":       words,
        })
        if i % 50 == 0:
            print(f"  Merged {i} segments... [{zh.start:.0f}s]")

    CACHE_DIR.mkdir(exist_ok=True)
    cache.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  Done. {len(result)} segments saved to {cache}")
    return result
