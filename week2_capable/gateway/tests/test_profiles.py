"""Allowlisted profiles and generated direct and hybrid surfaces."""

from __future__ import annotations

import json

import pytest

from mud_gateway.profiles import (
    ALL_AVAILABLE,
    PROFILES,
    PermissionDenied,
    Profile,
    ProfileError,
    Surface,
    load_profile,
)


class TestDirectProfiles:
    def test_default_full_profile_does_not_advertise_raw(self):
        names = {
            schema["name"]
            for schema in Surface(PROFILES["direct-full"]).schemas()
        }
        assert "send_raw" not in names

    def test_custom_allowlist_advertises_only_configured_tools(self):
        profile = load_profile(
            "direct-full",
            allow=["move", "look", "send_raw"],
        )
        names = [schema["name"] for schema in Surface(profile).schemas()]
        assert names == ["look", "move", "send_raw"]

    def test_disabled_known_capability_is_rejected_server_side(self):
        surface = Surface(load_profile("direct-core"))
        with pytest.raises(PermissionDenied, match="disabled"):
            surface.resolve("cast_spell", {"spell": "armor"})

    def test_unknown_or_unavailable_configuration_fails_at_startup(self):
        with pytest.raises(ProfileError, match="unknown"):
            Profile("bad", "direct", frozenset({"not-real"}))
        with pytest.raises(ProfileError, match="unavailable"):
            Profile("bad", "direct", frozenset({"navigate"}))

    def test_profile_identity_is_stable_for_allowlist_order(self):
        first = load_profile("direct-full", allow=["look", "move"])
        second = load_profile("direct-full", allow=["move", "look"])
        assert first.id == second.id
        assert first.capability_digest == second.capability_digest

    def test_profile_and_returned_schemas_cannot_mutate_the_session_surface(self):
        configured = {"look"}
        profile = Profile("fixed", "direct", configured)
        surface = Surface(profile)
        configured.add("move")
        returned = surface.schemas()
        returned[0]["inputSchema"]["properties"]["injected"] = {"type": "string"}
        assert profile.allowed == frozenset({"look"})
        assert "injected" not in (
            surface.schemas()[0]["inputSchema"]["properties"])


class TestHybridProjection:
    def test_full_hybrid_collapses_capabilities_into_three_tools(self):
        surface = Surface(PROFILES["hybrid-full"])
        assert [schema["name"] for schema in surface.schemas()] == [
            "move", "act", "interact",
        ]

    def test_group_call_resolves_to_the_underlying_capability(self):
        surface = Surface(PROFILES["hybrid-full"])
        invocation = surface.resolve(
            "act",
            {
                "action": "attack",
                "arguments": {"target": "rat"},
            },
        )
        assert invocation.capability.name == "attack"
        assert invocation.arguments == {"target": "rat", "style": "kill"}

    def test_group_validator_uses_the_capability_definition(self):
        surface = Surface(PROFILES["hybrid-full"])
        with pytest.raises(ValueError, match="not one of"):
            surface.resolve(
                "act",
                {
                    "action": "attack",
                    "arguments": {"target": "rat", "style": "hug"},
                },
            )

    def test_direct_name_is_not_a_backdoor_through_hybrid(self):
        surface = Surface(PROFILES["hybrid-full"])
        with pytest.raises(PermissionDenied):
            surface.resolve("attack", {"target": "rat"})

    def test_group_schema_contains_generated_per_capability_validation(self):
        act = next(
            schema for schema in Surface(PROFILES["hybrid-full"]).schemas()
            if schema["name"] == "act"
        )
        encoded = json.dumps(act)
        assert '"const": "attack"' in encoded
        assert '"style"' in encoded
        assert '"const": "send_raw"' not in encoded


class TestMeasurements:
    def test_every_named_profile_reports_bytes_and_coverage(self):
        for profile in PROFILES.values():
            measurement = Surface(profile).measurement()
            assert measurement["schema_bytes"] > 0
            assert 0 < measurement["coverage"] <= 1
            assert len(measurement["capability_digest"]) == 16

    def test_available_count_includes_deny_by_default_raw(self):
        assert "send_raw" in ALL_AVAILABLE
