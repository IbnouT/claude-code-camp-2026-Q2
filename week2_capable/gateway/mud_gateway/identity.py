"""Room identity: which observed places are the same room.

A place is recorded once per session, so the same room becomes a new
place in every run and the map never joins across sessions. This module
decides which places are one room, from what was observed by playing.

Difference is decided first and once: places whose keys differ are
different, and difference travels along the directions both walked.
Agreement then merges whole neighbourhoods, never one place at a time,
so the answer follows the evidence rather than the order of the walk.

Two limits are known and measured, both waiting on work elsewhere:

- A room's stored description sometimes carries what was happening in it
  rather than the room itself, so the same room can look like two. That
  costs joins and cannot be repaired here: the description fact has to
  become the static room text upstream.
- Difference is proven between observed places, not between the rooms
  they have been merged into, so a merge one hop above two rooms the
  resolver itself holds apart is possible. It does not occur in anything
  recorded so far, and closing it properly needs recorded room numbers
  to measure against.
"""

from __future__ import annotations

import hashlib
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

from .navigation.graph import canonical_direction

# Confidence in a binding, by the evidence that supported it.
CORROBORATED = "confirmed"
UNCONTESTED = "tracked"


@dataclass(frozen=True)
class Place:
    """One observed place, as the identity rule sees it."""

    place_id: str
    session: str
    title: str
    exits: tuple[str, ...]
    description_digest: str
    links: Mapping[str, str] = field(default_factory=dict)

    @property
    def key(self) -> tuple[str, tuple[str, ...], str]:
        """The candidate key. Equal keys are candidates, never a decision."""
        return (self.title.casefold(), self.exits, self.description_digest)


@dataclass(frozen=True)
class Binding:
    """One place bound to a room, with the evidence class that bound it."""

    place_id: str
    room_id: str
    confidence: str


def _digest(value: Any) -> str:
    text = value if isinstance(value, str) else repr(value)
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]


def _session_of(place_id: str) -> str:
    parts = place_id.split(":")
    return parts[1] if len(parts) > 2 else ""


def places_from_facts(assertions: Iterable[Any]) -> list[Place]:
    """Build places from current learned facts, ignoring anything else."""
    titles: dict[str, str] = {}
    exits: dict[str, tuple[str, ...]] = {}
    descriptions: dict[str, str] = {}
    links: dict[str, dict[str, str]] = defaultdict(dict)
    for assertion in assertions:
        subject = assertion.subject
        if not subject.startswith("place:"):
            continue
        predicate = assertion.predicate
        value = assertion.value
        if predicate == "title" and isinstance(value, str):
            titles[subject] = value
        elif predicate == "description":
            descriptions[subject] = _digest(value)
        elif predicate == "exits" and isinstance(value, Sequence):
            canonical = [
                canonical_direction(str(item)) for item in value
            ]
            exits[subject] = tuple(sorted(d for d in canonical if d))
        elif predicate.startswith("exit.") and isinstance(value, str):
            direction = canonical_direction(predicate.removeprefix("exit."))
            if direction:
                links[subject][direction] = value
    return [
        Place(
            place_id=place_id,
            session=_session_of(place_id),
            title=title,
            exits=exits.get(place_id, ()),
            description_digest=descriptions.get(place_id, ""),
            links=dict(links.get(place_id, {})),
        )
        for place_id, title in sorted(titles.items())
    ]


def _room_id(key: tuple[str, tuple[str, ...], str], ordinal: int) -> str:
    digest = _digest("|".join([key[0], ",".join(key[1]), key[2]]))
    return f"room:{digest}" if ordinal == 0 else f"room:{digest}#{ordinal}"


class _Union:
    """Places grouped into rooms. Groups only ever grow, so this settles."""

    def __init__(self, place_ids: Iterable[str]) -> None:
        self._parent = {place_id: place_id for place_id in place_ids}
        self.corroborated: set[str] = set()

    def find(self, place_id: str) -> str:
        root = place_id
        while self._parent[root] != root:
            root = self._parent[root]
        while self._parent[place_id] != root:
            self._parent[place_id], place_id = root, self._parent[place_id]
        return root

    def union(self, left: str, right: str) -> bool:
        a, b = self.find(left), self.find(right)
        if a == b:
            return False
        low, high = sorted((a, b))
        self._parent[high] = low
        return True

    def members(self) -> dict[str, list[str]]:
        groups: dict[str, list[str]] = defaultdict(list)
        for place_id in self._parent:
            groups[self.find(place_id)].append(place_id)
        return {root: sorted(ids) for root, ids in groups.items()}


def _proven_different(
    by_key: Mapping[tuple[str, tuple[str, ...], str], Sequence[Place]],
    index: Mapping[str, Place],
) -> set[frozenset[str]]:
    """Pairs the evidence proves are different rooms, closed over the map.

    Different keys are different rooms. Beyond that, difference travels:
    two places that look alike are still different when a direction they
    both walked leads to rooms already proven different. Applying that
    until it stops adding pairs is what stops a chain of lookalikes from
    merging one hop above a contradiction.
    """
    proven: set[frozenset[str]] = set()
    while True:
        found = False
        for _key, candidates in sorted(by_key.items()):
            for i, place in enumerate(candidates):
                for other in candidates[i + 1:]:
                    pair = frozenset((place.place_id, other.place_id))
                    if pair in proven:
                        continue
                    if _walks_apart(place, other, index, proven):
                        proven.add(pair)
                        found = True
        if not found:
            return proven


