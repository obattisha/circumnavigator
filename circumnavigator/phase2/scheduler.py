"""Phase 2: stitch legs into timed schedules using Amadeus flight offers.

All datetime arithmetic is done in UTC to avoid timezone bugs.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

from dateutil import parser as dtparser

from config import MIN_CONNECTION_MINUTES, RECORD_TIME_SECONDS
from circumnavigator.data.airports import Airport
from circumnavigator.phase1.enumerator import CandidateRoute
from circumnavigator.phase2.amadeus_client import (
    AmadeusClient,
    parse_offer,
    iso_duration_to_minutes,
)


UTC = timezone.utc


@dataclass
class ScheduledLeg:
    origin: str
    destination: str
    flight_number: str
    departure_utc: datetime
    arrival_utc: datetime
    duration_minutes: int
    connection_minutes: Optional[int] = None   # wait at origin before this leg


@dataclass
class ScheduledRoute:
    candidate: CandidateRoute
    legs: list[ScheduledLeg]
    start_date: str           # YYYY-MM-DD of first departure
    total_elapsed_seconds: float = field(init=False)
    beats_record: bool = field(init=False)

    def __post_init__(self) -> None:
        first_dep = self.legs[0].departure_utc
        last_arr = self.legs[-1].arrival_utc
        self.total_elapsed_seconds = (last_arr - first_dep).total_seconds()
        self.beats_record = self.total_elapsed_seconds < RECORD_TIME_SECONDS

    @property
    def elapsed_hms(self) -> str:
        s = int(self.total_elapsed_seconds)
        h, rem = divmod(s, 3600)
        m, sec = divmod(rem, 60)
        return f"{h}h {m:02d}m {sec:02d}s"

    @property
    def vs_record(self) -> str:
        diff = int(RECORD_TIME_SECONDS - self.total_elapsed_seconds)
        if diff >= 0:
            h, rem = divmod(diff, 3600)
            m, sec = divmod(rem, 60)
            return f"-{h}h {m:02d}m {sec:02d}s faster"
        diff = -diff
        h, rem = divmod(diff, 3600)
        m, sec = divmod(rem, 60)
        return f"+{h}h {m:02d}m {sec:02d}s slower"


def _min_connection(ap: Airport) -> int:
    cc = ap.country_code
    return MIN_CONNECTION_MINUTES.get(cc, MIN_CONNECTION_MINUTES["default"])


def _parse_local_as_utc_approx(dt_str: str, ap: Airport) -> datetime:
    """Parse Amadeus local datetime string, converting to UTC using pytz if available.

    Falls back to treating the local time as UTC offset from airport's rough offset
    if pytz is unavailable. This is an approximation; real scheduling needs exact TZ.
    """
    dt_local = dtparser.parse(dt_str)
    if dt_local.tzinfo is not None:
        # Already has offset — convert to UTC
        return dt_local.astimezone(UTC).replace(tzinfo=UTC)
    # Amadeus sandbox often returns bare local times without offset.
    # Try pytz for authoritative conversion.
    if ap.tz and ap.tz != r"\N":
        try:
            import pytz
            tz = pytz.timezone(ap.tz)
            dt_aware = tz.localize(dt_local)
            return dt_aware.astimezone(UTC).replace(tzinfo=UTC)
        except Exception:
            pass
    # Last resort: treat as UTC (may be slightly off, acceptable for ranking)
    return dt_local.replace(tzinfo=UTC)


def schedule_route(
    candidate: CandidateRoute,
    airports: dict[str, Airport],
    client: AmadeusClient,
    start_date: str,
    search_days: int = 7,
) -> list[ScheduledRoute]:
    """Find the best timed schedule(s) for a candidate route.

    Tries *search_days* departure dates for the first leg.
    Returns list of valid ScheduledRoute objects (may be empty).
    """
    iatas = candidate.airports  # e.g. [HKG, YVR, FRA, HKG]
    results: list[ScheduledRoute] = []

    # Try each start date
    base_dt = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=UTC)
    for day_offset in range(search_days):
        dep_date = (base_dt + timedelta(days=day_offset)).strftime("%Y-%m-%d")
        legs = _stitch(iatas, airports, client, dep_date)
        if legs:
            results.append(ScheduledRoute(
                candidate=candidate,
                legs=legs,
                start_date=dep_date,
            ))

    return results


def _stitch(
    iatas: list[str],
    airports: dict[str, Airport],
    client: AmadeusClient,
    first_dep_date: str,
) -> Optional[list[ScheduledLeg]]:
    """Recursively stitch legs into a valid schedule.

    Returns list of ScheduledLeg if a valid schedule is found, else None.
    """
    legs: list[ScheduledLeg] = []
    earliest_dep: Optional[datetime] = None  # earliest UTC departure for current leg

    for i in range(len(iatas) - 1):
        src, dst = iatas[i], iatas[i + 1]
        src_ap = airports[src]

        # Determine which date(s) to query
        if earliest_dep is None:
            query_date = first_dep_date
        else:
            query_date = earliest_dep.strftime("%Y-%m-%d")

        offers = client.get_nonstop_flights(src, dst, query_date)
        # Also query next day in case connection spills over midnight
        next_date = (
            datetime.strptime(query_date, "%Y-%m-%d") + timedelta(days=1)
        ).strftime("%Y-%m-%d")
        offers += client.get_nonstop_flights(src, dst, next_date)

        if not offers:
            return None

        best_leg: Optional[ScheduledLeg] = None
        for offer in offers:
            parsed = parse_offer(offer)
            if not parsed:
                continue
            dep_utc = _parse_local_as_utc_approx(parsed["departure_local"], src_ap)
            arr_utc = _parse_local_as_utc_approx(
                parsed["arrival_local"], airports[dst]
            )
            dur_min = iso_duration_to_minutes(parsed["duration_iso"])
            if dur_min == 0:
                dur_min = int((arr_utc - dep_utc).total_seconds() / 60)

            if earliest_dep is not None and dep_utc < earliest_dep:
                continue  # too early — doesn't allow minimum connection

            # Prefer earliest departure that still allows connection
            if best_leg is None or dep_utc < best_leg.departure_utc:
                min_conn = _min_connection(src_ap)
                conn = (
                    int((dep_utc - legs[-1].arrival_utc).total_seconds() / 60)
                    if legs
                    else None
                )
                if conn is not None and conn < min_conn:
                    continue
                best_leg = ScheduledLeg(
                    origin=src,
                    destination=dst,
                    flight_number=parsed["flight_number"],
                    departure_utc=dep_utc,
                    arrival_utc=arr_utc,
                    duration_minutes=dur_min,
                    connection_minutes=conn,
                )

        if best_leg is None:
            return None

        legs.append(best_leg)
        # Next leg must depart after arrival + min connection at destination
        min_conn_next = _min_connection(airports[dst])
        earliest_dep = best_leg.arrival_utc + timedelta(minutes=min_conn_next)

    return legs if len(legs) == len(iatas) - 1 else None


def schedule_top_candidates(
    candidates: list[CandidateRoute],
    airports: dict[str, Airport],
    client: AmadeusClient,
    start_date: str,
    max_candidates: int = 100,
    search_days: int = 7,
    verbose: bool = True,
) -> list[ScheduledRoute]:
    """Schedule up to *max_candidates* candidates and return all valid schedules."""
    all_schedules: list[ScheduledRoute] = []
    subset = candidates[:max_candidates]

    for i, candidate in enumerate(subset):
        if verbose:
            print(
                f"[{i+1}/{len(subset)}] Scheduling: {' → '.join(candidate.airports)}",
                file=sys.stderr,
            )
        try:
            schedules = schedule_route(
                candidate, airports, client, start_date, search_days
            )
            all_schedules.extend(schedules)
        except Exception as e:
            if verbose:
                print(f"  ERROR: {e}", file=sys.stderr)

    all_schedules.sort(key=lambda s: s.total_elapsed_seconds)
    return all_schedules
