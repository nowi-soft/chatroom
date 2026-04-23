import json
from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase
from odoo.tools import mute_logger


class TestAICoreCoverage(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.provider = cls.env["chatroom.ai.provider"].create(
            {
                "name": "OpenAI Provider",
                "provider_type": "openai",
                "state": "active",
                "default_model": "gpt-4o-mini",
                "api_key": "test-key",
            }
        )
        cls.agent = cls.env["chatroom.ai.agent"].create(
            {
                "name": "AI Agent",
                "provider_id": cls.provider.id,
                "system_prompt": "Short answers",
                "max_conversation_length": 2,
            }
        )
        cls.room = cls.env["chatroom.room"].create({"name": "AI Room"})
        cls.room.write({"ai_agent_id": cls.agent.id})
        cls.conversation = cls.room  # room holds AI context directly
        cls.tool = cls.env["chatroom.ai.tool"].create(
            {
                "name": "Echo",
                "code_name": "echo_tool",
                "description": "Echo params",
                "parameters_schema": '{"type":"object"}',
                "python_code": "result = {'success': True, 'echo': params}",
            }
        )
        cls.agent.tool_ids = [(4, cls.tool.id)]

    def test_provider_action_and_generation_contract(self):
        provider_class = type(self.provider)
        with patch.object(
            provider_class,
            "_test_provider_connection",
            autospec=True,
            return_value={"success": True},
        ):
            action = self.provider.action_test_connection()
        self.assertEqual(action["tag"], "display_notification")

        with patch.object(
            provider_class,
            "_generate_completion_impl",
            autospec=True,
            return_value={
                "content": "ok",
                "usage": {
                    "prompt_tokens": 1,
                    "completion_tokens": 1,
                    "total_tokens": 2,
                },
            },
        ):
            result = self.provider.generate_completion(
                messages=[{"role": "user", "content": "hello"}],
                model="gpt-4o-mini",
            )
        self.assertEqual(result["content"], "ok")

    def test_provider_inactive_raises(self):
        self.provider.state = "draft"
        with self.assertRaises(UserError):
            self.provider.generate_completion(messages=[])
        self.provider.state = "active"

    def test_conversation_context_helpers(self):
        self.room.ai_context_messages = "{bad"
        with mute_logger("odoo.addons.chatroom_ai.models.chatroom_room"):
            self.assertEqual(self.room._load_context(), [])
        self.room.ai_context_messages = json.dumps([])

        msg1 = self.env["chatroom.message"].create(
            {"room_id": self.room.id, "body": "one", "direction": "incoming"}
        )
        msg2 = self.env["chatroom.message"].create(
            {"room_id": self.room.id, "body": "two", "direction": "incoming"}
        )
        msg3 = self.env["chatroom.message"].create(
            {"room_id": self.room.id, "body": "three", "direction": "incoming"}
        )
        self.room.add_message(msg1)
        self.room.add_message(msg2)
        self.room.add_message(msg3)

        context = self.room._load_context()
        self.assertEqual(len(context), 2)
        self.assertTrue(self.room.ai_summary)

        self.room.add_tool_results(
            [{"id": "call_1", "name": "echo_tool", "result": {"ok": True}}]
        )
        self.assertTrue(self.room.has_tool_call_result("call_1"))
        self.assertEqual(self.room.get_tool_call_result("call_1")["ok"], True)

        built = self.room.build_context_messages()
        self.assertEqual(built[0]["role"], "system")

    def test_tool_methods(self):
        tool = self.env["chatroom.ai.tool"].create(
            {
                "name": "Tool 2",
                "code_name": "tool_2",
                "description": "desc",
                "parameters_schema": '{"foo": 1}',
                "python_code": "result = {'success': True}",
            }
        )
        with mute_logger("odoo.addons.chatroom_ai.models.chatroom_ai_tool"):
            definition = tool.get_tool_definition()
        self.assertEqual(definition["parameters"]["type"], "object")

        exec_result = tool.execute(self.room, {"x": 1}, self.room)
        self.assertTrue(exec_result["success"])

    def test_agent_tool_call_and_response_flow(self):
        self.room.assigned_to_id = False
        self.assertTrue(self.agent.should_respond_to_room(self.room))

        result = self.agent._execute_tool_call(
            self.conversation,
            {
                "id": "call_exec",
                "function": {
                    "name": "echo_tool",
                    "arguments": json.dumps({"x": 7}),
                },
            },
        )
        self.assertTrue(result["success"])

        provider_class = type(self.provider)
        with patch.object(
            provider_class,
            "generate_completion",
            autospec=True,
            return_value={"content": "AI answer", "usage": {"total_tokens": 1}},
        ):
            self.agent._generate_and_send_response(self.conversation.id)

        ai_message = self.env["chatroom.message"].search(
            [
                ("room_id", "=", self.room.id),
                ("is_ai_generated", "=", True),
                ("body", "=", "AI answer"),
            ],
            order="id desc",
            limit=1,
        )
        self.assertTrue(ai_message)
