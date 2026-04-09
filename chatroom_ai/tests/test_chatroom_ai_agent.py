import json
from unittest import SkipTest
from unittest.mock import patch

from odoo.tests.common import TransactionCase


class TestChatroomAIAgent(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        selection = cls.env["chatroom.ai.provider"]._fields["provider_type"].selection
        selection_keys = {item[0] for item in selection}
        if "openai" not in selection_keys:
            raise SkipTest("openai provider type not available in chatroom_ai stage")

        cls.provider = cls.env["chatroom.ai.provider"].create(
            {
                "name": "Provider",
                "provider_type": "openai",
                "state": "active",
                "default_model": "test-model",
            }
        )
        cls.agent = cls.env["chatroom.ai.agent"].create(
            {
                "name": "Main Agent",
                "provider_id": cls.provider.id,
                "system_prompt": "Prompt",
            }
        )
        cls.room = cls.env["chatroom.room"].create({"name": "Agent Room"})
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
                "description": "Echoes params",
                "parameters_schema": '{"type":"object"}',
                "implementation_type": "python",
                "python_code": "result = {'success': True, 'echo': params}",
            }
        )
        cls.agent.tool_ids = [(4, cls.tool.id)]

    def test_should_respond_to_room(self):
        self.room.assigned_to_id = False
        self.assertTrue(self.agent.should_respond_to_room(self.room))
        self.room.assigned_to_id = self.env.user.id
        self.assertFalse(self.agent.should_respond_to_room(self.room))

    def test_get_or_create_conversation(self):
        conv = self.agent.get_or_create_conversation(self.room)
        self.assertTrue(conv)
        conv2 = self.agent.get_or_create_conversation(self.room)
        self.assertEqual(conv.id, conv2.id)

    def test_execute_tool_call_with_invalid_json_args(self):
        result = self.agent._execute_tool_call(
            self.conversation,
            {
                "id": "call_bad_json",
                "function": {
                    "name": "echo_tool",
                    "arguments": "{invalid-json",
                },
            },
        )

        self.assertTrue(result["success"])

    def test_execute_tool_call_duplicate_result(self):
        self.conversation.add_tool_results(
            [{"id": "call_dup", "name": "echo_tool", "result": {"ok": True}}]
        )
        result = self.agent._execute_tool_call(
            self.conversation,
            {
                "id": "call_dup",
                "function": {
                    "name": "echo_tool",
                    "arguments": json.dumps({"x": 1}),
                },
            },
        )
        self.assertEqual(result["ok"], True)

    def test_execute_tool_call_tool_not_found(self):
        result = self.agent._execute_tool_call(
            self.conversation,
            {
                "id": "call_not_found",
                "function": {"name": "unknown_tool", "arguments": "{}"},
            },
        )
        self.assertIn("error", result)

    def test_generate_and_send_response_content_flow(self):
        provider_class = type(self.provider)
        with patch.object(
            provider_class,
            "generate_completion",
            autospec=True,
            return_value={"content": "AI says hi", "usage": {"total_tokens": 1}},
        ):
            self.agent._generate_and_send_response(self.conversation.id)

        ai_message = self.env["chatroom.message"].search(
            [
                ("room_id", "=", self.room.id),
                ("is_ai_generated", "=", True),
                ("body", "=", "AI says hi"),
            ],
            order="id desc",
            limit=1,
        )
        self.assertTrue(ai_message)

    def test_generate_and_send_response_empty_result_pauses_room(self):
        provider_class = type(self.provider)
        room_class = type(self.room)
        with patch.object(
            provider_class,
            "generate_completion",
            autospec=True,
            return_value={},
        ), patch.object(
            room_class,
            "action_pause_ai_and_request_attention",
            autospec=True,
            return_value=True,
        ) as pause_action:
            self.agent._generate_and_send_response(self.conversation.id)

        self.assertGreaterEqual(pause_action.call_count, 1)
