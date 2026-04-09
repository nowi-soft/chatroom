from odoo.tests.common import TransactionCase


class TestResPartnerChatroom(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.room = cls.env["chatroom.room"].create({"name": "Partner Link Room"})

    def test_create_partner_links_to_room_from_context(self):
        partner = (
            self.env["res.partner"]
            .with_context(default_chatroom_room_id=self.room.id)
            .create({"name": "Context Partner"})
        )

        self.assertIn(partner, self.room.partner_ids)
        self.assertIn(self.room, partner.chatroom_ids)

    def test_action_view_chatrooms_returns_chatroom_client_action(self):
        partner = self.env["res.partner"].create({"name": "Action Partner"})
        action = partner.action_view_chatrooms()

        self.assertEqual(action["type"], "ir.actions.client")
        self.assertEqual(action["tag"], "chatroom.app")
        self.assertEqual(action["params"]["partner_id"], partner.id)

    def test_action_open_first_chatroom(self):
        partner = self.env["res.partner"].create({"name": "Open Room Partner"})
        partner.chatroom_ids = [(4, self.room.id)]

        action = partner.action_open_first_chatroom()
        self.assertEqual(action["type"], "ir.actions.client")
        self.assertEqual(action["tag"], "chatroom.app")
        self.assertEqual(action["params"]["room_id"], self.room.id)
