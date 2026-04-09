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

    def test_action_view_ai_conversations(self):
        action = self.room.action_view_ai_conversations()

        self.assertEqual(action["type"], "ir.actions.act_window")
        self.assertEqual(action["res_model"], "chatroom.ai.conversation")
        self.assertEqual(action["domain"], [("room_id", "=", self.room.id)])