def _differ(
    left: str,
    right: str,
    index: Mapping[str, Place],
    proven: set[frozenset[str]],
) -> bool:
    """True when two observed places are known to be different rooms."""
    if left == right:
        return False
    here, there = index.get(left), index.get(right)
    if here is None or there is None:
        return False
    if here.key != there.key:
        return True
    return frozenset((left, right)) in proven


def _walks_apart(
    place: Place,
    member: Place,
    index: Mapping[str, Place],
    proven: set[frozenset[str]],
) -> bool:
    """True when a direction both walked leads to rooms known to differ."""
    for direction, target in place.links.items():
        other = member.links.get(direction)
        if other is None or target == other:
            continue
        if _differ(target, other, index, proven):
            return True
    return False


def _corroborates(
    place: Place,
    member: Place,
    union: _Union,
    landmarks: Mapping[str, tuple[str, tuple[str, ...], str]],
) -> bool:
    """True when a shared direction leads to the same room.

    Two rooms count as the same when they are already one room, or when
    both are landmarks of the same kind: places whose key names one room
    in everything observed. A key whose own places are proven different
    is not a landmark, so a lookalike cannot vouch for a lookalike.
    """
    for direction, target in place.links.items():
        other = member.links.get(direction)
        if other is None:
            continue
        if target == other:
            return True
        if target in union._parent and other in union._parent:
            if union.find(target) == union.find(other):
                return True
        here = landmarks.get(target)
        if here is not None and here == landmarks.get(other):
            return True
    return False


def _landmarks(
    by_key: Mapping[tuple[str, tuple[str, ...], str], Sequence[Place]],
    proven: set[frozenset[str]],
) -> dict[str, tuple[str, tuple[str, ...], str]]:
    """Places whose key names exactly one room in everything observed.

    A key loses that standing the moment two of its own places are proven
    different, since it then demonstrably names more than one room.
    """
    return {
        place.place_id: key
        for key, candidates in by_key.items()
        if _never_duplicated(candidates)
        and not any(
            frozenset((a.place_id, b.place_id)) in proven
            for i, a in enumerate(candidates)
            for b in candidates[i + 1:]
        )
        for place in candidates
    }


def _blocked(place: Place, other: Place, union: _Union,
             index: Mapping[str, Place],
             proven: set[frozenset[str]]) -> bool:
    """True when joining these two rooms would contradict any pair in them.

    The test covers both rooms entirely, not just the arriving place.
    Checking one side lets a partly observed place act as glue between
    two places that contradict each other, merging rooms the evidence
    separates: a middleman agrees with each of them about one direction
    while they disagree about another.
    """
    members = union.members()
    here = members[union.find(place.place_id)]
    there = members[union.find(other.place_id)]
    return any(
        _walks_apart(index[a], index[b], index, proven)
        or _walks_apart(index[b], index[a], index, proven)
        or _differ(a, b, index, proven)
        for a in here
        for b in there
    )


def resolve(
    places: Sequence[Place],
    *,
    max_rounds: int | None = None,
    merge_without_evidence: bool = True,
) -> list[Binding]:
    """Bind places to rooms, growing groups until no further merge holds.

    Two places bind when no linked direction leads to places known to
    differ, and either a shared direction agrees, or the key was never
    live twice inside one session and exactly one room is open to them.
    A key that repeats within a run is ambiguous by observation, which is
    the signature of a maze, and ambiguous keys merge only on agreement.

    Groups only grow, so the result settles. Where the evidence conflicts
    the outcome can still depend on which merge is considered first, so a
    conflicting neighbourhood is reported as split rather than resolved.
    Splitting is the safe error: a duplicate costs walking, while a wrong
    merge invents a route that does not exist.
    """
    by_key: dict[tuple[str, tuple[str, ...], str], list[Place]] = defaultdict(list)
    for place in sorted(places, key=lambda p: p.place_id):
        by_key[place.key].append(place)
    index = {place.place_id: place for place in places}
    union = _Union(index)
    proven = _proven_different(by_key, index)
    landmarks = _landmarks(by_key, proven)
    rounds = len(places) + 1 if max_rounds is None else max_rounds

    for _ in range(rounds):
        changed = _merge_on_agreement(
            by_key, union, index, landmarks, proven
        )
        if merge_without_evidence:
            changed = _merge_unambiguous(
                by_key, union, index, proven
            ) or changed
        if not changed:
            break
    else:
        raise ValueError(
            f"room identity did not settle in {rounds} rounds over "
            f"{len(places)} places"
        )

    members = union.members()
    ordinals: dict[tuple[str, tuple[str, ...], str], int] = defaultdict(int)
    bindings: list[Binding] = []
    for root in sorted(members):
        ids = members[root]
        key = index[ids[0]].key
        ordinal = ordinals[key]
        ordinals[key] += 1
        room = _room_id(key, ordinal)
        for place_id in ids:
            bindings.append(
                Binding(
                    place_id,
                    room,
                    CORROBORATED if place_id in union.corroborated
                    else UNCONTESTED,
                )
            )
    return sorted(bindings, key=lambda binding: binding.place_id)


