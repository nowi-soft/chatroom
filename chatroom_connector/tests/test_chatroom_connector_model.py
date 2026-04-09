from odoo.tests.common import TransactionCase


class TestChatroomConnectorModel(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["ir.config_parameter"].sudo().set_param("web.base.url", "http://test")
        cls.connector = cls.env["chatroom.connector"].new({"name": "Test Connector"})
        cls.connector_type_options = cls.env["chatroom.connector"]._fields[
            "connector_type"
        ].selection

    def test_compute_webhook_url(self):
        if not self.connector_type_options:
            self.connector._compute_webhook_url()
            self.assertFalse(self.connector.webhook_url)
            return

        connector_type = self.connector_type_options[0][0]
        connector = self.env["chatroom.connector"].create(
            {
                "name": "Test Connector",
                "connector_type": connector_type,
            }
        )
        self.assertEqual(
            connector.webhook_url,
            f"http://test/chatroom/webhook/{connector_type}/{connector.id}",
        )

    def test_action_test_connection_contract(self):
        action = self.connector.action_test_connection()

        self.assertEqual(action["type"], "ir.actions.client")
        self.assertEqual(action["tag"], "display_notification")
        self.assertEqual(action["params"]["type"], "warning")

    def test_send_message_not_implemented(self):
        with self.assertRaises(NotImplementedError):
            self.connector.send_message(
                phone_number="+5491111111111",
                message_text="hello",
            )
