"""Phase 3: formatted output and results persistence."""

from __future__ import annotations

import json
import os
import sys

from config import (
    RECORD_TIME_SECONDS, SIX_CONTINENT_RECORD_SECONDS,
    ANTIPODAL_RECORD_SECONDS, RESULTS_FILE, OUTPUT_DIR,
)
from circumnavigator.phase1.enumerator import CandidateRoute
from circumnavigator.phase2.static_scheduler import ScheduledRoute

PHASE1_RESULTS_FILE = os.path.join(OUTPUT_DIR, "phase1_candidates.json")
RECORD_H = RECORD_TIME_SECONDS / 3600


# --------------------------------------------------------------------------- #
# Phase 1 report
# --------------------------------------------------------------------------- #

def print_phase1_report(
    candidates: list[CandidateRoute],
    top_n: int = 50,
    airports_dict: dict | None = None,
) -> None:
    print(f"\n{'='*90}")
    print(f"  PHASE 1 — Static Route Candidates  (top {top_n} of {len(candidates)} found)")
    print(f"  Record to beat: {RECORD_H:.2f}h  (44h 33m 39s)  —  HKG → YVR → FRA → HKG")
    print(f"  Elapsed = flight time (@ 900 km/h) + minimum connection time per stop")
    print(f"{'='*90}\n")

    header = (
        f"{'#':>4}  {'Route':<42}  {'Legs':>4}  {'Distance':>10}  "
        f"{'~Flight':>8}  {'Min conns':>9}  {'~Elapsed':>9}"
    )
    print(header)
    print("-" * len(header))

    for i, r in enumerate(candidates[:top_n], 1):
        route_str = " → ".join(r.airports)
        conn_h = r.estimated_elapsed_hours - r.estimated_flight_hours
        flag = "  *** BEATS RECORD ***" if r.estimated_elapsed_hours < RECORD_H else ""
        print(
            f"{i:>4}  {route_str:<42}  {r.num_legs:>4}  "
            f"{r.total_km:>9,.0f}km  "
            f"{r.estimated_flight_hours:>7.1f}h  "
            f"{conn_h:>+8.1f}h  "
            f"{r.estimated_elapsed_hours:>8.1f}h"
            f"{flag}"
        )

    print()
    save_phase1_results(candidates)


