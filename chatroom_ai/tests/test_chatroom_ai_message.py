from unittest.mock import patch

from odoo.tests.common import TransactionCase


class TestChatroomAIMessage(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.room = cls.env["chatroom.room"].create({"name": "AI Room"})

    def test_incoming_message_marks_ai_pending(self):
        message = self.env["chatroom.message"].create(
            {
                "room_id": self.room.id,
                "body": "Need AI answer",
                "direction": "incoming",
            }
        )

        self.assertTrue(message.ai_pending_processing)
        self.assertEqual(message.ai_processing_state, "pending")

        job = self.env["queue.job"].sudo().search(
            [("identity_key", "=", f"ai_process_room_{self.room.id}")],
            limit=1,
        )
        self.assertTrue(job)

    def test_outgoing_message_does_not_mark_ai_pending(self):
        message = self.env["chatroom.message"].create(
            {
                "room_id": self.room.id,
                "body": "Agent answer",
                "direction": "outgoing",
                "is_ai_generated": True,
            }
        )

        self.assertFalse(message.ai_pending_processing)
        self.assertEqual(message.ai_processing_state, "pending")

    def test_needs_attention_notifies_users_without_all_user_ids(self):
        bus_bus_class = type(self.env["bus.bus"])

        with patch.object(bus_bus_class, "_sendone", autospec=True) as sendone:
            self.room.write({"needs_attention": True})

        self.assertGreaterEqual(sendone.call_count, 1)
