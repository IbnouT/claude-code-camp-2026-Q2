"""Current bounded map windows and independently versioned Live partitions."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from typing import Any, cast

from ..redaction import sanitize_evidence
from .base import (
    ResourceBase,
    ResourceNotFoundError,
    cursor_int,
    decode_payload,
    first_text,
    json_object,
)
from .bounds import bounded_json_object, content_identity
from .contracts import (
    Completeness,
    LivePartition,
    LivePartitionResponse,
    MapEdge,
    MapNode,
    MapPrefixResponse,
)
from .cursor import CursorCoordinates, decode_cursor, encode_cursor

MAX_MAP_EVENTS = 2_000
MAX_MAP_NODES = 200
MAX_MAP_EDGES = 400
MAX_PATH_ITEMS = 100
MAX_LIVE_VALUES_BYTES = 96 * 1024


class LiveResources(ResourceBase):
    """Read current map state and content-versioned Live partitions."""

    def map_prefix(
        self,
        session_id: str,
        *,
        cursor: str | None,
    ) -> MapPrefixResponse:
        resource_id = f"session:{session_id}:map"
        before_sequence: int | None = None
        if cursor is not None:
            before_sequence = cursor_int(
                decode_cursor(cursor, resource=resource_id).primary
            )
        clauses = [
            "p.session_id = ?",
            """p.evidence_kind IN (
                'gateway:observation',
                'gateway:position',
                'gateway:tool_result'
            )""",
        ]
        arguments: list[object] = [session_id]
        if before_sequence is not None:
            clauses.append("CAST(json_extract(p.payload, '$.sequence') AS INTEGER) < ?")
            arguments.append(before_sequence)
        arguments.append(MAX_MAP_EVENTS + 1)
        with closing(self._connect()) as database:
            rows_desc = database.execute(
                f"""
                SELECT e.id, e.source_ref, p.payload
                FROM evidence_payloads AS p
                JOIN entities AS e ON e.id = p.entity_id
                WHERE {" AND ".join(clauses)}
                ORDER BY CAST(json_extract(p.payload, '$.sequence') AS INTEGER) DESC,
                         e.id DESC
                LIMIT ?
                """,
                arguments,
            ).fetchall()
        visible_desc: list[sqlite3.Row] = []
        visible_room_ids: set[str] = set()
        for row in rows_desc[:MAX_MAP_EVENTS]:
            event = decode_payload(row["payload"])
            payload = event.get("payload")
            room_id = (
                None
                if not isinstance(payload, dict)
                else first_text(payload, ("place_id", "room_id", "id"))
            )
            if (
                room_id is not None
                and room_id not in visible_room_ids
                and len(visible_room_ids) >= MAX_MAP_NODES
            ):
                break
            visible_desc.append(row)
            if room_id is not None:
                visible_room_ids.add(room_id)
        rows = tuple(reversed(visible_desc))
        nodes: dict[str, MapNode] = {}
        edges: list[MapEdge] = []
        path: list[str] = []
        for row in rows:
            event = decode_payload(row["payload"])
            sequence = _json_int(event.get("sequence"))
            payload = event.get("payload")
            if not isinstance(payload, dict):
                continue
            room_id = first_text(payload, ("place_id", "room_id", "id"))
            if room_id is None:
                continue
            title = _bounded_string(
                first_text(payload, ("title", "name")) or room_id,
                maximum=256,
            )
            nodes.pop(room_id, None)
            nodes[room_id] = MapNode(
                id=room_id,
                title=title,
                x=_optional_number(payload.get("x")),
                y=_optional_number(payload.get("y")),
                exits=_string_tuple(payload.get("exits"), maximum=32),
                last_sequence=sequence,
                source_ref=str(row["source_ref"]),
            )
            if not path or path[-1] != room_id:
                if path:
                    edges.append(
                        MapEdge(
                            source=path[-1],
                            target=room_id,
                            direction=(
                                first_text(payload, ("direction", "via")) or "unknown"
                            ),
                            sequence=sequence,
                        )
                    )
                path.append(room_id)
        bounded_nodes = tuple(nodes.values())[-MAX_MAP_NODES:]
        bounded_node_ids = {node.id for node in bounded_nodes}
        bounded_edges = tuple(
            edge
            for edge in edges
            if edge.source in bounded_node_ids and edge.target in bounded_node_ids
        )[-MAX_MAP_EDGES:]
        bounded_path = tuple(path[-MAX_PATH_ITEMS:])
        has_more = len(visible_desc) < len(rows_desc)
        gaps = (
            ("map_prefix_truncated",)
            if has_more or len(nodes) > MAX_MAP_NODES or len(edges) > MAX_MAP_EDGES
            else ()
        )
        continuation = (
            encode_cursor(
                CursorCoordinates(
                    resource=resource_id,
                    primary=str(
                        _json_int(
                            decode_payload(visible_desc[-1]["payload"]).get("sequence")
                        )
                    ),
                    secondary=str(visible_desc[-1]["id"]),
                )
            )
            if has_more and visible_desc
            else None
        )
        return MapPrefixResponse(
            **self._metadata(
                session_id,
                "map",
                gaps=gaps,
                refs=("gateway.db structured observations",),
            ),
            current_room_id=bounded_path[-1] if bounded_path else None,
            nodes=bounded_nodes,
            edges=bounded_edges,
            recent_path=bounded_path,
            continuation_cursor=continuation,
        )

    def live_partition(
        self,
        session_id: str,
        partition: LivePartition,
    ) -> LivePartitionResponse:
        repository = cast(Any, self)
        summary = repository.session_summary(session_id)
        local_gaps: list[str] = []
        ids: tuple[str, ...]
        refs: tuple[str, ...]
        if partition == "identity-lifecycle":
            ids = (session_id,)
            values: dict[str, Any] = {
                "character": summary.character,
                "player_id": summary.player_id,
                "state": summary.state,
                "latest_goal": summary.latest_goal,
                "updated_at": summary.updated_at,
                "lifecycle": [
                    item.model_dump(mode="json") for item in summary.lifecycle
                ],
            }
            refs = ("registry.db sessions", "registry.db lifecycle")
        elif partition in {"world-map", "position-path"}:
            map_value = self.map_prefix(session_id, cursor=None)
            local_gaps.extend(map_value.capture_gaps)
            if partition == "world-map":
                ids = tuple(node.id for node in map_value.nodes)
                values = {
                    "current_room_id": map_value.current_room_id,
                    "nodes": [node.model_dump(mode="json") for node in map_value.nodes],
                    "edges": [edge.model_dump(mode="json") for edge in map_value.edges],
                }
                refs = ("gateway.db structured observations",)
            else:
                ids = tuple(map_value.recent_path)
                values = {
                    "current_room_id": map_value.current_room_id,
                    "recent_path": list(map_value.recent_path),
                }
                refs = ("gateway.db position observations",)
        elif partition == "economics":
            cost = repository.cost_range(
                session_id,
                scope_id=None,
                cursor=None,
                limit=100,
            )
            ids = tuple(item.record_id for item in cost.contributors)
            values = {
                "tokens": cost.total_tokens,
                "cost_usd": cost.total_cost_usd,
                "duration_ms": cost.total_duration_ms,
                "contributors": [
                    item.model_dump(mode="json") for item in cost.contributors
                ],
            }
            refs = ("agent.jsonl usage",)
        else:
            rows = self._latest_evidence(
                session_id,
                _partition_kinds(partition),
                limit=100,
            )
            ids = tuple(str(row["id"]) for row in rows)
            values = {
                "records": [
                    {
                        "id": str(row["id"]),
                        "kind": str(row["evidence_kind"]),
                        "occurred_at": str(row["occurred_at"]),
                        "title": str(row["title"]),
                        "fields": decode_payload(row["payload"]),
                    }
                    for row in rows
                ]
            }
            refs = ("observatory index evidence",)
        sanitized = json_object(sanitize_evidence(values))
        bounded, truncated = bounded_json_object(
            sanitized,
            max_bytes=MAX_LIVE_VALUES_BYTES,
        )
        if truncated:
            local_gaps.append("live_values_truncated")
        checkpoint = self.index.checkpoint(session_id)
        if checkpoint is None:
            raise ResourceNotFoundError(session_id)
        gaps = tuple(
            dict.fromkeys(
                (*_partition_gaps(partition, checkpoint.capture_gaps), *local_gaps)
            )
        )[:32]
        version, source_cursor = content_identity(
            "obl1",
            {
                "session_id": session_id,
                "partition": partition,
                "stable_node_ids": ids,
                "values": bounded,
                "capture_gaps": gaps,
            },
        )
        completeness: Completeness = "partial" if gaps else "complete"
        return LivePartitionResponse(
            resource_id=f"session:{session_id}:live:{partition}",
            resource_version=version,
            source_cursor=source_cursor,
            completeness=completeness,
            capture_gaps=gaps,
            source_refs=refs,
            session_id=session_id,
            partition=partition,
            stable_node_ids=ids,
            values=bounded,
        )

    def _latest_evidence(
        self,
        session_id: str,
        evidence_kinds: tuple[str, ...],
        *,
        limit: int,
    ) -> tuple[sqlite3.Row, ...]:
        placeholders = ",".join("?" for _ in evidence_kinds)
        with closing(self._connect()) as database:
            rows = database.execute(
                f"""
                SELECT e.id, e.occurred_at, e.title,
                       p.evidence_kind, p.payload
                FROM evidence_payloads AS p
                JOIN entities AS e ON e.id = p.entity_id
                WHERE p.session_id = ?
                  AND p.evidence_kind IN ({placeholders})
                ORDER BY e.ordinal DESC, e.id DESC
                LIMIT ?
                """,
                (session_id, *evidence_kinds, limit),
            ).fetchall()
        return tuple(reversed(rows))


def _partition_kinds(partition: LivePartition) -> tuple[str, ...]:
    if partition == "thought-activity":
        return (
            "agent:reasoning",
            "agent:thinking",
            "agent:plan",
            "agent:response",
            "agent:tool_call",
            "agent:tool_result",
        )
    if partition == "vitals-combat":
        return ("gateway:observation", "gateway:player_state", "gateway:combat")
    if partition == "controls":
        return ("agent:operator_control", "operator:guide", "operator:revise")
    return (
        "gateway:capability_gap",
        "gateway:unparsed",
        "gateway:observer_probe",
        "agent:error",
    )


def _partition_gaps(
    partition: LivePartition,
    gaps: tuple[str, ...],
) -> tuple[str, ...]:
    prefixes: tuple[str, ...]
    if partition in {"world-map", "position-path", "vitals-combat"}:
        prefixes = ("gateway_",)
    elif partition in {"thought-activity", "economics"}:
        prefixes = ("agent_",)
    elif partition == "controls":
        prefixes = ("agent_", "operator_")
    elif partition == "identity-lifecycle":
        prefixes = ("lifecycle_", "registry_")
    else:
        prefixes = ("agent_", "gateway_", "operator_")
    return tuple(gap for gap in gaps if gap.startswith(prefixes))


def _json_int(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _bounded_string(value: str, *, maximum: int) -> str:
    return value.encode("utf-8")[:maximum].decode("utf-8", errors="ignore")


def _string_tuple(value: object, *, maximum: int) -> tuple[str, ...]:
    if isinstance(value, str):
        return (_bounded_string(value, maximum=128),)[:maximum]
    if not isinstance(value, list | tuple):
        return ()
    return tuple(_bounded_string(str(item), maximum=128) for item in value[:maximum])


def _optional_number(value: object) -> float | None:
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value)
    return None
