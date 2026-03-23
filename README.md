# Circumnavigator

A Python optimizer for finding the fastest commercially-flown route around the world, targeting three Guinness World Records:

1. **Fastest circumnavigation by scheduled commercial flights** — current record: 44h 33m 39s (HKG → YVR → FRA → HKG, Nov 2024)
2. **Fastest journey visiting all six inhabited continents** — current record: 56h 56m 00s (SYD → SCL → PTY → MAD → ALG → DXB → SYD)
3. **Fastest circumnavigation through two antipodal points** — current record: 52h 34m 00s (PVG → AKL → EZE → AMS → PVG, Jan 2018, Andrew Fisher)

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

**Antipodal circumnavigation search**
A third search mode targets the Guinness record for fastest circumnavigation passing through two near-antipodal airports. Rules: full 360° longitude coverage in one direction, ≥36,788 km minimum distance, must cross the equator, must land and change planes at two airports forming a near-antipodal pair (independent ≤5° tolerance per dimension: `|lat1 + lat2| ≤ 5°` AND circular longitude gap ≤ 5°). The search is identical to the standard circumnavigation Dijkstra but carries one additional state bit (`ap_pair_met`) that gates the closing leg. Antipodal pairs are computed at runtime from the flight graph with `O(n²)` geometry.

**Six-continent search**
A separate search mode that finds the fastest trip visiting all six inhabited continents (Africa, Asia, Europe, North America, Oceania, South America) and returning to the origin. The search:
- Tracks which continents have been visited in the heap state
- Prunes branches where remaining legs cannot cover unvisited continents
- Uses a curated set of ~380 inter-continental route pairs as the search graph
- No longitude or distance requirements — any direction, any path

---

## Results (April 2026 schedules)

### Circumnavigation (FAI/Guinness)

**Records landscape:**

| Record | Time | Route | Distance | Notes |
|--------|------|-------|----------|-------|
| FAI (Concorde, unbeatable subsonic) | 44h 06m | LAX → LHR → BAH → SIN → BKK → MNL → NRT → HNL → LAX | 37,082 km | David Springbett, Jan 1980 |
| Guinness GWR 63169 (current) | 44h 33m 39s | HKG → YVR → FRA → HKG | ~27,500 km | Nov 21–23, 2024 — likely below 36,787 km FAI floor |
| **Subsonic record to beat** | **46h 23m 11s** | **LAX → DOH → BNE → LAX** | **37,215 km** | Umit Sabanci, Aug 2022 — FAI-compliant |

**Best found: LAX → DOH → BNE → LAX — 47h 20m** (scheduled, April 2026)

The optimizer independently converged on the same route as Sabanci's record: LAX → DOH → BNE → LAX. The 57-minute gap from the 46h 23m record is recoverable through real-world flight timing (see below).

**Top 10 routes (eastbound, April 2026 schedules, all ≥36,787 km FAI-compliant):**

| # | Route | Elapsed | Distance |
|---|-------|---------|----------|
| 1 | LAX → DOH → BNE → LAX | 47h 20m | 37,210 km |
| 2 | YVR → FRA → SIN → SYD → YVR | 49h 45m | 37,136 km |
| 3 | DOH → BNE → LAX → MUC → DOH | 50h 35m | 37,782 km |
| 4 | LHR → DXB → SYD → YVR → LHR | 50h 40m | 37,621 km |
| 5 | LHR → DOH → BNE → LAX → LHR | 50h 50m | 37,865 km |
| 6 | SFO → DXB → SYD → HNL → SFO | 50h 55m | 37,091 km |
| 7 | LAX → DXB → SYD → HNL → LAX | 50h 56m | 37,723 km |
| 8 | BNE → LAX → CDG → DXB → BNE | 51h 00m | 37,854 km |
| 9 | BNE → LAX → MUC → DXB → BNE | 51h 00m | 37,692 km |
| 10 | BNE → LAX → LHR → DXB → BNE | 51h 00m | 37,770 km |

`output/results.json` contains all 60 valid FAI-compliant routes found.

**Leg details for LAX → DOH → BNE → LAX (April 2026 schedules):**

| Flight | Leg | Dep (UTC) | Arr (UTC) | Block |
|--------|-----|-----------|-----------|-------|
| AA8226 (QR codeshare) | LAX → DOH | Apr 7 23:10 | Apr 8 14:50 | 940 min |
| AT5735 (QR codeshare) | DOH → BNE | Apr 8 17:20 | Apr 9 07:30 | 850 min |
| AA7380 (QF codeshare) | BNE → LAX | Apr 9 09:40 | Apr 9 22:30 | 770 min |

#### Why the scheduled 47h 20m can beat the 46h 23m record in practice

Guinness elapsed time is measured from **actual first departure to actual last arrival**. Intermediate early arrivals are irrelevant — you wait for the next scheduled connection. The only variables that affect total elapsed time are:

