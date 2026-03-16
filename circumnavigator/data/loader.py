"""Download and parse OpenFlights airports.dat and routes.dat."""

from __future__ import annotations

import csv
import os
import sys
from typing import Optional

import httpx

from config import AIRPORTS_URL, ROUTES_URL, AIRPORTS_FILE, ROUTES_FILE, DATA_DIR
from circumnavigator.data.airports import Airport


# --------------------------------------------------------------------------- #
# Country code lookup from timezone prefix
# --------------------------------------------------------------------------- #
_TZ_PREFIX_TO_CC: dict[str, str] = {
    "America": "US",   # rough default; refined below
    "Europe": "XX",
    "Asia": "XX",
    "Africa": "XX",
    "Pacific": "XX",
    "Atlantic": "XX",
    "Indian": "XX",
    "Australia": "AU",
}

# Airport IATA → country code mapping derived from airports.dat column 8
# (which is a DST / country in some versions).  We derive from the "country"
# name column instead via a small static map.
_COUNTRY_NAME_TO_CC: dict[str, str] = {
    "United States": "US",
    "Canada": "CA",
    "United Kingdom": "GB",
    "Germany": "DE",
    "France": "FR",
    "Netherlands": "NL",
    "United Arab Emirates": "AE",
    "Qatar": "QA",
    "Japan": "JP",
    "Singapore": "SG",
    "Australia": "AU",
    "New Zealand": "NZ",
    "Hong Kong": "HK",
    "China": "CN",
    "South Korea": "KR",
    "India": "IN",
    "Thailand": "TH",
    "Malaysia": "MY",
    "Indonesia": "ID",
    "Philippines": "PH",
    "Taiwan": "TW",
    "Turkey": "TR",
    "Russia": "RU",
    "South Africa": "ZA",
    "Kenya": "KE",
    "Ethiopia": "ET",
    "Brazil": "BR",
    "Argentina": "AR",
    "Chile": "CL",
    "Colombia": "CO",
    "Mexico": "MX",
    "Spain": "ES",
    "Italy": "IT",
    "Switzerland": "CH",
    "Austria": "AT",
    "Belgium": "BE",
    "Sweden": "SE",
    "Norway": "NO",
    "Denmark": "DK",
    "Finland": "FI",
    "Portugal": "PT",
    "Greece": "GR",
    "Poland": "PL",
    "Czech Republic": "CZ",
    "Hungary": "HU",
    "Romania": "RO",
    "Pakistan": "PK",
    "Saudi Arabia": "SA",
    "Israel": "IL",
    "Jordan": "JO",
    "Kuwait": "KW",
    "Bahrain": "BH",
    "Oman": "OM",
    "Sri Lanka": "LK",
    "Bangladesh": "BD",
    "Nepal": "NP",
    "Egypt": "EG",
    "Morocco": "MA",
    "Algeria": "DZ",
    "Tunisia": "TN",
    "Libya": "LY",
    "Nigeria": "NG",
    "Ghana": "GH",
    "Tanzania": "TZ",
    "Mozambique": "MZ",
    "Angola": "AO",
    "Cameroon": "CM",
    "Ivory Coast": "CI",
    "Cote d'Ivoire": "CI",
    "Senegal": "SN",
    "Uganda": "UG",
    "Rwanda": "RW",
    "Zimbabwe": "ZW",
    "Zambia": "ZM",
    "Namibia": "NA",
    "Botswana": "BW",
    # Central America and Caribbean
    "Panama": "PA",
    "Costa Rica": "CR",
    "Guatemala": "GT",
    "Honduras": "HN",
    "El Salvador": "SV",
    "Nicaragua": "NI",
    "Cuba": "CU",
    "Dominican Republic": "DO",
    "Jamaica": "JM",
    "Trinidad and Tobago": "TT",
    # More South America
    "Peru": "PE",
    "Ecuador": "EC",
    "Bolivia": "BO",
    "Paraguay": "PY",
    "Uruguay": "UY",
    "Venezuela": "VE",
    "Suriname": "SR",
    "Guyana": "GY",
    # More Europe
    "Ireland": "IE",
    "Croatia": "HR",
    "Serbia": "RS",
    "Bulgaria": "BG",
    "Slovakia": "SK",
    "Slovenia": "SI",
    "Albania": "AL",
    "Iceland": "IS",
    "Estonia": "EE",
    "Latvia": "LV",
    "Lithuania": "LT",
    "Luxembourg": "LU",
    "Moldova": "MD",
    "Belarus": "BY",
    "Ukraine": "UA",
    "Cyprus": "CY",
    "Malta": "MT",
    "North Macedonia": "MK",
    "Bosnia and Herzegovina": "BA",
    "Montenegro": "ME",
    "Kosovo": "XK",
    # More Asia
    "Cambodia": "KH",
    "Myanmar": "MM",
    "Laos": "LA",
    "Mongolia": "MN",
    "Uzbekistan": "UZ",
    "Kazakhstan": "KZ",
    "Azerbaijan": "AZ",
    "Georgia": "GE",
    "Armenia": "AM",
    "Iraq": "IQ",
    "Syria": "SY",
    "Lebanon": "LB",
    "Jordan": "JO",
    "Palestine": "PS",
    "Maldives": "MV",
    "Bhutan": "BT",
    "Timor-Leste": "TL",
    "Brunei": "BN",
    # Oceania
    "Papua New Guinea": "PG",
    "Fiji": "FJ",
    "Solomon Islands": "SB",
    "Vanuatu": "VU",
    "Samoa": "WS",
    "Tonga": "TO",
    "Kiribati": "KI",
    "Micronesia": "FM",
    "Nauru": "NR",
    "Palau": "PW",
    "Marshall Islands": "MH",
    "French Polynesia": "PF",
    "New Caledonia": "NC",
    "Guam": "GU",
}


