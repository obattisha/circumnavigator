"""Phase 1 graph construction entry point."""

from __future__ import annotations

from circumnavigator.data.airports import Airport
from circumnavigator.data.loader import load_airports, load_routes
from circumnavigator.data.routes import build_graph, AdjList


def load_phase1_graph() -> tuple[dict[str, Airport], AdjList]:
    """Load airports + routes and build the long-haul graph."""
    airports = load_airports()
    raw_routes = load_routes(airports)
    graph = build_graph(airports, raw_routes)
    return airports, graph
