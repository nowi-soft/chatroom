import json
from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase


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
        cls.conversation = cls.env["chatroom.ai.conversation"].create(
            {
                "agent_id": cls.agent.id,
                "room_id": cls.room.id,
            }
        )
        cls.tool = cls.env["chatroom.ai.tool"].create(
            {
                "name": "Echo",
                "code_name": "echo_tool",
                "description": "Echo params",
                "parameters_schema": '{"type":"object"}',
                "implementation_type": "python",
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
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
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
        self.conversation.context_messages = "{bad"
        self.assertEqual(self.conversation._load_context(), [])

        msg1 = self.env["chatroom.message"].create(
            {"room_id": self.room.id, "body": "one", "direction": "incoming"}
        )
        msg2 = self.env["chatroom.message"].create(
            {"room_id": self.room.id, "body": "two", "direction": "incoming"}
        )
        msg3 = self.env["chatroom.message"].create(
            {"room_id": self.room.id, "body": "three", "direction": "incoming"}
        )
        self.conversation.add_message(msg1)
        self.conversation.add_message(msg2)
        self.conversation.add_message(msg3)

        self.assertEqual(self.conversation.message_count, 2)
        self.assertTrue(self.conversation.summary)

        self.conversation.add_tool_results(
            [{"id": "call_1", "name": "echo_tool", "result": {"ok": True}}]
        )
        self.assertTrue(self.conversation.has_tool_call_result("call_1"))
        self.assertEqual(self.conversation.get_tool_call_result("call_1")["ok"], True)

        built = self.conversation.build_context_messages()
        self.assertEqual(built[0]["role"], "system")

    def test_tool_methods(self):
        tool = self.env["chatroom.ai.tool"].create(
            {
                "name": "Tool 2",
                "code_name": "tool_2",
                "description": "desc",
                "parameters_schema": '{"foo": 1}',
                "implementation_type": "python",
                "python_code_source": "result = {'success': True}",
                "python_code": "",
            }
        )
        definition = tool.get_tool_definition()
        self.assertEqual(definition["parameters"]["type"], "object")

        action = tool.action_copy_source_to_implementation()
        self.assertEqual(action["tag"], "display_notification")

        exec_result = tool.execute(self.room, {"x": 1}, self.conversation)
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