def save_phase1_results(candidates: list[CandidateRoute]) -> None:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    data = [
        {
            "airports": r.airports,
            "distances_km": [round(d, 1) for d in r.distances_km],
            "total_km": round(r.total_km, 1),
            "lon_coverage": round(r.lon_coverage, 2),
            "direction": r.direction,
            "num_legs": r.num_legs,
            "estimated_flight_hours": round(r.estimated_flight_hours, 2),
            "estimated_elapsed_hours": round(r.estimated_elapsed_hours, 2),
            "connection_hours_added": round(
                r.estimated_elapsed_hours - r.estimated_flight_hours, 2
            ),
        }
        for r in candidates
    ]
    with open(PHASE1_RESULTS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    print(f"Phase 1 results saved → {PHASE1_RESULTS_FILE}  ({len(candidates)} routes)", file=sys.stderr)


# --------------------------------------------------------------------------- #
# Phase 2 report
# --------------------------------------------------------------------------- #

def print_phase2_report(
    schedules: list[ScheduledRoute],
    airports_dict: dict | None = None,
    top_n: int = 20,
) -> None:
    record_h = RECORD_TIME_SECONDS / 3600
    print(f"\n{'='*80}")
    print(f"  PHASE 2 — Scheduled Routes  (top {top_n} of {len(schedules)} valid)")
    print(f"  Record to beat: {record_h:.2f}h  (44h 33m 39s)  HKG→YVR→FRA→HKG")
    print(f"{'='*80}\n")

    if not schedules:
        print("  No valid schedules found.\n")
        return

    for i, s in enumerate(schedules[:top_n], 1):
        flag = "  *** BEATS RECORD ***" if s.beats_record else ""
        route_str = " → ".join(s.candidate.airports)
        print(f"\n  [{i}] {route_str}{flag}")
        print(f"       Elapsed:  {s.elapsed_hms}  ({s.vs_record})")
        print(f"       Start:    {s.start_date}  "
              f"({s.legs[0].departure_utc.strftime('%a')})")
        print(f"       Distance: {s.candidate.total_km:,.0f} km  "
              f"| Lon: {s.candidate.lon_coverage:.1f}°")
        print()
        for leg in s.legs:
            conn_str = ""
            if leg.connection_minutes is not None:
                conn_str = f"  (connection: {leg.connection_minutes}m)"
            print(
                f"       {(leg.flight_number or '?'):>7}  "
                f"{leg.origin} → {leg.destination}  "
                f"dep {leg.departure_utc.strftime('%Y-%m-%d %H:%MZ')}  "
                f"arr {leg.arrival_utc.strftime('%Y-%m-%d %H:%MZ')}  "
                f"[{leg.duration_minutes}m]{conn_str}"
            )
    print()


# --------------------------------------------------------------------------- #
# Six-continent report
# --------------------------------------------------------------------------- #

def print_six_continent_report(
    schedules: list[ScheduledRoute],
    top_n: int = 20,
) -> None:
    record_s = SIX_CONTINENT_RECORD_SECONDS
    record_h = record_s / 3600
    print(f"\n{'='*80}")
    print(f"  SIX-CONTINENT WORLD TRIP  (top {top_n} of {len(schedules)} valid)")
    print(f"  Record to beat: {record_h:.2f}h  (56h 56m 00s)")
    print(f"  Route: SYD → SCL → PTY → MAD → ALG → DXB → SYD")
    print(f"{'='*80}\n")

    if not schedules:
        print("  No valid schedules found.\n")
        return

    for i, s in enumerate(schedules[:top_n], 1):
        diff = int(record_s - s.total_elapsed_seconds)
        sign = "-" if diff >= 0 else "+"
        abs_diff = abs(diff)
        dh, dr = divmod(abs_diff, 3600)
        dm, ds = divmod(dr, 60)
        label = "faster" if sign == "-" else "slower"
        vs_str = f"({sign}{dh}h {dm:02d}m {ds:02d}s {label})"
        flag = "  *** BEATS RECORD ***" if diff >= 0 else ""

        route_str = " → ".join(s.candidate.airports)
        print(f"\n  [{i}] {route_str}{flag}")
        print(f"       Elapsed:  {s.elapsed_hms}  {vs_str}")
        print(f"       Start:    {s.start_date}  "
              f"({s.legs[0].departure_utc.strftime('%a')})")
        print(f"       Distance: {s.candidate.total_km:,.0f} km")
        print()
        for leg in s.legs:
            conn_str = ""
            if leg.connection_minutes is not None:
                conn_str = f"  (connection: {leg.connection_minutes}m)"
            print(
                f"       {(leg.flight_number or '?'):>7}  "
                f"{leg.origin} → {leg.destination}  "
                f"dep {leg.departure_utc.strftime('%Y-%m-%d %H:%MZ')}  "
                f"arr {leg.arrival_utc.strftime('%Y-%m-%d %H:%MZ')}  "
                f"[{leg.duration_minutes}m]{conn_str}"
            )
    print()


# --------------------------------------------------------------------------- #
# Antipodal circumnavigation report
# --------------------------------------------------------------------------- #

def print_antipodal_report(
    schedules: list[ScheduledRoute],
    antipodal_partners: dict,   # iata -> frozenset[iata]
    airports_dict: dict | None = None,
    top_n: int = 20,
) -> None:
    record_s = ANTIPODAL_RECORD_SECONDS
    record_h = record_s / 3600
    print(f"\n{'='*80}")
    print(f"  ANTIPODAL CIRCUMNAVIGATION  (top {top_n} of {len(schedules)} valid)")
    print(f"  Record to beat: {record_h:.4f}h  (52h 34m 00s)")
    print(f"  Holder: Andrew Fisher  —  PVG → AKL → EZE → AMS → PVG")
    print(f"  Rules: land+change-planes at a near-antipodal pair; cross equator")
    print(f"{'='*80}\n")

    if not schedules:
        print("  No valid schedules found.\n")
        return

    for i, s in enumerate(schedules[:top_n], 1):
        diff = int(record_s - s.total_elapsed_seconds)
        sign = "-" if diff >= 0 else "+"
        abs_diff = abs(diff)
        dh, dr = divmod(abs_diff, 3600)
        dm, ds = divmod(dr, 60)
        label = "faster" if sign == "-" else "slower"
        vs_str = f"({sign}{dh}h {dm:02d}m {ds:02d}s {label})"
        beats = diff >= 0
        flag = "  *** BEATS RECORD ***" if beats else ""

        route_str = " → ".join(s.candidate.airports)
        print(f"\n  [{i}] {route_str}{flag}")
        print(f"       Elapsed:  {s.elapsed_hms}  {vs_str}")
        print(f"       Start:    {s.start_date}  "
              f"({s.legs[0].departure_utc.strftime('%a')})")
        print(f"       Distance: {s.candidate.total_km:,.0f} km")

        # Identify the antipodal pair in this route
        visited = [leg.origin for leg in s.legs] + [s.legs[-1].destination]
        found_pair = None
        for j, a in enumerate(visited):
            for b in visited[j + 1:]:
                if b in antipodal_partners.get(a, frozenset()):
                    found_pair = (a, b)
                    break
            if found_pair:
                break
        if found_pair:
            print(f"       Antipodal pair: {found_pair[0]} ↔ {found_pair[1]}")

        print()
        for leg in s.legs:
            conn_str = ""
            if leg.connection_minutes is not None:
                conn_str = f"  (connection: {leg.connection_minutes}m)"
            print(
                f"       {(leg.flight_number or '?'):>7}  "
                f"{leg.origin} → {leg.destination}  "
                f"dep {leg.departure_utc.strftime('%Y-%m-%d %H:%MZ')}  "
                f"arr {leg.arrival_utc.strftime('%Y-%m-%d %H:%MZ')}  "
                f"[{leg.duration_minutes}m]{conn_str}"
            )
    print()


# --------------------------------------------------------------------------- #
# JSON persistence
# --------------------------------------------------------------------------- #

def save_results(
    candidates: list[CandidateRoute],
    schedules: list[ScheduledRoute],
) -> None:
    os.makedirs(os.path.dirname(RESULTS_FILE), exist_ok=True)
    data = {
        "phase1_candidates": [
            {
                "airports": r.airports,
                "distances_km": [round(d, 1) for d in r.distances_km],
                "total_km": round(r.total_km, 1),
                "lon_coverage": round(r.lon_coverage, 2),
                "direction": r.direction,
                "num_legs": r.num_legs,
                "estimated_flight_hours": round(r.estimated_flight_hours, 2),
                "estimated_elapsed_hours": round(r.estimated_elapsed_hours, 2),
            }
            for r in candidates
        ],
        "phase2_schedules": [
            {
                "airports": s.candidate.airports,
                "start_date": s.start_date,
                "total_elapsed_seconds": s.total_elapsed_seconds,
                "elapsed_hms": s.elapsed_hms,
                "beats_record": s.beats_record,
                "legs": [
                    {
                        "origin": leg.origin,
                        "destination": leg.destination,
                        "flight_number": leg.flight_number,
                        "departure_utc": leg.departure_utc.isoformat(),
                        "arrival_utc": leg.arrival_utc.isoformat(),
                        "duration_minutes": leg.duration_minutes,
                        "connection_minutes": leg.connection_minutes,
                    }
                    for leg in s.legs
                ],
            }
            for s in schedules
        ],
    }
    with open(RESULTS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    print(f"\nResults saved → {RESULTS_FILE}", file=sys.stderr)
