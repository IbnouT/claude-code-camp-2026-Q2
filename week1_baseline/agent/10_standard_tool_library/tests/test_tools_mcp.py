"""The host layer: registration, prefixing, collisions, schemas, allow/deny."""

from boukensha.errors import McpToolCollisionError
from boukensha.registry import Registry
from boukensha.tool import Tool
from boukensha.tools import mcp as mcp_host

from .helper import PY, STUB, McpTestCase, spawn_stub


class TestRegistration(McpTestCase):
    def test_register_populates_the_registry_from_discovery(self):
        registry = Registry()
        self.track(mcp_host.register(registry, PY, args=[STUB]))
        self.assertEqual({"say", "boom"}, set(registry.tools))
        self.assertIn("you say: yo", registry.dispatch("say", {"message": "yo"}))

    def test_prefix_is_agent_side_and_the_server_sees_bare_names(self):
        registry = Registry()
        mcp_host.register_client(registry, self.track(spawn_stub()), prefix="tbamud")
        self.assertIn("tbamud__say", registry.tools)
        self.assertNotIn("say", registry.tools)
        # The dispatch succeeding proves the prefix never reached the wire.
        self.assertIn("you say: hey",
                      registry.dispatch("tbamud__say", {"message": "hey"}))

    def test_none_prefix_yields_bare_names(self):
        registry = Registry()
        mcp_host.register_client(registry, self.track(spawn_stub()), prefix=None)
        self.assertIn("say", registry.tools)
        self.assertNotIn("tbamud__say", registry.tools)

    def test_result_over_the_size_cap_is_truncated_with_a_stated_count(self):
        registry = Registry()
        mcp_host.register_client(registry, self.track(spawn_stub()), prefix="cap")
        result = registry.tools["cap__say"].handler(message="x" * 9000)
        self.assertIn("[truncated", result)
        self.assertLessEqual(len(result), mcp_host.MAX_RESULT_CHARS + 60)


class TestSchemas(McpTestCase):
    def _say_tool(self, env=None):
        registry = Registry()
        mcp_host.register_client(registry, self.track(spawn_stub(env=env)))
        return registry.tools["say"]

    def test_enum_is_surfaced_in_the_parameter_description(self):
        say = self._say_tool()
        self.assertIn("(one of: whisper, normal, shout)",
                      say.parameters["volume"]["description"])

    def test_enum_stays_a_real_json_schema_field(self):
        # Backends pass parameters to the wire, so providers enforce it.
        say = self._say_tool()
        self.assertEqual(["whisper", "normal", "shout"],
                         say.parameters["volume"]["enum"])

    def test_only_input_schema_required_members_are_marked_required(self):
        say = self._say_tool()
        self.assertEqual(["message"], say.required_parameters)
        self.assertIn("volume", say.parameters)

    def test_a_structured_parameter_keeps_its_full_schema(self):
        # An array is not flattened to a bare string type.
        say = self._say_tool(env={"STUB_ARRAY_PARAM": "1"})
        self.assertEqual("array", say.parameters["targets"]["type"])
        self.assertEqual({"type": "string"}, say.parameters["targets"]["items"])


class TestCollisions(McpTestCase):
    def test_a_colliding_agent_side_name_raises_naming_the_fix(self):
        registry = Registry()
        mcp_host.register_client(registry, self.track(spawn_stub()), prefix=None)
        with self.assertRaises(McpToolCollisionError) as ctx:
            mcp_host.register_client(registry, self.track(spawn_stub()), prefix=None)
        self.assertIn("say", str(ctx.exception))
        self.assertIn("prefix", str(ctx.exception))

    def test_a_collision_with_a_pre_existing_non_mcp_tool_raises(self):
        registry = Registry()
        registry.register(Tool("say", "an inline tool", {}, lambda: "inline"))
        with self.assertRaises(McpToolCollisionError):
            mcp_host.register_client(registry, self.track(spawn_stub()))


class TestAllowDeny(McpTestCase):
    def test_allow_admits_only_the_named_tools(self):
        registry = Registry()
        self.track(mcp_host.register(registry, PY, args=[STUB], allow=["say"]))
        self.assertEqual({"say"}, set(registry.tools))

    def test_deny_excludes_the_named_tools(self):
        registry = Registry()
        self.track(mcp_host.register(registry, PY, args=[STUB], deny=["boom"]))
        self.assertEqual({"say"}, set(registry.tools))
