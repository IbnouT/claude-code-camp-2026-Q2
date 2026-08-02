"""Deterministic OpenAPI 3.1 publication from the operation registry."""

from __future__ import annotations

import json
import re
from pathlib import Path

from pydantic import BaseModel
from pydantic.json_schema import JsonSchemaMode, models_json_schema

from .contracts import PUBLIC_COMPONENT_MODELS
from .operations import API_V1_OPERATIONS, OperationSpec, ResponseSpec

OPENAPI_VERSION = "3.1.1"
API_VERSION = "1.0.0"
_CONVERTER = re.compile(r"{([a-zA-Z_][a-zA-Z0-9_]*):[^}]+}")


def _model_ref(model: type[BaseModel]) -> dict[str, str]:
    return {"$ref": f"#/components/schemas/{model.__name__}"}


def _openapi_path(path: str) -> str:
    return f"/api/v1{_CONVERTER.sub(lambda match: f'{{{match.group(1)}}}', path)}"


def _response_document(response: ResponseSpec) -> dict[str, object]:
    content: dict[str, object] = {}
    if response.model is not None:
        content[response.media_type] = {
            "schema": _model_ref(response.model),
        }
    elif response.media_type == "audio/mpeg":
        content[response.media_type] = {
            "schema": {"type": "string", "format": "binary"},
        }
    return {
        "description": response.description,
        "content": content,
    }


def _operation_document(operation: OperationSpec) -> dict[str, object]:
    document: dict[str, object] = {
        "operationId": operation.operation_id,
        "tags": list(operation.tags),
        "parameters": [
            {
                "name": parameter.name,
                "in": parameter.location,
                "required": parameter.required,
                "schema": parameter.schema,
            }
            for parameter in operation.parameters
        ],
        "responses": {
            str(response.status): _response_document(response)
            for response in operation.responses
        },
    }
    if operation.request_model is not None:
        document["requestBody"] = {
            "required": True,
            "content": {
                "application/json": {
                    "schema": _model_ref(operation.request_model),
                }
            },
        }
    return document


def _public_models() -> tuple[type[BaseModel], ...]:
    models: set[type[BaseModel]] = set(PUBLIC_COMPONENT_MODELS)
    for operation in API_V1_OPERATIONS:
        if operation.request_model is not None:
            models.add(operation.request_model)
        for response in operation.responses:
            if response.model is not None:
                models.add(response.model)
    return tuple(sorted(models, key=lambda model: model.__name__))


def openapi_document() -> dict[str, object]:
    """Return the canonical deterministic OpenAPI document."""

    inputs: list[tuple[type[BaseModel], JsonSchemaMode]] = [
        (model, "validation") for model in _public_models()
    ]
    _, schemas = models_json_schema(
        inputs,
        ref_template="#/components/schemas/{model}",
    )
    paths: dict[str, dict[str, object]] = {}
    for operation in API_V1_OPERATIONS:
        paths.setdefault(_openapi_path(operation.path), {})[
            operation.method.casefold()
        ] = _operation_document(operation)
    return {
        "openapi": OPENAPI_VERSION,
        "info": {
            "title": "Boukensha Observatory API",
            "version": API_VERSION,
            "description": (
                "Versioned local contracts for Live, Sessions, Experiments, "
                "Knowledge, and evidence queries."
            ),
        },
        "servers": [{"url": "/"}],
        "paths": paths,
        "components": {
            "schemas": schemas.get("$defs", {}),
        },
    }


def canonical_openapi_json() -> str:
    """Serialize the canonical document byte-for-byte deterministically."""

    return (
        json.dumps(
            openapi_document(),
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        )
        + "\n"
    )


def canonical_operations_json() -> str:
    """Serialize the callable operation inventory deterministically."""

    operations = [
        [
            operation.method,
            _openapi_path(operation.path),
            operation.operation_id,
        ]
        for operation in API_V1_OPERATIONS
    ]
    return json.dumps(operations, indent=2, ensure_ascii=False) + "\n"


def write_openapi(path: Path) -> None:
    """Write one deterministic schema artifact."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_openapi_json(), encoding="utf-8")


def main() -> None:
    """Write the checked-in schema artifact."""

    root = Path(__file__).resolve().parents[3]
    write_openapi(root / "openapi" / "observatory-v1.json")
    (root / "openapi" / "operations.json").write_text(
        canonical_operations_json(),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
