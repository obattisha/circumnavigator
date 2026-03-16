"""DFS route enumerator for circumnavigation candidates.

Searches for routes that:
  - Start and end at the same airport
  - Cover ≥ 360° of longitude in a consistent direction
  - Use only nonstop legs present in the long-haul graph
  - Visit no airport twice (except origin at the end)
  - Have at most MAX_LEGS legs

Longitude direction convention:
  - eastbound: each leg has a POSITIVE raw longitude delta
  - westbound: each leg has a NEGATIVE raw longitude delta
  - longitude_delta() returns the true (-180, 180] signed change for a direct
    flight, so we never accidentally treat a 3°-westward hop as a 357°-east leg.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from config import MIN_LONGITUDE_COVERAGE, MAX_LEGS, GUINNESS_MIN_DISTANCE_KM, MIN_CONNECTION_MINUTES
from circumnavigator.data.airports import Airport
from circumnavigator.data.routes import AdjList
from circumnavigator.geometry.distance import haversine
from circumnavigator.geometry.longitude import longitude_delta

# Average connection time used when airport country is unknown in Phase 1
_AVG_CONNECTION_MIN = 75


@dataclass
class CandidateRoute:
    airports: list[str]              # IATA codes; first == last
    distances_km: list[float]        # per-leg great-circle distances
    total_km: float
    lon_coverage: float              # absolute degrees (≥ 360 for valid)
    direction: str                   # "eastbound" | "westbound"
    # airports_ref is set by enumerate_routes so we can look up country codes
    airports_ref: dict = field(default_factory=dict, repr=False, compare=False)
    estimated_flight_hours: float = field(init=False)
    estimated_elapsed_hours: float = field(init=False)  # flight + min connections

    def __post_init__(self) -> None:
        self.estimated_flight_hours = self.total_km / 900.0
        # Sum minimum connection times at each intermediate stop
        conn_min = 0
        for iata in self.airports[1:-1]:   # intermediate stops only
            ap = self.airports_ref.get(iata)
            cc = ap.country_code if ap else "XX"
            conn_min += MIN_CONNECTION_MINUTES.get(cc, MIN_CONNECTION_MINUTES["default"])
        self.estimated_elapsed_hours = self.estimated_flight_hours + conn_min / 60.0

    @property
    def num_legs(self) -> int:
        return len(self.airports) - 1

    def __str__(self) -> str:
        route = " → ".join(self.airports)
        return (
            f"{route}  |  {self.num_legs} legs  |  {self.total_km:,.0f} km  "
            f"|  {self.lon_coverage:.1f}° lon  |  ~{self.estimated_flight_hours:.1f}h flight"
        )


def enumerate_routes(
    start: str,
    airports: dict[str, Airport],
    graph: AdjList,
    direction: str = "eastbound",
    max_legs: int = MAX_LEGS,
    require_min_distance: bool = True,
) -> list[CandidateRoute]:
    """Return all qualifying circumnavigation routes starting from *start*.

    Args:
        start: IATA code of origin airport.
        airports: All airports dict.
        graph: Long-haul adjacency list.
        direction: "eastbound" or "westbound".
        max_legs: Maximum number of legs (DFS depth).
        require_min_distance: If True (default), enforce GUINNESS_MIN_DISTANCE_KM.
            Pass False only for exploratory searches where distance validity
            is not required.
    """
    if start not in graph:
        return []

    east = direction == "eastbound"
    results: list[CandidateRoute] = []
    origin = airports[start]

    # State: (current_iata, visited_set, path_iata, path_dists, lon_sum, total_km)
    # lon_sum: running signed sum (positive→east accumulated, negative→west accumulated)
    stack: list[tuple[str, frozenset[str], list[str], list[float], float, float]] = [
        (start, frozenset({start}), [start], [], 0.0, 0.0)
    ]

    while stack:
        cur, visited, path, dists, lon_sum, total_km = stack.pop()
        cur_ap = airports[cur]
        depth = len(path) - 1   # number of legs so far

        # Can we close the loop back to origin?
        if depth >= 2:
            close_edges = [(dst, d) for dst, d in graph.get(cur, []) if dst == start]
            if close_edges:
                _, close_dist = close_edges[0]
                final_delta = longitude_delta(cur_ap.lon, origin.lon)
                # Closing leg must also go in the right direction
                closing_ok = (east and final_delta > 0) or (not east and final_delta < 0)
                if closing_ok:
                    final_lon_sum = lon_sum + final_delta
                    final_lon_cov = abs(final_lon_sum)
                    final_km = total_km + close_dist

                    valid_lon = final_lon_cov >= MIN_LONGITUDE_COVERAGE
                    valid_dist = (not require_min_distance) or (final_km >= GUINNESS_MIN_DISTANCE_KM)

                    if valid_lon and valid_dist:
                        results.append(CandidateRoute(
                            airports=path + [start],
                            distances_km=dists + [close_dist],
                            total_km=final_km,
                            lon_coverage=final_lon_cov,
                            direction=direction,
                            airports_ref=airports,
                        ))

        # Depth limit
        if depth >= max_legs - 1:
            continue

        # Expand neighbours
        for dst, leg_dist in graph.get(cur, []):
            if dst in visited:
                continue
            dst_ap = airports[dst]
            delta = longitude_delta(cur_ap.lon, dst_ap.lon)

            # Longitude monotonicity: leg must advance in the chosen direction
            if east and delta <= 0:
                continue
            if not east and delta >= 0:
                continue

            new_lon_sum = lon_sum + delta
            new_lon_cov = abs(new_lon_sum)
            new_total_km = total_km + leg_dist

            # Optimistic upper-bound check:
            # With at most `remaining` more intermediate legs each covering max
            # 180° + 1 return leg of max 180°, can we still reach 360°?
            remaining = max_legs - (depth + 1)   # legs left after this one
            if new_lon_cov < MIN_LONGITUDE_COVERAGE:
                # +1 for the eventual return leg
                max_achievable = new_lon_cov + (remaining + 1) * 180.0
                if max_achievable < MIN_LONGITUDE_COVERAGE:
                    continue

            stack.append((
                dst,
                visited | {dst},
                path + [dst],
                dists + [leg_dist],
                new_lon_sum,
                new_total_km,
            ))

    return results


def enumerate_all(
    airports: dict[str, Airport],
    graph: AdjList,
    direction: str = "eastbound",
    max_legs: int = MAX_LEGS,
    require_min_distance: bool = True,
    start_filter: Optional[str] = None,
) -> list[CandidateRoute]:
    """Enumerate from all airports (or just *start_filter* if given)."""
    starts = [start_filter] if start_filter else list(graph.keys())
    all_routes: list[CandidateRoute] = []
    seen: set[frozenset[str]] = set()   # deduplicate by airport set

    for start in starts:
        routes = enumerate_routes(
            start, airports, graph, direction, max_legs, require_min_distance
        )
        for r in routes:
            key = frozenset(r.airports)
            if key not in seen:
                seen.add(key)
                all_routes.append(r)

    all_routes.sort(key=lambda r: r.estimated_flight_hours)
    return all_routes
