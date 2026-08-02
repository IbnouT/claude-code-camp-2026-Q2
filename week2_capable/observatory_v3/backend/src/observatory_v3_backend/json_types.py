"""Shared explicit JSON value types at retained and public boundaries."""

type JsonScalar = bool | int | float | str | None
type JsonValue = JsonScalar | list[JsonValue] | dict[str, JsonValue]
