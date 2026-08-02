"""Canonical version 1 Observatory API contracts and route registry."""

from .openapi import openapi_document
from .operations import API_V1_OPERATIONS, api_v1_routes

__all__ = ["API_V1_OPERATIONS", "api_v1_routes", "openapi_document"]