def _country_code(country_name: str) -> str:
    return _COUNTRY_NAME_TO_CC.get(country_name, "XX")


# --------------------------------------------------------------------------- #
# Download helpers
# --------------------------------------------------------------------------- #

def _download(url: str, dest: str) -> None:
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    print(f"Downloading {url} → {dest}", file=sys.stderr)
    with httpx.stream("GET", url, follow_redirects=True, timeout=60) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_bytes(chunk_size=65536):
                f.write(chunk)


def ensure_data_files() -> None:
    """Download OpenFlights data files if not already cached locally."""
    if not os.path.exists(AIRPORTS_FILE):
        _download(AIRPORTS_URL, AIRPORTS_FILE)
    if not os.path.exists(ROUTES_FILE):
        _download(ROUTES_URL, ROUTES_FILE)


# --------------------------------------------------------------------------- #
# Parsers
# --------------------------------------------------------------------------- #

def load_airports() -> dict[str, Airport]:
    """Return dict of IATA code → Airport for all airports with valid IATA + coords."""
    ensure_data_files()
    airports: dict[str, Airport] = {}

    with open(AIRPORTS_FILE, encoding="utf-8", errors="replace") as f:
        reader = csv.reader(f)
        for row in reader:
            # OpenFlights airports.dat columns (0-indexed):
            # 0: ID, 1: Name, 2: City, 3: Country, 4: IATA, 5: ICAO,
            # 6: Lat, 7: Lon, 8: Alt, 9: TZ offset, 10: DST, 11: Tz (Olson), 12: Type, 13: Source
            if len(row) < 12:
                continue
            iata = row[4].strip().strip('"')
            if not iata or iata == r"\N" or len(iata) != 3:
                continue
            try:
                lat = float(row[6])
                lon = float(row[7])
            except ValueError:
                continue
            tz = row[11].strip().strip('"') if len(row) > 11 else ""
            country_name = row[3].strip().strip('"')
            airports[iata] = Airport(
                iata=iata,
                name=row[1].strip().strip('"'),
                city=row[2].strip().strip('"'),
                country=country_name,
                country_code=_country_code(country_name),
                lat=lat,
                lon=lon,
                tz=tz,
            )
    return airports


def load_routes(airports: dict[str, Airport]) -> list[tuple[str, str, str]]:
    """Return list of (src_iata, dst_iata, equipment) for all nonstop routes.

    Only includes routes where both endpoints exist in *airports*.
    """
    ensure_data_files()
    routes: list[tuple[str, str, str]] = []

    with open(ROUTES_FILE, encoding="utf-8", errors="replace") as f:
        reader = csv.reader(f)
        for row in reader:
            # routes.dat columns:
            # 0: Airline, 1: Airline ID, 2: Src airport, 3: Src airport ID,
            # 4: Dst airport, 5: Dst airport ID, 6: Codeshare, 7: Stops, 8: Equipment
            if len(row) < 8:
                continue
            stops = row[7].strip()
            if stops != "0":
                continue   # nonstop only
            src = row[2].strip().upper()
            dst = row[4].strip().upper()
            if src not in airports or dst not in airports:
                continue
            equip = row[8].strip() if len(row) > 8 else ""
            routes.append((src, dst, equip))
    return routes
