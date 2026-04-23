from odoo.tests.common import TransactionCase


class TestChatroomAIRoom(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.room = cls.env["chatroom.room"].create({"name": "AI Room Actions"})

    def test_action_enable_ai_sets_flags(self):
        self.room.write({"ai_enabled": False, "needs_attention": True})

        action = self.room.action_enable_ai()

        self.assertTrue(self.room.ai_enabled)
        self.assertFalse(self.room.needs_attention)
        self.assertEqual(action["type"], "ir.actions.client")
        self.assertEqual(action["tag"], "display_notification")

    def test_action_disable_ai(self):
        self.room.write({"ai_enabled": True})

        action = self.room.action_disable_ai()

        self.assertFalse(self.room.ai_enabled)
        self.assertEqual(action["type"], "ir.actions.client")
        self.assertEqual(action["tag"], "display_notification")

    def test_action_pause_ai_and_request_attention(self):
        self.room.write({"ai_enabled": True, "needs_attention": False})

        self.room.action_pause_ai_and_request_attention()

        self.assertFalse(self.room.ai_enabled)
        self.assertTrue(self.room.needs_attention)
        self.assertEqual(self.room.ai_conversation_state, "paused")
