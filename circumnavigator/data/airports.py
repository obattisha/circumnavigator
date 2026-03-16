"""Airport dataclass and parsing helpers."""

from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Airport:
    iata: str          # 3-letter IATA code
    name: str
    city: str
    country: str       # country name
    country_code: str  # ISO 2-letter (inferred from timezone or left "XX")
    lat: float
    lon: float
    tz: str            # Olson timezone string e.g. "Asia/Hong_Kong"

    def __str__(self) -> str:
        return f"{self.iata} ({self.city}, {self.country})"
