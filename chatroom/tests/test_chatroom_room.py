from odoo.tests.common import TransactionCase


class TestChatroomRoom(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.room = cls.env["chatroom.room"].create(
            {
                "name": "Room Actions",
                "assigned_to_id": cls.env.user.id,
                "state": "assigned",
            }
        )

    def test_action_close_creates_internal_note_and_closes_room(self):
        self.room.action_close()

        self.assertEqual(self.room.state, "closed")
        self.assertFalse(self.room.assigned_to_id)

        note = self.env["chatroom.message"].search(
            [
                ("room_id", "=", self.room.id),
                ("is_internal", "=", True),
            ],
            order="id desc",
            limit=1,
        )
        self.assertTrue(note)
        self.assertEqual(note.direction, "outgoing")
        self.assertIn("Chat closed", note.body)

    def test_action_reopen_uses_assignment_state(self):
        self.room.write({"state": "closed", "assigned_to_id": False})
        self.room.action_reopen()
        self.assertEqual(self.room.state, "unassigned")

        self.room.write({"state": "closed", "assigned_to_id": self.env.user.id})
        self.room.action_reopen()
        self.assertEqual(self.room.state, "assigned")

    def test_assign_and_unassign_actions(self):
        self.room.write({"assigned_to_id": False, "state": "unassigned"})

        result_assign = self.room.action_assign_to_me()
        self.assertTrue(result_assign)
        self.assertEqual(self.room.assigned_to_id, self.env.user)
        self.assertEqual(self.room.state, "assigned")

        result_unassign = self.room.action_unassign()
        self.assertTrue(result_unassign)
        self.assertFalse(self.room.assigned_to_id)
        self.assertEqual(self.room.state, "unassigned")

    def test_partner_related_and_open_actions(self):
        partner = self.env["res.partner"].create({"name": "Room Partner"})
        self.room.partner_ids = [(4, partner.id)]

        create_partner_action = self.room.action_create_partner_from_chat()
        self.assertEqual(create_partner_action["res_model"], "res.partner")
        self.assertEqual(create_partner_action["view_mode"], "form")

        related = self.room.get_related_records()
        self.assertEqual(len(related), 1)
        self.assertEqual(related[0]["id"], partner.id)

        open_action = self.room.action_open_chatroom()
        self.assertEqual(open_action["type"], "ir.actions.client")
        self.assertEqual(open_action["tag"], "chatroom.app")
        self.assertEqual(open_action["params"]["room_id"], self.room.id)
