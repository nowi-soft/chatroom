import logging

import requests

from odoo import api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class ChatroomConnector(models.Model):
    _inherit = "chatroom.connector"

    connector_type = fields.Selection(
        selection_add=[("telegram", "Telegram Bot")], ondelete={"telegram": "cascade"}
    )

    @api.constrains("connector_type", "api_key")
    def _check_telegram_config(self):
        for connector in self:
            if connector.connector_type == "telegram":
                if not connector.api_key:
                    raise ValidationError(
                        self.env._("Bot Token (API Key) is required for Telegram Bot")
                    )
                if not connector.api_key.count(":") == 1:
                    raise ValidationError(
                        self.env._(
                            "Invalid Bot Token format. Should be like: "
                            "123456789:ABC-DEF1234"
                        )
                    )

    def action_test_connection(self):
        self.ensure_one()
        if self.connector_type == "telegram":
            return self._test_telegram_connection()
        return super().action_test_connection()

    def _test_telegram_connection(self):
        try:
            url = f"https://api.telegram.org/bot{self.api_key}/getMe"
            response = requests.get(url, timeout=10)

            if response.status_code == 200:
                result = response.json()
                if result.get("ok"):
                    bot_info = result.get("result", {})
                    self.state = "active"
                    self.error_message = False
                    return {
                        "type": "ir.actions.client",
                        "tag": "display_notification",
                        "params": {
                            "message": (
                                "Connection successful! "
                                f"Bot: @{bot_info.get('username')}"
                            ),
                            "type": "success",
                            "sticky": False,
                        },
                    }
                else:
                    self.state = "error"
                    self.error_message = result.get("description", "Unknown error")
                    return {
                        "type": "ir.actions.client",
                        "tag": "display_notification",
                        "params": {
                            "message": (
                                f"Connection failed: {result.get('description')}"
                            ),
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
                        "message": (f"Connection failed: {response.text}"),
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
                    "message": (f"Connection error: {str(e)}"),
                    "type": "danger",
                    "sticky": True,
                },
            }

    def send_message(
        self, phone_number, message_text, message_type="text", media_url=None
    ):
        self.ensure_one()
        if self.connector_type == "telegram":
            return self._send_telegram_message(
                phone_number, message_text, message_type, media_url
            )
        return super().send_message(phone_number, message_text, message_type, media_url)

    def _send_telegram_message(
        self, chat_id, message_text, message_type="text", media_url=None
    ):
        try:
            base_url = f"https://api.telegram.org/bot{self.api_key}"

            if message_type == "text":
                url = f"{base_url}/sendMessage"
                data = {"chat_id": chat_id, "text": message_text}
            elif message_type == "image":
                url = f"{base_url}/sendPhoto"
                data = {
                    "chat_id": chat_id,
                    "photo": media_url,
                    "caption": message_text or "",
                }
            elif message_type == "document":
                url = f"{base_url}/sendDocument"
                data = {
                    "chat_id": chat_id,
                    "document": media_url,
                    "caption": message_text or "",
                }
            elif message_type == "audio":
                url = f"{base_url}/sendAudio"
                data = {
                    "chat_id": chat_id,
                    "audio": media_url,
                    "caption": message_text or "",
                }
            elif message_type == "video":
                url = f"{base_url}/sendVideo"
                data = {
                    "chat_id": chat_id,
                    "video": media_url,
                    "caption": message_text or "",
                }
            else:
                url = f"{base_url}/sendMessage"
                data = {"chat_id": chat_id, "text": message_text}

            response = requests.post(url, json=data, timeout=30)

            if response.status_code == 200:
                result = response.json()
                if result.get("ok"):
                    self.sudo().messages_sent += 1
                    return {"success": True, "response": result["result"]}
                else:
                    return {"success": False, "error": result.get("description")}
            else:
                return {"success": False, "error": response.text}

        except Exception as e:
            return {"success": False, "error": str(e)}

    def process_incoming_webhook(self, data):
        self.ensure_one()
        if self.connector_type == "telegram":
            return self._process_telegram_webhook(data)
        return super().process_incoming_webhook(data)

    def _process_telegram_webhook(self, data):
        try:
            message_data = data.get("message", {})

            if not message_data:
                return None

            chat = message_data.get("chat", {})
            from_user = message_data.get("from", {})

            chat_id = str(chat.get("id", ""))
            sender_name = from_user.get("first_name", "")
            if from_user.get("last_name"):
                sender_name += f" {from_user['last_name']}"
            if from_user.get("username"):
                sender_name += f" (@{from_user['username']})"

            message_text = ""
            media_url = None
            message_type = "text"

            if "text" in message_data:
                message_text = message_data["text"]
                message_type = "text"
            elif "photo" in message_data:
                photos = message_data["photo"]
                largest_photo = max(photos, key=lambda p: p.get("file_size", 0))
                file_id = largest_photo.get("file_id")
                media_url = self._get_telegram_file_url(file_id)
                message_text = message_data.get("caption", "Photo")
                message_type = "image"
            elif "document" in message_data:
                file_id = message_data["document"].get("file_id")
                media_url = self._get_telegram_file_url(file_id)
                message_text = message_data.get("caption") or message_data[
                    "document"
                ].get("file_name", "Document")
                message_type = "document"
            elif "audio" in message_data:
                file_id = message_data["audio"].get("file_id")
                media_url = self._get_telegram_file_url(file_id)
                message_text = message_data.get("caption", "Audio")
                message_type = "audio"
            elif "video" in message_data:
                file_id = message_data["video"].get("file_id")
                media_url = self._get_telegram_file_url(file_id)
                message_text = message_data.get("caption", "Video")
                message_type = "video"
            elif "voice" in message_data:
                file_id = message_data["voice"].get("file_id")
                media_url = self._get_telegram_file_url(file_id)
                message_text = "Voice message"
                message_type = "audio"
            else:
                message_text = "Unsupported message type"

            room = self.env["chatroom.room"].search(
                [("connector_id", "=", self.id), ("external_id", "=", chat_id)], limit=1
            )

            if not room:
                room_name = chat.get("title") or sender_name or chat_id
                room = self.env["chatroom.room"].create(
                    {
                        "name": room_name,
                        "connector_id": self.id,
                        "external_id": chat_id,
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
                    "external_id": str(message_data.get("message_id", "")),
                    "media_url": media_url,
                }
            )

            self.sudo().write(
                {
                    "messages_received": self.messages_received + 1,
                    "last_sync": fields.Datetime.now(),
                }
            )

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
            self.error_message = str(e)
            raise

    def _get_telegram_file_url(self, file_id):
        try:
            url = f"https://api.telegram.org/bot{self.api_key}/getFile"
            response = requests.get(url, params={"file_id": file_id}, timeout=10)
            if response.status_code == 200:
                result = response.json()
                if result.get("ok"):
                    file_path = result["result"]["file_path"]
                    return (
                        f"https://api.telegram.org/file/bot{self.api_key}/{file_path}"
                    )
        except Exception as e:
            _logger.warning(f"Failed to get Telegram file URL: {e}")
        return None
