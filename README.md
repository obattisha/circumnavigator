# Circumnavigator

A Python optimizer for finding the fastest commercially-flown route around the world, targeting two Guinness World Records:

1. **Fastest circumnavigation by scheduled commercial flights** — current record: 44h 33m 39s (HKG → YVR → FRA → HKG, Nov 2024)
2. **Fastest journey visiting all six inhabited continents** — current record: 56h 56m 00s (SYD → SCL → PTY → MAD → ALG → DXB → SYD)

---

## How it works

### Circumnavigation search

**Phase 1 — Geometry filter**
Loads the OpenFlights airport and route graph (~7,000 airports, ~67,000 nonstop routes) and runs a depth-first search to enumerate every route that:
- Covers at least 360° of longitude (Guinness rule)
- Exceeds the minimum great-circle distance (~36,788 km, equivalent to the Tropic of Cancer circumference)
- Flies consistently eastbound or westbound

This produces ~96,000 candidate route geometries without any API calls.

**Phase 2 — Schedule search**
For every (departure, arrival) airport pair identified in Phase 1, schedule data is fetched from the [AirLabs Routes API](https://airlabs.co) and cached permanently to disk. A time-space priority-queue search (Dijkstra-style) then finds the globally optimal (route, date) combination using real flight departure times, arrival times, and minimum connection times per country.

**Six-continent search**
A separate search mode that finds the fastest trip visiting all six inhabited continents (Africa, Asia, Europe, North America, Oceania, South America) and returning to the origin. The search:
- Tracks which continents have been visited in the heap state
- Prunes branches where remaining legs cannot cover unvisited continents
- Uses a curated set of ~380 inter-continental route pairs as the search graph
- No longitude or distance requirements — any direction, any path

---

## Results (April 2026 schedules)

### Circumnavigation
Best found: **~44h** routes via SVO/PEK hub structures. The 2024 record route (HKG→YVR→FRA→HKG) is reproduced at ~30.5h estimated flight time, verified at rank ~796 in the candidate list.

### Six continents
Best found: **MEL → SCL → PTY → MAD → ALG → DOH → MEL — 58h 50m** (Saturday Apr 11 departure)

| # | Route | Elapsed | vs Record |
|---|-------|---------|-----------|
| 1 | MEL → SCL → PTY → MAD → ALG → DOH → MEL | 58h 50m | +1h 54m |
| 2 | MEL → SCL → PTY → MAD → CMN → DOH → MEL | 58h 50m | +1h 54m |
| 3 | MEL → SCL → PTY → MAD → ALG → DXB → MEL | 58h 55m | +1h 59m |
| 4 | SYD → SCL → PTY → MAD → ALG → DXB → SYD | 59h 20m | +2h 24m |

Route 4 is the exact record-holder pattern reproduced with April 2026 flight schedules (JL5744 / CM498 / BA4222 / IB1377 / EK758 / EK414), confirming the record-setting route still operates — just with slightly different connection timing versus the November 2024 attempt.

---

## Setup

**Requirements:** Python 3.11+, [httpx](https://www.python-httpx.org/)

```bash
pip install httpx
```

No API key is required to run Phase 1 (geometry only). For the full schedule search you need a free AirLabs API key:

```bash
export AIRLABS_API_KEY=your_key_here
```

Sign up free at [airlabs.co](https://airlabs.co). The free tier is sufficient — all results are cached permanently after the first fetch.

---

## Usage

```bash
# Circumnavigation — eastbound, top 20 results
python3 main.py --direction eastbound --max-legs 4 --top 20

# Circumnavigation — both directions, 30 results
python3 main.py --direction both --max-legs 4 --top 30

# Phase 1 geometry preview (no API key needed)
python3 main.py --geometry-only --direction eastbound --top 30

# Restrict to a specific origin airport
python3 main.py --start HKG --direction eastbound

# Six-continent world trip search
python3 main.py --six-continents --start-date 2026-04-07 --search-days 7 --top 20

# Six-continent from a specific origin
python3 main.py --six-continents --start SYD --start-date 2026-04-11 --search-days 1
```

### Key options

| Flag | Default | Description |
|------|---------|-------------|
| `--direction` | `eastbound` | `eastbound`, `westbound`, or `both` |
| `--max-legs` | `4` | Max flight legs per route |
| `--start-date` | `2026-04-07` | First departure date to try |
| `--search-days` | `7` | Number of consecutive dates to search |
| `--budget-hours` | `89` | Prune routes exceeding this time (2× record) |
| `--max-wait-hours` | `24` | Max connection wait before giving up |
| `--six-continents` | off | Enable six-continent mode |
| `--max-legs-6c` | `7` | Max legs for six-continent search |
| `--geometry-only` | off | Phase 1 only, no API calls |

---

## Project structure

```
circumnavigator/
├── main.py                          # CLI entry point
├── config.py                        # Constants, route pairs, continent mapping
├── circumnavigator/
│   ├── data/
│   │   ├── airports.py              # Airport dataclass
│   │   ├── loader.py                # OpenFlights data loader
│   │   └── routes.py                # Graph builder
│   ├── geometry/
│   │   ├── distance.py              # Haversine formula
│   │   └── longitude.py             # Longitude delta / direction helpers
│   ├── phase1/
│   │   └── enumerator.py            # DFS route geometry search
│   ├── phase2/
│   │   ├── airlabs_client.py        # AirLabs API + disk cache
│   │   └── static_scheduler.py      # ScheduledRoute / ScheduledLeg dataclasses
│   ├── search/
│   │   ├── time_space.py            # Circumnavigation Dijkstra search
│   │   └── six_continents.py        # Six-continent Dijkstra search
│   └── phase3/
│       └── reporter.py              # Formatted output + JSON persistence
└── data/                            # Auto-downloaded OpenFlights files (gitignored)
```

---

## Data sources

- **[OpenFlights](https://openflights.org/data)** — airport coordinates, nonstop route graph (public domain)
- **[AirLabs Routes API](https://airlabs.co)** — scheduled departure/arrival times, days of operation (free tier, API key required)

---

## Records being targeted

| Record | Time | Route | Date |
|--------|------|-------|------|
| Fastest circumnavigation | 44h 33m 39s | HKG → YVR → FRA → HKG | Nov 21–23, 2024 |
| Six continents fastest | 56h 56m 00s | SYD → SCL → PTY → MAD → ALG → DXB → SYD | — |
