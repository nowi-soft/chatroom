import json
import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class ChatroomWebhook(http.Controller):
    @http.route(
        "/chatroom/webhook/<string:connector_type>/<int:connector_id>",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def receive_webhook(self, connector_type, connector_id, **kwargs):
        try:
            connector = request.env["chatroom.connector"].sudo().browse(connector_id)

            if not connector.exists():
                return json.dumps({"status": "error", "message": "Connector not found"})

            if connector.connector_type != connector_type:
                return json.dumps(
                    {"status": "error", "message": "Connector type mismatch"}
                )

            if not connector.active:
                return json.dumps(
                    {"status": "error", "message": "Connector is inactive"}
                )

            data = (
                json.loads(request.httprequest.data.decode("utf-8"))
                if request.httprequest.data
                else {}
            )

            message = connector.process_incoming_webhook(data)

            return json.dumps(
                {"status": "success", "message_id": message.id if message else None}
            )

        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})

    @http.route(
        "/chatroom/webhook/<string:connector_type>/<int:connector_id>",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
    )
    def webhook_verification(self, connector_type, connector_id, **kwargs):
        challenge = kwargs.get("hub.challenge")
        verify_token = kwargs.get("hub.verify_token")

        if challenge and verify_token:
            connector = request.env["chatroom.connector"].sudo().browse(connector_id)
            if connector.exists() and connector.api_secret == verify_token:
                return challenge

        return "Webhook endpoint active"
