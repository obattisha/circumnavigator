"""Build the long-haul nonstop route graph from OpenFlights data."""

from __future__ import annotations

from collections import defaultdict

from config import (
    MIN_ROUTE_DISTANCE_KM,
    MIN_OUTBOUND_EDGES,
    WIDEBODY_EQUIPMENT,
)
from circumnavigator.data.airports import Airport
from circumnavigator.geometry.distance import haversine


# Edge: (dst_iata, distance_km)
AdjList = dict[str, list[tuple[str, float]]]


def _equipment_ok(equip_field: str) -> bool:
    """Return True if the equipment is widebody/long-haul or unspecified."""
    if not equip_field.strip():
        return True   # conservative include
    codes = equip_field.strip().split()
    return any(c in WIDEBODY_EQUIPMENT for c in codes)


def build_graph(
    airports: dict[str, Airport],
    raw_routes: list[tuple[str, str, str]],
    min_distance_km: float = MIN_ROUTE_DISTANCE_KM,
    min_outbound: int = MIN_OUTBOUND_EDGES,
) -> AdjList:
    """Build adjacency list of long-haul nonstop routes.

    Filters:
    - Route distance ≥ min_distance_km
    - Widebody equipment OR empty equipment field
    - Both endpoints have valid coords in *airports*
    - Each airport must have ≥ min_outbound qualifying outbound edges
    """
    # First pass: compute qualifying edges
    candidate: AdjList = defaultdict(list)
    for src, dst, equip in raw_routes:
        if not _equipment_ok(equip):
            continue
        a1, a2 = airports[src], airports[dst]
        dist = haversine(a1.lat, a1.lon, a2.lat, a2.lon)
        if dist < min_distance_km:
            continue
        candidate[src].append((dst, dist))

    # Second pass: keep only airports with enough outbound edges
    qualified: set[str] = {
        ap for ap, edges in candidate.items() if len(edges) >= min_outbound
    }
    graph: AdjList = {}
    for src in qualified:
        graph[src] = [(dst, d) for dst, d in candidate[src] if dst in qualified]
        # Re-check after filtering destinations (some may have been pruned)
    # Iterative pruning until stable
    changed = True
    while changed:
        changed = False
        to_remove = []
        for src, edges in graph.items():
            valid = [(dst, d) for dst, d in edges if dst in graph]
            if len(valid) < min_outbound:
                to_remove.append(src)
                changed = True
            else:
                graph[src] = valid
        for src in to_remove:
            del graph[src]

    return graph
