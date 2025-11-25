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
                },
            }

    def send_message(
        self, phone_number, message_text, message_type="text", media_url=None
    ):
        self.ensure_one()
        if self.connector_type == "evolution":
            return self._send_evolution_message(
                phone_number, message_text, message_type, media_url
            )
        return super().send_message(phone_number, message_text, message_type, media_url)

    def _send_evolution_message(
        self, phone_number, message_text, message_type="text", media_url=None
    ):
        try:
            base_url = self.base_url.rstrip("/")
            headers = {"apikey": self.api_key, "Content-Type": "application/json"}

            if "@" not in phone_number:
                phone_number = f"{phone_number}@s.whatsapp.net"

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
            elif message_type == "document":
                url = f"{base_url}/message/sendMedia/{self.app_name}"
                data = {
                    "number": phone_number,
                    "mediatype": "document",
                    "media": media_url,
                    "fileName": message_text or "document",
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

            if "conversation" in message_info:
                message_text = message_info["conversation"]
                message_type = "text"
            elif "extendedTextMessage" in message_info:
                message_text = message_info["extendedTextMessage"].get("text", "")
                message_type = "text"
            elif "imageMessage" in message_info:
                message_text = message_info["imageMessage"].get("caption", "Image")
                media_url = message_info["imageMessage"].get("url", "")
                message_type = "image"
            elif "documentMessage" in message_info:
                message_text = message_info["documentMessage"].get(
                    "fileName", "Document"
                )
                media_url = message_info["documentMessage"].get("url", "")
                message_type = "document"
            elif "audioMessage" in message_info:
                message_text = "Voice message"
                media_url = message_info["audioMessage"].get("url", "")
                message_type = "audio"
            elif "videoMessage" in message_info:
                message_text = message_info["videoMessage"].get("caption", "Video")
                media_url = message_info["videoMessage"].get("url", "")
                message_type = "video"
            else:
                message_text = "Unsupported message type"

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

            message = self.env["chatroom.message"].create(
                {
                    "room_id": room.id,
                    "body": message_text,
                    "direction": "incoming",
                    "author_name": sender_name,
                    "message_type": message_type,
                    "external_id": key.get("id", ""),
                    "media_url": media_url,
                }
            )

            self.messages_received += 1
            self.last_sync = fields.Datetime.now()

            self.env["bus.bus"]._sendone(
                room,
                "chatroom/room_updated",
                {
                    "room": {
                        "id": room.id,
                        "name": room.name,
                        "state": room.state,
                        "last_message": message_text[:50],
                    }
                },
            )

            return message

        except Exception as e:
            _logger.error(f"Error processing webhook: {str(e)}")
            self.error_message = str(e)
            raise
