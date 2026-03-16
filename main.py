#!/usr/bin/env python3
"""Commercial Flight Circumnavigation Optimizer — CLI entry point.

Goal: Beat the Guinness World Record of 44h 33m 39s
      (HKG → YVR → FRA → HKG, Nov 21-23 2024).

The search is UNIFIED: route geometry and real flight schedules are optimised
simultaneously.  No pre-committed route list is passed to a scheduler — the
priority-queue search finds the globally optimal (route, schedule) pair.

Flow:
  1. Build the long-haul airport graph from OpenFlights (fast, no API).
  2. Enumerate all geometrically valid routes with the Phase 1 DFS — this
     identifies every (dep, arr) pair that could appear in a valid route.
     Supplemental pairs (Qatar Airways etc. missing from OpenFlights) are
     appended automatically.
  3. Fetch AirLabs schedule data for ALL those pairs (cached forever).
  4. Run the time-space priority-queue search over the full schedule graph.
     Connection waits are real, not assumed minimums.

Usage examples:
  # Eastbound search (default)
  python3 main.py --direction eastbound --max-legs 4 --top 20

  # Both directions
  python3 main.py --direction both --max-legs 4 --top 30

  # Focus on a specific origin
  python3 main.py --start LAX --direction eastbound

  # Phase 1 geometry only (no API, quick preview)
  python3 main.py --geometry-only --direction eastbound --top 30
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(__file__))

from config import (
    GUINNESS_MIN_DISTANCE_KM, MIN_ROUTE_DISTANCE_KM,
    SUPPLEMENTAL_PAIRS, SIX_CONTINENT_PAIRS,
)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Circumnavigation optimizer — beat the 44h33m Guinness record."
    )
    p.add_argument(
        "--direction", choices=["eastbound", "westbound", "both"], default="eastbound"
    )
    p.add_argument("--start", default=None, metavar="IATA",
                   help="Restrict search to routes starting at this airport.")
    p.add_argument("--max-legs", type=int, default=4,
                   help="Max legs per route (default 4).")
    p.add_argument("--start-date", default="2026-04-07",
                   help="First departure date to try (YYYY-MM-DD).")
    p.add_argument("--search-days", type=int, default=7,
                   help="Number of departure dates to try (default 7 = one week).")
    p.add_argument("--max-wait-hours", type=int, default=24,
                   help="Give up on a connection if no flight within this window (default 24h).")
    p.add_argument("--budget-hours", type=float, default=89.0,
                   help="Prune routes exceeding this elapsed time (default 89h = 2× record).")
    p.add_argument("--top", type=int, default=20,
                   help="Top results to display (default 20).")
    p.add_argument("--skip-min-distance", action="store_true", default=False,
                   help=f"Skip Guinness min distance check ({GUINNESS_MIN_DISTANCE_KM:,.0f} km).")
    p.add_argument("--min-route-distance", type=float, default=None,
                   help="Override minimum per-leg great-circle filter (km).")
    p.add_argument("--geometry-only", action="store_true", default=False,
                   help="Run Phase 1 geometry search only (no API calls).")
    p.add_argument("--six-continents", action="store_true", default=False,
                   help="Search for fastest trip visiting all six continents "
                        "(record: 56h 56m, SYD→SCL→PTY→MAD→ALG→DXB→SYD).")
    p.add_argument("--max-legs-6c", type=int, default=7,
                   help="Max legs for six-continent search (default 7).")
    p.add_argument("--budget-hours-6c", type=float, default=80.0,
                   help="Prune budget for six-continent search (default 80h).")
    return p.parse_args()


# --------------------------------------------------------------------------- #
# Phase 1: geometry (unchanged from before — used to collect pairs to fetch)
# --------------------------------------------------------------------------- #

def build_graph_and_candidates(args):
    from circumnavigator.data.loader import load_airports, load_routes
    from circumnavigator.data.routes import build_graph
    from circumnavigator.phase1.enumerator import enumerate_all

    print("Loading OpenFlights data...", file=sys.stderr)
    airports = load_airports()
    raw_routes = load_routes(airports)

    min_dist = args.min_route_distance or MIN_ROUTE_DISTANCE_KM
    print(f"Building long-haul graph (min leg: {min_dist:,.0f} km)...", file=sys.stderr)
    graph = build_graph(airports, raw_routes, min_distance_km=min_dist)
    print(f"Graph: {len(graph)} airports, "
          f"{sum(len(v) for v in graph.values())} edges", file=sys.stderr)

    directions = (
        ["eastbound", "westbound"] if args.direction == "both" else [args.direction]
    )
    all_candidates = []
    for direction in directions:
        print(f"Enumerating {direction} routes...", file=sys.stderr)
        candidates = enumerate_all(
            airports, graph,
            direction=direction,
            max_legs=args.max_legs,
            require_min_distance=not args.skip_min_distance,
            start_filter=args.start,
        )
        print(f"  {len(candidates)} {direction} candidates.", file=sys.stderr)
        all_candidates.extend(candidates)

    all_candidates.sort(key=lambda r: r.estimated_elapsed_hours)
    return airports, graph, all_candidates


def collect_pairs(candidates, supplemental=True) -> list[tuple[str, str]]:
    """Collect every (dep, arr) pair from all candidates plus supplemental pairs."""
    seen: set[tuple[str, str]] = set()
    pairs: list[tuple[str, str]] = []

    def _add(d, a):
        if (d, a) not in seen:
            seen.add((d, a))
            pairs.append((d, a))

    for c in candidates:
        for i in range(len(c.airports) - 1):
            _add(c.airports[i], c.airports[i + 1])

    if supplemental:
        for d, a in SUPPLEMENTAL_PAIRS:
            _add(d, a)

    return pairs


# --------------------------------------------------------------------------- #
# Unified search
# --------------------------------------------------------------------------- #

def run_unified(args) -> None:
    from circumnavigator.phase2.airlabs_client import prefetch_all_pairs
    from circumnavigator.phase2.static_scheduler import extract_pairs
    from circumnavigator.phase3.reporter import print_phase2_report, save_results
    from circumnavigator.search.time_space import search
    from config import AIRLABS_API_KEY

    airports, graph, candidates = build_graph_and_candidates(args)

    # Collect every pair we might need schedule data for.
    pairs = collect_pairs(candidates, supplemental=True)
    print(f"\nCollected {len(pairs)} unique route pairs "
          f"({len(SUPPLEMENTAL_PAIRS)} supplemental).", file=sys.stderr)

    # Fetch AirLabs schedule data for all pairs (cached permanently).
    freq_map = prefetch_all_pairs(pairs, verbose=True)

    # Determine which airports to start from.
    if args.start:
        origins = [args.start]
    else:
        # Use every airport that has at least one outbound flight in the schedule data.
        # This is broader than Phase 1 origins and catches airports like AUH, FRA,
        # HKG, PEK, ATL, YVR, etc. that appear in supplemental pairs or as mid-route
        # stops but were not origin candidates in Phase 1.
        origins = sorted({dep for dep, arr in freq_map.keys() if freq_map[(dep, arr)]})

    # Build the date window.
    base = date.fromisoformat(args.start_date)
    start_dates = [base + timedelta(days=i) for i in range(args.search_days)]

    directions = (
        ["eastbound", "westbound"] if args.direction == "both" else [args.direction]
    )

    all_schedules = []
    for direction in directions:
        print(f"\nTime-space search: {direction}, {len(origins)} origins, "
              f"{len(start_dates)} dates, max {args.max_legs} legs, "
              f"budget {args.budget_hours:.0f}h ...", file=sys.stderr)

        schedules = search(
            origins=origins,
            freq_map=freq_map,
            airports=airports,
            start_dates=start_dates,
            max_legs=args.max_legs,
            direction=direction,
            require_min_distance=not args.skip_min_distance,
            budget_hours=args.budget_hours,
            max_wait_hours=args.max_wait_hours,
            top_n=args.top * 2,
            verbose=True,
        )
        all_schedules.extend(schedules)

    all_schedules.sort(key=lambda s: s.total_elapsed_seconds)
    print_phase2_report(all_schedules, top_n=args.top)
    save_results(candidates, all_schedules)


# --------------------------------------------------------------------------- #
# Six-continent world trip search
# --------------------------------------------------------------------------- #

def run_six_continents(args) -> None:
    from circumnavigator.phase2.airlabs_client import prefetch_all_pairs
    from circumnavigator.phase3.reporter import print_six_continent_report
    from circumnavigator.search.six_continents import search
    from config import COUNTRY_TO_CONTINENT

    # Load airport data (needed for continent mapping and connection times).
    from circumnavigator.data.loader import load_airports
    print("Loading airport data...", file=sys.stderr)
    airports = load_airports()

    # Collect all pairs: SIX_CONTINENT_PAIRS + any explicit --start filter.
    pairs: list[tuple[str, str]] = []
    seen_pairs: set[tuple[str, str]] = set()

    def _add(d, a):
        if (d, a) not in seen_pairs:
            seen_pairs.add((d, a))
            pairs.append((d, a))

    for d, a in SIX_CONTINENT_PAIRS:
        _add(d, a)

    print(f"Six-continent pairs: {len(pairs)} to fetch/load.", file=sys.stderr)
    freq_map = prefetch_all_pairs(pairs, verbose=True)

    # Origins: every airport in the freq_map that has outbound flights and a
    # known continent.  If --start is given, restrict to that airport.
    if args.start:
        origins = [args.start]
    else:
        origins = sorted({
            dep for dep, arr in freq_map.keys()
            if freq_map[(dep, arr)]
            and dep in airports
            and COUNTRY_TO_CONTINENT.get(airports[dep].country_code)
        })

    base = date.fromisoformat(args.start_date)
    start_dates = [base + timedelta(days=i) for i in range(args.search_days)]

    print(
        f"\nSix-continent search: {len(origins)} origins, {len(start_dates)} dates, "
        f"max {args.max_legs_6c} legs, budget {args.budget_hours_6c:.0f}h ...",
        file=sys.stderr,
    )

    schedules = search(
        origins=origins,
        freq_map=freq_map,
        airports=airports,
        start_dates=start_dates,
        max_legs=args.max_legs_6c,
        budget_hours=args.budget_hours_6c,
        max_wait_hours=args.max_wait_hours,
        top_n=args.top * 2,
        verbose=True,
    )
    print_six_continent_report(schedules, top_n=args.top)


# --------------------------------------------------------------------------- #
# Geometry-only mode (Phase 1 preview, no API)
# --------------------------------------------------------------------------- #

def run_geometry_only(args) -> None:
    from circumnavigator.phase3.reporter import print_phase1_report

    airports, graph, candidates = build_graph_and_candidates(args)
    print_phase1_report(candidates, top_n=args.top)


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #

def main() -> None:
    args = parse_args()
    if args.six_continents:
        run_six_continents(args)
    elif args.geometry_only:
        run_geometry_only(args)
    else:
        run_unified(args)


if __name__ == "__main__":
    main()
