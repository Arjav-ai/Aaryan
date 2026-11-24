"""Small, polite client for ESPN's free public JSON (used for every sport except NBA).

Responses are cached on disk. Finished data is cached forever; anything that can still change
(today's scoreboard, the current month) uses a short time limit instead.
"""
import hashlib
import json
import time
from pathlib import Path

import requests

BASE = "https://site.api.espn.com/apis/site/v2/sports"
CACHE_DIR = Path("data/cache/espn")
MIN_DELAY = 0.25
HEADERS = {"User-Agent": "Mozilla/5.0 (personal research project)"}
_last = 0.0


def get(path: str, ttl: float | None = None, pace: bool = True, **params) -> dict:
    """GET {BASE}/{path}?params -> parsed JSON. ttl = seconds the cached copy stays valid (None = forever)."""
    global _last
    key = hashlib.sha1((path + json.dumps(params, sort_keys=True)).encode()).hexdigest()
    f = CACHE_DIR / f"{key}.json"
    if f.exists() and (ttl is None or time.time() - f.stat().st_mtime < ttl):
        return json.loads(f.read_text())
    wait = MIN_DELAY - (time.time() - _last)
    if pace and wait > 0:   # pace=False: caller limits concurrency itself (a small thread pool)
        time.sleep(wait)
    for attempt in range(4):
        r = requests.get(f"{BASE}/{path}", params=params, headers=HEADERS, timeout=40)
        _last = time.time()
        if r.status_code in (429, 500, 502, 503):
            time.sleep(2 ** attempt)
            continue
        r.raise_for_status()
        break
    else:
        raise RuntimeError(f"ESPN kept failing for {path}")
    data = r.json()
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(data))
    return data
