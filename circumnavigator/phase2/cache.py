"""Disk-based JSON cache for Amadeus API responses.

Cache key: (origin, destination, date_str)  → file on disk.
"""

from __future__ import annotations

import hashlib
import json
import os
from typing import Any, Optional

from config import API_CACHE_DIR


def _cache_path(origin: str, dest: str, date: str) -> str:
    key = f"{origin}_{dest}_{date}"
    # Use hash to keep filenames short
    h = hashlib.sha1(key.encode()).hexdigest()[:16]
    return os.path.join(API_CACHE_DIR, f"{key}_{h}.json")


def cache_get(origin: str, dest: str, date: str) -> Optional[Any]:
    path = _cache_path(origin, dest, date)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return None


def cache_set(origin: str, dest: str, date: str, data: Any) -> None:
    os.makedirs(API_CACHE_DIR, exist_ok=True)
    path = _cache_path(origin, dest, date)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)