def _merge_on_agreement(
    by_key: Mapping[tuple[str, tuple[str, ...], str], Sequence[Place]],
    union: _Union,
    index: Mapping[str, Place],
    landmarks: Mapping[str, tuple[str, tuple[str, ...], str]],
    proven: set[frozenset[str]],
) -> bool:
    """Join places whose shared exits agree, one neighbourhood at a time.

    Agreement is read as a whole: places that agree, directly or through
    another, form one neighbourhood, and a neighbourhood joins only when
    nothing inside it contradicts. Deciding place by place would let
    whichever pair was considered first attach a lookalike to one side
    of a disagreement, so identity would follow the order of the walk
    rather than the evidence.
    """
    changed = False
    for _key, candidates in sorted(by_key.items()):
        agreement: dict[str, set[str]] = {
            place.place_id: set() for place in candidates
        }
        for i, place in enumerate(candidates):
            for other in candidates[i + 1:]:
                if _blocked(place, other, union, index, proven):
                    continue
                if _corroborates(place, other, union, landmarks) or (
                    _corroborates(other, place, union, landmarks)
                ):
                    agreement[place.place_id].add(other.place_id)
                    agreement[other.place_id].add(place.place_id)
        for component in _components(agreement):
            if len(component) < 2:
                continue
            if any(
                _blocked(index[a], index[b], union, index, proven)
                for i, a in enumerate(component)
                for b in component[i + 1:]
            ):
                continue
            first = component[0]
            union.corroborated.update(component)
            for member in component[1:]:
                changed = union.union(first, member) or changed
    return changed


def _components(agreement: Mapping[str, set[str]]) -> list[list[str]]:
    """The groups of places that agree, directly or through another."""
    seen: set[str] = set()
    found: list[list[str]] = []
    for start in sorted(agreement):
        if start in seen:
            continue
        stack, members = [start], []
        seen.add(start)
        while stack:
            node = stack.pop()
            members.append(node)
            for neighbour in sorted(agreement[node] - seen):
                seen.add(neighbour)
                stack.append(neighbour)
        found.append(sorted(members))
    return found


def _merge_unambiguous(
    by_key: Mapping[tuple[str, tuple[str, ...], str], Sequence[Place]],
    union: _Union,
    index: Mapping[str, Place],
    proven: set[frozenset[str]],
) -> bool:
    """Join the places of a key that names one room in observed history.

    A key that never appeared twice inside a single run names one room,
    so its places are the same room unless the graph objects. They join
    only when no pair contradicts: one disagreement anywhere means the
    key is not the landmark it looked like, and nothing merges.
    """
    changed = False
    for _key, candidates in sorted(by_key.items()):
        if len(candidates) < 2 or not _never_duplicated(candidates):
            continue
        if any(
            _blocked(place, other, union, index, proven)
            for i, place in enumerate(candidates)
            for other in candidates[i + 1:]
        ):
            continue
        first = candidates[0].place_id
        for other in candidates[1:]:
            changed = union.union(first, other.place_id) or changed
    return changed


def _never_duplicated(candidates: Sequence[Place]) -> bool:
    """True when this key was never live twice inside one session."""
    seen: set[str] = set()
    for place in candidates:
        if place.session in seen:
            return False
        seen.add(place.session)
    return True




def record(store: Any, assertions: Sequence[Any]) -> dict[str, str]:
    """Recompute room identity from the store and write it down.

    The derived layer is dropped whole and rebuilt, because identity is a
    conclusion about the facts underneath rather than an observation of
    its own. Returns the place-to-room mapping that was recorded.
    """
    places = places_from_facts(assertions)
    bindings = resolve(places)
    evidence: dict[str, Any] = {}
    for assertion in assertions:
        if assertion.subject.startswith("place:"):
            evidence.setdefault(
                assertion.subject,
                assertion.latest_evidence or assertion.evidence,
            )
    store.retract_layer("derived", reason="identity recompute")
    transaction = uuid.uuid4().hex
    recorded: dict[str, str] = {}
    for binding in bindings:
        source = evidence.get(binding.place_id)
        if source is None:
            continue
        store.assert_fact(
            binding.place_id,
            "identity.room",
            binding.room_id,
            layer="derived",
            confidence=binding.confidence,
            evidence=source,
            transaction_id=transaction,
        )
        recorded[binding.place_id] = binding.room_id
    return recorded


def rooms_of(store: Any) -> dict[str, str]:
    """The recorded place-to-room mapping, empty when none was written."""
    return {
        assertion.subject: assertion.value
        for assertion in store.current_facts(layer="derived")
        if assertion.predicate == "identity.room"
        and isinstance(assertion.value, str)
    }
