import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class ChatroomMessage(models.Model):
    _inherit = "chatroom.message"

    external_id = fields.Char(
        string="External Message ID", help="Message ID from external platform"
    )
    media_url = fields.Char(
        string="Media URL", help="URL for images, documents, audio, video, etc."
    )

    @api.model_create_multi
    def create(self, vals_list):
        messages = super().create(vals_list)

        for message in messages:
            if (
                message.direction == "outgoing"
                and message.room_id.connector_id
                and not message.is_internal
            ):
                self._send_through_connector(message)

            message._notify_message_created()

        return messages

    def _send_through_connector(self, message):
        try:
            connector = message.room_id.connector_id
            if not connector or not connector.active:
                return

            phone_number = message.room_id.external_id
            if not phone_number:
                return

            message_text = message._get_message_text_with_author()

            result = connector.send_message(
                phone_number=phone_number,
                message_text=message_text,
                message_type=message.message_type or "text",
                media_url=message.file_url or message.media_url,
                filename=message.filename,
                mime_type=message.mime_type,
                attachment=message.attachment_id,
            )

            if result.get("success"):
                if result.get("response", {}).get("messageId"):
                    message.external_id = result["response"]["messageId"]

        except Exception as e:
            _logger.warning(
                f"Failed to send message {message.id} through connector: {e}"
            )
