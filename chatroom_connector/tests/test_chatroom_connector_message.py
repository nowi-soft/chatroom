from types import SimpleNamespace
from unittest.mock import patch

from odoo.tests.common import TransactionCase


class TestChatroomConnectorMessage(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.room = cls.env["chatroom.room"].create({"name": "Connector Room"})

    def test_create_does_not_duplicate_message_notification(self):
        message_model_class = type(self.env["chatroom.message"])

        with patch.object(
            message_model_class,
            "_notify_message_created",
            autospec=True,
        ) as notify_message_created:
            self.env["chatroom.message"].create(
                {
                    "room_id": self.room.id,
                    "body": "Outgoing",
                    "direction": "outgoing",
                }
            )

        self.assertEqual(notify_message_created.call_count, 1)

    def test_connector_send_is_skipped_without_connector(self):
        message_model_class = type(self.env["chatroom.message"])

        with patch.object(
            message_model_class,
            "_send_through_connector",
            autospec=True,
        ) as send_through_connector:
            self.env["chatroom.message"].create(
                {
                    "room_id": self.room.id,
                    "body": "No connector",
                    "direction": "outgoing",
                }
            )

        send_through_connector.assert_not_called()

    def test_send_through_connector_sets_external_id_on_success(self):
        connector = SimpleNamespace(
            active=True,
            send_message=lambda **kwargs: {
                "success": True,
                "response": {"messageId": "ext-123"},
            },
        )
        room = SimpleNamespace(connector_id=connector, external_id="+549111111111")

        class FakeMessage:
            def __init__(self):
                self.room_id = room
                self.message_type = "text"
                self.file_url = None
                self.media_url = None
                self.filename = None
                self.mime_type = None
                self.attachment_id = None
                self.external_id = False
                self.id = 99

            def _get_message_text_with_author(self):
                return "hello"

        fake_message = FakeMessage()
        self.env["chatroom.message"]._send_through_connector(fake_message)
        self.assertEqual(fake_message.external_id, "ext-123")

    def test_send_through_connector_skips_inactive_or_missing_phone(self):
        inactive_connector = SimpleNamespace(
            active=False, send_message=lambda **kwargs: {}
        )
        inactive_room = SimpleNamespace(
            connector_id=inactive_connector, external_id="+549"
        )
        missing_phone_room = SimpleNamespace(
            connector_id=SimpleNamespace(active=True, send_message=lambda **kwargs: {}),
            external_id=False,
        )

        class FakeMessage:
            def __init__(self, room):
                self.room_id = room
                self.message_type = "text"
                self.file_url = None
                self.media_url = None
                self.filename = None
                self.mime_type = None
                self.attachment_id = None
                self.external_id = False
                self.id = 42

            def _get_message_text_with_author(self):
                return "hello"

        msg_inactive = FakeMessage(inactive_room)
        self.env["chatroom.message"]._send_through_connector(msg_inactive)
        self.assertFalse(msg_inactive.external_id)

        msg_missing_phone = FakeMessage(missing_phone_room)
        self.env["chatroom.message"]._send_through_connector(msg_missing_phone)
        self.assertFalse(msg_missing_phone.external_id)