1. **First departure delay** — a late QR LAX→DOH departure *reduces* elapsed time (clock starts later, last arrival unchanged)
2. **Last arrival** — an early QF BNE→LAX arrival *reduces* elapsed time
3. **Connection integrity** — delays must not cause a missed connection at DOH or BNE

Sabanci's own 46h 23m 11s relied on exactly this: QR LAX→DOH routinely departs 20–60 minutes late at LAX due to slot congestion and pushback queues, and QF BNE→LAX carries generous block padding that frequently delivers early arrivals at LAX.

A 57-minute late departure from LAX (within normal variance) + 15-minute early BNE→LAX arrival = **~45h 58m actual**, beating Sabanci's record.

### Six continents
Best found: **SYD → SCL → PTY → MAD → ALG → DXB → SYD — 58h 10m** (Wednesday Apr 8 departure)

| # | Route | Elapsed | vs Record |
|---|-------|---------|-----------|
| 1 | SYD → SCL → PTY → MAD → ALG → DXB → SYD | 58h 10m | +1h 14m |
| 2 | MEL → SCL → PTY → MAD → ALG → DOH → MEL | 59h 20m | +2h 24m |
| 3 | MEL → SCL → PTY → MAD → ALG → DXB → MEL | 59h 25m | +2h 29m |
| 4 | DXB → SYD → SCL → PTY → MAD → ALG → DXB | 62h 55m | +5h 59m |

Route 1 is the exact record-holder pattern (MU4082/QF27 / CM498 / BA4222 / IB1377 / EK758 / EK414) reproduced with April 2026 schedules. The route is only feasible on **Wednesday/Saturday/Monday departures** from SYD — BA4222 (PTY→MAD) operates Mon/Wed/Sat only, and the SYD→SCL→PTY chain arrives PTY the same day it departs SYD.

#### Why the record is 1h 14m faster than today's best schedule

The 56h 56m record uses the same six flights. The gap is almost entirely explained by one change: **QF27 now departs SYD at 01:20 UTC (12:20 AEDT)** versus **02:29 UTC (13:29 AEDT) in January 2018** — 1h 09m earlier. Since EK414 still arrives SYD at 11:30 UTC, the last arrival is unchanged, and starting the clock 1h 09m earlier adds ~1h 09m to elapsed time. The remaining ~5 min comes from EK758 (ALG→DXB) now departing 35 min later (14:45 vs 14:10 UTC in 2018), though this does not affect the EK414 connection since there is still a 50-minute window at DXB.

### Antipodal circumnavigation

**Current record:** Andrew Fisher, 52h 34m 00s — PVG → AKL → EZE → AMS → PVG (January 21–23, 2018)
Antipodal pair: PVG (31.1°N 121.8°E) ↔ EZE (34.8°S 58.5°W) — lat_off 3.68°, lon_off 0.34°

**Best found: DOH → AKL → LAX → MAD → DOH — 52h 55m** (scheduled, April 2026)
Antipodal pair: AKL (37.0°S 174.8°E) ↔ MAD (40.5°N 3.7°W) — lat_off 3.46°, lon_off 1.65°

The search found 68 near-antipodal airport pairs across the long-haul graph. The AKL↔MAD pair dominates the top results because it sits on two of the most efficient transoceanic corridors (Australasia–North America and US West Coast–Europe).

**Top 10 routes (both directions, April 2026 schedules):**

| # | Route | Elapsed | vs 52h34m | Antipodal pair |
|---|-------|---------|-----------|----------------|
| 1 | DOH → AKL → LAX → MAD → DOH | 52h 55m | +21m | AKL ↔ MAD |
| 2 | PEK → AKL → SCL → MAD → PEK | 54h 15m | +1h 41m | AKL ↔ MAD |
| 3 | MAD → DOH → AKL → LAX → MAD | 54h 15m | +1h 41m | MAD ↔ AKL |
| 4 | MAD → PEK → AKL → SCL → MAD | 55h 10m | +2h 36m | AKL ↔ MAD |
| 5 | MAD → ICN → ATL → EZE → MAD | 55h 45m | +3h 11m | ICN ↔ EZE |
| 6 | MAD → ICN → JFK → EZE → MAD | 55h 45m | +3h 11m | ICN ↔ EZE |
| 7 | EZE → CDG → ICN → ATL → EZE | 56h 40m | +4h 06m | EZE ↔ ICN |
| 8 | AKL → EZE → MAD → DXB → PER → AKL | 57h 15m | +4h 41m | AKL ↔ MAD |
| 10 | MAD → PEK → AKL → EZE → MAD | 58h 00m | +5h 26m | AKL ↔ MAD |
| 11 | AKL → EZE → FRA → PVG → AKL | 58h 10m | +5h 36m | EZE ↔ PVG |

Route #3 is the same loop as #1 starting from MAD instead of DOH — the 1h20m gap is exactly the cost of including the DOH layover inside the elapsed clock. Route #11 uses Fisher's original EZE↔PVG antipodal pair but is 5h36m slower than the best route.

