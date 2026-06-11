"""CC-CEDICT offline Chinese-English dictionary."""

import gzip
import re
import urllib.request
from pathlib import Path

CEDICT_URL  = "https://www.mdbg.net/chinese/export/cedict/cedict_1_0_ts_utf-8_mdbg.txt.gz"
DATA_PATH   = Path(__file__).parent / "data" / "cedict_ts.u8"
LINE_RE     = re.compile(r'^(\S+)\s+(\S+)\s+\[([^\]]+)\]\s+/(.+)/$')

_index: dict[str, list[dict]] = {}


def _download() -> None:
    DATA_PATH.parent.mkdir(exist_ok=True)
    print("Downloading CC-CEDICT dictionary (~7 MB)...")
    tmp = DATA_PATH.with_suffix(".gz")
    urllib.request.urlretrieve(CEDICT_URL, tmp)
    with gzip.open(tmp, "rb") as gz, open(DATA_PATH, "wb") as out:
        out.write(gz.read())
    tmp.unlink()
    print(f"  Saved to {DATA_PATH}")


def build_index() -> None:
    global _index
    if not DATA_PATH.exists():
        _download()

    print("Loading dictionary...", end=" ", flush=True)
    idx: dict[str, list[dict]] = {}
    with open(DATA_PATH, encoding="utf-8") as f:
        for line in f:
            if line.startswith("#"):
                continue
            m = LINE_RE.match(line.rstrip())
            if not m:
                continue
            trad, simp, pinyin, defs_raw = m.groups()
            entry = {
                "traditional": trad,
                "simplified":  simp,
                "pinyin":      pinyin,
                "definitions": defs_raw.split("/"),
            }
            idx.setdefault(simp, []).append(entry)
            if trad != simp:
                idx.setdefault(trad, []).append(entry)

    _index = idx
    print(f"{len(_index):,} entries loaded.")


def lookup(word: str) -> list[dict]:
    return _index.get(word, [])
