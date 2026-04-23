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
        cls.room.write({"ai_agent_id": cls.agent.id})
        cls.conversation = cls.room  # room holds AI context directly

    def test_load_context_invalid_json(self):
        self.room.ai_context_messages = "{broken"
        with mute_logger("odoo.addons.chatroom_ai.models.chatroom_room"):
            self.assertEqual(self.room._load_context(), [])

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

        self.room.add_message(msg1)
        self.room.add_message(msg2)
        self.room.add_message(msg3)

        context = self.room._load_context()
        self.assertEqual(len(context), 2)
        self.assertTrue(self.room.ai_summary)

    def test_build_context_messages(self):
        self.room.ai_context_messages = json.dumps(
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
        messages = self.room.build_context_messages()

        self.assertEqual(messages[0]["role"], "system")
        self.assertIn("CHANNEL CONTEXT", messages[0]["content"])
        self.assertTrue(any(m["role"] == "assistant" for m in messages))

    def test_tool_results_helpers(self):
        self.room.ai_context_messages = json.dumps([])
        self.room.add_tool_results(
            [
                {"id": "call_1", "name": "x", "result": {"ok": True}},
                {"id": "call_1", "name": "x", "result": {"ok": True}},
            ]
        )

        self.assertTrue(self.room.has_tool_call_result("call_1"))
        result = self.room.get_tool_call_result("call_1")
        self.assertEqual(result["ok"], True)
        # second add_tool_results with same id is deduped
        context = self.room._load_context()
        tool_msgs = [m for m in context if m.get("role") == "tool"]
        self.assertEqual(len(tool_msgs), 1)

    def test_state_field(self):
        self.room.write({"ai_conversation_state": "paused"})
        self.assertEqual(self.room.ai_conversation_state, "paused")
        self.room.write({"ai_conversation_state": "active"})
        self.assertEqual(self.room.ai_conversation_state, "active")
