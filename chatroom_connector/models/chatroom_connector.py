import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class ChatroomConnector(models.Model):
    _name = "chatroom.connector"
    _description = "ChatRoom External Connector"

    name = fields.Char(required=True)
    connector_type = fields.Selection(
        [],
        required=True,
    )

    active = fields.Boolean(default=True)

    api_key = fields.Char()
    api_secret = fields.Char()
    app_name = fields.Char()
    webhook_url = fields.Char(compute="_compute_webhook_url", store=False)
    base_url = fields.Char()

    last_sync = fields.Datetime()
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("active", "Active"),
            ("error", "Error"),
        ],
        "Status",
        default="draft",
    )
    error_message = fields.Text("Last Error")

    messages_sent = fields.Integer(default=0)
    messages_received = fields.Integer(default=0)

    extra_config = fields.Json()

    @api.depends("connector_type")
    def _compute_webhook_url(self):
        base_url = self.env["ir.config_parameter"].sudo().get_param("web.base.url")
        for connector in self:
            if connector.connector_type:
                connector.webhook_url = (
                    f"{base_url}/chatroom/webhook/"
                    f"{connector.connector_type}/{connector.id}"
                )
            else:
                connector.webhook_url = False

    def action_test_connection(self):
        self.ensure_one()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "message": "Test connection not implemented for this connector type",
                "type": "warning",
                "sticky": False,
            },
        }

    def send_message(
        self, phone_number, message_text, message_type="text", media_url=None
    ):
        self.ensure_one()
        raise NotImplementedError(
            f"Send message not implemented for {self.connector_type}"
        )

    def process_incoming_webhook(self, data):
        self.ensure_one()
        raise NotImplementedError(
            f"Webhook processing not implemented for {self.connector_type}"
        )
