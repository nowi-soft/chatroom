from unittest.mock import patch

from odoo.tests.common import TransactionCase
from odoo.tools import mute_logger


class TestAIMessageProcessing(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.provider = cls.env["chatroom.ai.provider"].create(
            {
                "name": "OpenAI Provider Msg",
                "provider_type": "openai",
                "state": "active",
                "default_model": "gpt-4o-mini",
                "api_key": "test-key",
            }
        )
        cls.agent = cls.env["chatroom.ai.agent"].create(
            {
                "name": "Processor Agent",
                "provider_id": cls.provider.id,
                "system_prompt": "Answer shortly",
                "unsupported_media_message": "Unsupported media",
            }
        )
        cls.room = cls.env["chatroom.room"].create(
            {
                "name": "Process Room",
                "ai_enabled": True,
                "ai_agent_id": cls.agent.id,
            }
        )

    def test_job_process_room_messages_completes(self):
        msg_text = self.env["chatroom.message"].create(
            {
                "room_id": self.room.id,
                "body": "hello",
                "direction": "incoming",
            }
        )
        msg_media = self.env["chatroom.message"].create(
            {
                "room_id": self.room.id,
                "body": "image",
                "direction": "incoming",
                "message_type": "image",
            }
        )

        pending = msg_text | msg_media
        pending.write({"ai_processing_state": "pending", "ai_pending_processing": True})

        agent_class = type(self.agent)
        with (
            patch.object(
                agent_class,
                "get_or_create_conversation",
                autospec=True,
                return_value=self.room,
            ),
            patch.object(
                agent_class,
                "_generate_and_send_response",
                autospec=True,
                return_value=None,
            ),
        ):
            msg_text._job_process_room_messages()

        self.assertEqual(msg_text.ai_processing_state, "completed")
        self.assertEqual(msg_media.ai_processing_state, "completed")

        unsupported = self.env["chatroom.message"].search(
            [
                ("room_id", "=", self.room.id),
                ("is_ai_generated", "=", True),
                ("body", "=", "Unsupported media"),
            ],
            limit=1,
        )
        self.assertTrue(unsupported)

    def test_job_process_room_messages_failure_marks_attention(self):
        msg = self.env["chatroom.message"].create(
            {
                "room_id": self.room.id,
                "body": "trigger fail",
                "direction": "incoming",
            }
        )
        msg.write({"ai_processing_state": "pending", "ai_pending_processing": True})

        room_class = type(self.room)
        agent_class = type(self.agent)
        with (
            patch.object(
                agent_class,
                "get_or_create_conversation",
                autospec=True,
                return_value=self.room,
            ),
            patch.object(
                room_class,
                "add_message",
                autospec=True,
                side_effect=RuntimeError("boom"),
            ),
        ):
            with mute_logger("odoo.addons.chatroom_ai.models.chatroom_message"):
                with self.assertRaises(RuntimeError):
                    msg._job_process_room_messages()
