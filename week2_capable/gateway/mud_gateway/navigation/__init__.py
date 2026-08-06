"""Purposeful movement over the agent's own learned map.

The navigation capability: a world graph read from the knowledge store, a
route planner over it, and bounded routines (sweep, travel) that execute
steps through the ordinary session command path so every step remains
ordinary wire evidence.
"""

from .graph import Room, WorldGraph
from .route import RoutePlan, nearest_frontier, plan_route
from .executor import NavigationExecutor, RoutineReport

__all__ = [
    "NavigationExecutor",
    "Room",
    "RoutePlan",
    "RoutineReport",
    "WorldGraph",
    "nearest_frontier",
    "plan_route",
]
