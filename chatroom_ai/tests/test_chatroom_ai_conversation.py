import json
from unittest import SkipTest

from odoo.tests.common import TransactionCase
from odoo.tools import mute_logger


class TestChatroomAIConversation(TransactionCase):
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
                "name": "Agent",
                "provider_id": cls.provider.id,
                "system_prompt": "Be concise",
                "max_conversation_length": 2,
            }
        )
        cls.room = cls.env["chatroom.room"].create({"name": "Conversation Room"})
        cls.conversation = cls.env["chatroom.ai.conversation"].create(
            {
                "agent_id": cls.agent.id,
                "room_id": cls.room.id,
            }
        )

    def test_load_context_invalid_json(self):
        self.conversation.context_messages = "{broken"
        with mute_logger("odoo.addons.chatroom_ai.models.chatroom_ai_conversation"):
            self.assertEqual(self.conversation._load_context(), [])

    def test_add_message_and_summary(self):
        msg1 = self.env["chatroom.message"].create(
            {
                "room_id": self.room.id,
                "body": "first",
                "direction": "incoming",
            }
        )
        msg2 = self.env["chatroom.message"].create(
            {
                "room_id": self.room.id,
                "body": "second",
                "direction": "incoming",
            }
        )
        msg3 = self.env["chatroom.message"].create(
            {
                "room_id": self.room.id,
                "body": "third",
                "direction": "incoming",
            }
        )

        self.conversation.add_message(msg1)
        self.conversation.add_message(msg2)
        self.conversation.add_message(msg3)

        self.assertEqual(self.conversation.message_count, 2)
        self.assertTrue(self.conversation.summary)
        self.assertGreaterEqual(self.conversation.human_messages, 3)

    def test_build_context_messages(self):
        self.conversation.context_messages = json.dumps(
            [
                {
                    "role": "user",
                    "content": "Hi",
                    "timestamp": "2026-01-01T12:00:00",
                },
                {
                    "role": "assistant",
                    "content": "Hello",
                },
            ]
        )
        messages = self.conversation.build_context_messages()

        self.assertEqual(messages[0]["role"], "system")
        self.assertIn("CHANNEL CONTEXT", messages[0]["content"])
        self.assertTrue(any(m["role"] == "assistant" for m in messages))

    def test_tool_results_helpers(self):
        self.conversation.context_messages = json.dumps([])
        self.conversation.add_tool_results(
            [
                {"id": "call_1", "name": "x", "result": {"ok": True}},
                {"id": "call_1", "name": "x", "result": {"ok": True}},
            ]
        )

        self.assertTrue(self.conversation.has_tool_call_result("call_1"))
        result = self.conversation.get_tool_call_result("call_1")
        self.assertEqual(result["ok"], True)
        self.assertEqual(self.conversation.tool_executions, 1)

    def test_state_actions(self):
        self.conversation.action_pause()
        self.assertEqual(self.conversation.state, "paused")
        self.conversation.action_resume()
        self.assertEqual(self.conversation.state, "active")
        self.conversation.action_complete()
        self.assertEqual(self.conversation.state, "completed")