---

#### Why the scheduled 52h55m can beat the 52h34m record in practice

The Guinness elapsed time is measured from **actual first departure to actual last arrival**. Intermediate early arrivals are irrelevant — you wait for the next scheduled connection anyway. The only variables that affect total elapsed time are:

1. **First departure delay** — a late QR920 departure from DOH *reduces* elapsed time (clock starts later, last arrival is unchanged)
2. **Last arrival** — an early IB6226 arrival at DOH *reduces* elapsed time
3. **Connection integrity** — delays must not cause a missed connection

Fisher's own 52h34m relied on exactly this: NZ284 departed PVG **28 minutes late** (clock started later) and MU772 arrived PVG **8 minutes early** — 36 minutes of savings off his 53h10m timetable.

For the DOH→AKL→LAX→MAD→DOH route, the key constraint is that **QR920 must depart DOH on a Saturday, Tuesday, or Thursday (UTC)** — otherwise IB352 (LAX→MAD, which operates Sun/Wed/Fri) does not run when NZ6 arrives at LAX.

#### Historical analysis: Winter 2025/26 (Oct 2025 – Mar 2026)

Using actual flight data from flightera.net, 12 dates in the Winter 2025/26 schedule period would have beaten Fisher's record, assuming all connections were made:

| QR920 dep date | Day | QR920 dep delay | IB6226 arr delay | **Actual elapsed** | vs 52h34m |
|----------------|-----|-----------------|------------------|-------------------|-----------|
| Dec 25, 2025 | Thu | +38 min late | −8 min early | **51h 31m** | **−1h 03m** |
| Jan 17, 2026 | Sat | +27 min late | −3 min early | **51h 58m** | −36 min |
| Feb 19, 2026 | Thu | +30 min late | +5 min late | **52h 00m** | −34 min |
| Dec 27, 2025 | Sat | +24 min late | +2 min late | **52h 09m** | −25 min |
| Jan 31, 2026 | Sat | +23 min late | on time | **52h 09m** | −25 min |
| Jan 22, 2026 | Thu | +28 min late | +14 min late | **52h 13m** | −21 min |
| Feb 12, 2026 | Thu | +27 min late | +12 min late | **52h 13m** | −21 min |
| Jan 24, 2026 | Sat | +24 min late | +10 min late | **52h 17m** | −17 min |
| Jan 29, 2026 | Thu | +24 min late | +12 min late | **52h 19m** | −15 min |
| Dec 11, 2025 | Thu | +22 min late | +13 min late | **52h 24m** | −10 min |
| Feb 17, 2026 | Tue | +22 min late | +14 min late | **52h 25m** | −9 min |
| Dec 23, 2025 | Tue | +11 min late | −1 min early | **52h 32m** | −2 min |

QR920 routinely departs DOH 20–40 minutes late due to standard slot and pushback delays, which directly shaves time off the elapsed total. No date in this dataset showed a QR920 AKL arrival delay ≥90 minutes (the threshold for missing the NZ6 connection).

**~30% of valid Sat/Tue/Thu departures in the Dec–Feb window beat the record.** November and late February/March were weaker periods due to IB6226 running chronically late out of Madrid.

**Optimal attempt window: December–January, departing DOH on Saturday or Thursday.**

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

# Antipodal circumnavigation (Andrew Fisher's record)
python3 main.py --antipodal --direction both --top 20

# Antipodal — wider date window, both directions
python3 main.py --antipodal --direction both --start-date 2026-12-01 --search-days 14 --top 20
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
│   ├── geometry/
│   │   ├── antipodal.py             # Near-antipodal pair detection + build_antipodal_partners()
│   ├── search/
│   │   ├── time_space.py            # Circumnavigation Dijkstra search
│   │   ├── six_continents.py        # Six-continent Dijkstra search
│   │   └── antipodal.py             # Antipodal circumnavigation search (time_space + ap_pair_met bit)
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

| Record | Time | Route | Date | Notes |
|--------|------|-------|------|-------|
| Circumnavigation (FAI, Concorde) | 44h 06m | LAX → LHR → BAH → SIN → BKK → MNL → NRT → HNL → LAX | Jan 1980 | Springbett; unbeatable by subsonic |
| Circumnavigation (Guinness GWR 63169) | 44h 33m 39s | HKG → YVR → FRA → HKG | Nov 21–23, 2024 | ~27,500 km — likely below FAI distance floor |
| **Circumnavigation (subsonic, FAI-compliant)** | **46h 23m 11s** | **LAX → DOH → BNE → LAX** | **Aug 2022** | **Sabanci; 37,215 km — actual target** |
| Six continents fastest | 56h 56m 00s | SYD → SCL → PTY → MAD → ALG → DXB → SYD | — | |
| Antipodal circumnavigation | 52h 34m 00s | PVG → AKL → EZE → AMS → PVG | Jan 21–23, 2018 | Andrew Fisher |
