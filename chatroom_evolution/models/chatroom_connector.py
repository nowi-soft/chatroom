import logging

import requests

from odoo import api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class ChatroomConnector(models.Model):
    _inherit = "chatroom.connector"

    connector_type = fields.Selection(
        selection_add=[("evolution", "Evolution API")],
        ondelete={"evolution": "cascade"},
    )

    @api.constrains("connector_type", "base_url", "api_key", "app_name")
    def _check_evolution_config(self):
        for connector in self:
            if connector.connector_type == "evolution":
                if not connector.base_url:
                    raise ValidationError(
                        self.env._("Base URL is required for Evolution API")
                    )
                if not connector.base_url.startswith(("http://", "https://")):
                    raise ValidationError(
                        self.env._("Base URL must start with http:// or https://")
                    )
                if not connector.api_key:
                    raise ValidationError(
                        self.env._("API Key is required for Evolution API")
                    )
                if not connector.app_name:
                    raise ValidationError(
                        self.env._("Instance Name is required for Evolution API")
                    )

    def action_test_connection(self):
        self.ensure_one()
        if self.connector_type == "evolution":
            return self._test_evolution_connection()
        return super().action_test_connection()

    def _test_evolution_connection(self):
        try:
            base_url = self.base_url.rstrip("/")
            url = f"{base_url}/instance/fetchInstances"
            headers = {"apikey": self.api_key, "Content-Type": "application/json"}

            response = requests.get(url, headers=headers, timeout=10)

            if response.status_code == 200:
                instances = response.json()
                instance_found = any(i.get("name") == self.app_name for i in instances)

                if instance_found:
                    self.state = "active"
                    self.error_message = False
                    return {
                        "type": "ir.actions.client",
                        "tag": "display_notification",
                        "params": {
                            "message": "Connection successful!",
                            "type": "success",
                            "sticky": False,
                            "next": {"type": "ir.actions.act_window_close"},
                        },
                    }
                else:
                    self.state = "error"
                    self.error_message = f"Instance {self.app_name} not found"
                    return {
                        "type": "ir.actions.client",
                        "tag": "display_notification",
                        "params": {
                            "message": f"Instance {self.app_name} not found",
                            "type": "danger",
                            "sticky": True,
                            "next": {"type": "ir.actions.act_window_close"},
                        },
                    }
            else:
                self.state = "error"
                self.error_message = f"HTTP {response.status_code}: {response.text}"
                return {
                    "type": "ir.actions.client",
                    "tag": "display_notification",
                    "params": {
                        "message": f"Connection failed: {response.text}",
                        "type": "danger",
                        "sticky": True,
                        "next": {"type": "ir.actions.act_window_close"},
                    },
                }
        except Exception as e:
            self.state = "error"
            self.error_message = str(e)
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "message": f"Connection error: {str(e)}",
                    "type": "danger",
                    "sticky": True,
                    "next": {"type": "ir.actions.act_window_close"},
                },
            }

    def send_message(
        self,
        phone_number,
        message_text,
        message_type="text",
        media_url=None,
        filename=None,
        mime_type=None,
        attachment=None,
    ):
        self.ensure_one()
        if self.connector_type == "evolution":
            return self._send_evolution_message(
                phone_number,
                message_text,
                message_type,
                media_url,
                filename,
                mime_type,
                attachment,
            )
        return super().send_message(
            phone_number,
            message_text,
            message_type,
            media_url,
            filename,
            mime_type,
            attachment,
        )

    def _send_evolution_message(
        self,
        phone_number,
        message_text,
        message_type="text",
        media_url=None,
        filename=None,
        mime_type=None,
        attachment=None,
    ):
        try:
            base_url = self.base_url.rstrip("/")
            headers = {"apikey": self.api_key, "Content-Type": "application/json"}

            if "@" not in phone_number:
                phone_number = f"{phone_number}@s.whatsapp.net"

            if not media_url and attachment:
                base_web_url = (
                    self.env["ir.config_parameter"].sudo().get_param("web.base.url")
                )
                media_url = f"{base_web_url}/web/content/{attachment.id}?download=true"

            if message_type == "text":
                url = f"{base_url}/message/sendText/{self.app_name}"
                data = {"number": phone_number, "text": message_text}
            elif message_type == "image":
                url = f"{base_url}/message/sendMedia/{self.app_name}"
                data = {
                    "number": phone_number,
                    "mediatype": "image",
                    "media": media_url,
                    "caption": message_text or "",
                }
            elif message_type == "file":
                url = f"{base_url}/message/sendMedia/{self.app_name}"
                data = {
                    "number": phone_number,
                    "mediatype": "document",
                    "media": media_url,
                    "fileName": filename or message_text or "document",
                }
            elif message_type == "audio":
                url = f"{base_url}/message/sendMedia/{self.app_name}"
                data = {
                    "number": phone_number,
                    "mediatype": "audio",
                    "media": media_url,
                }
            elif message_type == "video":
                url = f"{base_url}/message/sendMedia/{self.app_name}"
                data = {
                    "number": phone_number,
                    "mediatype": "video",
                    "media": media_url,
                    "caption": message_text or "",
                }
            else:
                url = f"{base_url}/message/sendText/{self.app_name}"
                data = {"number": phone_number, "text": message_text}

            response = requests.post(url, headers=headers, json=data, timeout=30)

            if response.status_code == 201:
                self.messages_sent += 1
                _logger.info(f"Message sent successfully to {phone_number}")
                return {"success": True, "response": response.json()}
            else:
                _logger.error(f"Failed to send message: {response.text}")
                return {"success": False, "error": response.text}

        except Exception as e:
            _logger.error(f"Error sending message: {str(e)}")
            return {"success": False, "error": str(e)}

    def process_incoming_webhook(self, data):
        self.ensure_one()
        if self.connector_type == "evolution":
            return self._process_evolution_webhook(data)
        return super().process_incoming_webhook(data)

    def _process_evolution_webhook(self, data):
        try:
            event = data.get("event")

            if event not in ["messages.upsert", "messages.update"]:
                return None

            message_data = data.get("data", {})

            if message_data.get("key", {}).get("fromMe"):
                return None

            message_info = message_data.get("message", {})
            key = message_data.get("key", {})

            phone_number = key.get("remoteJid", "").replace("@s.whatsapp.net", "")

            sender_name = message_data.get("pushName", phone_number)

            message_text = ""
            media_url = None
            message_type = "text"
            filename = None
            mime_type = None

            if "conversation" in message_info:
                message_text = message_info["conversation"]
                message_type = "text"
            elif "extendedTextMessage" in message_info:
                message_text = message_info["extendedTextMessage"].get("text", "")
                message_type = "text"
            elif "imageMessage" in message_info:
                img_msg = message_info["imageMessage"]
                message_text = img_msg.get("caption", "")
                media_url = img_msg.get("url", "")
                message_type = "image"
                mime_type = img_msg.get("mimetype", "image/jpeg")
                filename = f"image_{key.get('id', 'unknown')}.jpg"
            elif "documentMessage" in message_info:
                doc_msg = message_info["documentMessage"]
                filename = doc_msg.get("fileName", "Document")
                message_text = doc_msg.get("caption", "")
                media_url = doc_msg.get("url", "")
                message_type = "file"
                mime_type = doc_msg.get("mimetype", "application/octet-stream")
            elif "audioMessage" in message_info:
                audio_msg = message_info["audioMessage"]
                message_text = self.env._("Voice message")
                media_url = audio_msg.get("url", "")
                message_type = "audio"
                mime_type = audio_msg.get("mimetype", "audio/ogg")
                filename = f"audio_{key.get('id', 'unknown')}.ogg"
            else:
                message_text = self.env._("Unsupported message type")

            room = self.env["chatroom.room"].search(
                [("connector_id", "=", self.id), ("external_id", "=", phone_number)],
                limit=1,
            )

            if not room:
                room = self.env["chatroom.room"].create(
                    {
                        "name": sender_name or phone_number,
                        "connector_id": self.id,
                        "external_id": phone_number,
                        "state": "unassigned",
                    }
                )

            message_vals = {
                "room_id": room.id,
                "body": message_text or self.env._("Media message"),
                "direction": "incoming",
                "author_name": sender_name,
                "message_type": message_type,
                "external_id": key.get("id", ""),
                "file_url": media_url,
                "filename": filename,
                "mime_type": mime_type,
            }

            if message_type == "audio" and room.ai_enabled:
                message_vals["is_transcribing"] = True
                message_vals["body"] = ""

            message = self.env["chatroom.message"].create(message_vals)

            self.messages_received += 1
            self.last_sync = fields.Datetime.now()

            return message

        except Exception as e:
            _logger.error(f"Error processing webhook: {str(e)}")
            self.error_message = str(e)
            raise
