import base64

from odoo.tests.common import TransactionCase


class TestChatroomMessage(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.room = cls.env["chatroom.room"].create({"name": "Test Customer"})

    def test_incoming_message_reopens_closed_room(self):
        self.room.write({"state": "closed", "assigned_to_id": self.env.user.id})

        self.env["chatroom.message"].create(
            {
                "room_id": self.room.id,
                "body": "Hello from customer",
                "direction": "incoming",
            }
        )

        self.assertEqual(self.room.state, "unassigned")
        self.assertFalse(self.room.assigned_to_id)

    def test_get_message_text_with_author_respects_config(self):
        message = self.env["chatroom.message"].create(
            {
                "room_id": self.room.id,
                "body": "Message body",
                "direction": "outgoing",
                "user_id": self.env.user.id,
            }
        )

        self.env["ir.config_parameter"].sudo().set_param(
            "chatroom.show_author_name", "True"
        )
        with_author = message._get_message_text_with_author()
        self.assertIn("Message body", with_author)
        self.assertIn(self.env.user.name, with_author)

        self.env["ir.config_parameter"].sudo().set_param(
            "chatroom.show_author_name", "False"
        )
        without_author = message._get_message_text_with_author()
        self.assertEqual(without_author, "Message body")

    def test_compute_file_url_for_file_message(self):
        attachment = self.env["ir.attachment"].create(
            {
                "name": "sample.txt",
                "datas": base64.b64encode(b"hello").decode("ascii"),
                "mimetype": "text/plain",
                "res_model": "chatroom.message",
                "res_id": 0,
            }
        )

        message = self.env["chatroom.message"].create(
            {
                "room_id": self.room.id,
                "body": "Attachment",
                "message_type": "file",
                "attachment_id": attachment.id,
            }
        )

        self.assertEqual(message.file_url, f"/chatroom/file/{attachment.id}")

    def test_compute_file_url_for_inline_media(self):
        attachment = self.env["ir.attachment"].create(
            {
                "name": "image.png",
                "datas": base64.b64encode(b"png-bytes").decode("ascii"),
                "mimetype": "image/png",
                "res_model": "chatroom.message",
                "res_id": 0,
            }
        )

        message = self.env["chatroom.message"].create(
            {
                "room_id": self.room.id,
                "body": "Image",
                "message_type": "image",
                "mime_type": "image/png",
                "attachment_id": attachment.id,
            }
        )

        self.assertTrue(message.file_url.startswith("data:image/png;base64,"))
