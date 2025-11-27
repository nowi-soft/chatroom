import base64
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
                            "next": {"type": "ir.actions.act_window_close"},
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
                        "message": (f"Connection failed: {response.text}"),
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
                    "message": (f"Connection error: {str(e)}"),
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
        if self.connector_type == "telegram":
            return self._send_telegram_message(
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

    def _send_telegram_message(
        self,
        chat_id,
        message_text,
        message_type="text",
        media_url=None,
        filename=None,
        mime_type=None,
        attachment=None,
    ):
        try:
            base_url = f"https://api.telegram.org/bot{self.api_key}"

            if message_type == "text":
                url = f"{base_url}/sendMessage"
                data = {"chat_id": chat_id, "text": message_text}
                response = requests.post(url, json=data, timeout=30)
            else:
                file_data = None
                if attachment and attachment.datas:
                    file_data = base64.b64decode(attachment.datas)
                    file_name = attachment.name
                elif media_url:
                    file_name = filename or "file"
                else:
                    url = f"{base_url}/sendMessage"
                    data = {"chat_id": chat_id, "text": message_text}
                    response = requests.post(url, json=data, timeout=30)
                    return self._process_telegram_response(response)

                if message_type == "image":
                    url = f"{base_url}/sendPhoto"
                    field_name = "photo"
                elif message_type == "audio":
                    if mime_type and "ogg" in mime_type:
                        url = f"{base_url}/sendVoice"
                        field_name = "voice"
                    else:
                        url = f"{base_url}/sendAudio"
                        field_name = "audio"
                elif message_type == "video":
                    url = f"{base_url}/sendVideo"
                    field_name = "video"
                else:
                    url = f"{base_url}/sendDocument"
                    field_name = "document"

                data = {"chat_id": chat_id}
                if message_text and message_text != file_name:
                    data["caption"] = message_text

                if file_data:
                    files = {
                        field_name: (
                            file_name,
                            file_data,
                            mime_type or "application/octet-stream",
                        )
                    }
                    response = requests.post(url, data=data, files=files, timeout=30)
                else:
                    data[field_name] = media_url
                    response = requests.post(url, json=data, timeout=30)

            return self._process_telegram_response(response)

        except Exception as e:
            return {"success": False, "error": str(e)}

    def _process_telegram_response(self, response):
        if response.status_code == 200:
            result = response.json()
            if result.get("ok"):
                self.sudo().messages_sent += 1
                return {"success": True, "response": result["result"]}
            else:
                return {"success": False, "error": result.get("description")}
        else:
            return {"success": False, "error": response.text}

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
            filename = None
            mime_type = None

            if "text" in message_data:
                message_text = message_data["text"]
                message_type = "text"
            elif "photo" in message_data:
                photos = message_data["photo"]
                largest_photo = max(photos, key=lambda p: p.get("file_size", 0))
                file_id = largest_photo.get("file_id")
                media_url = self._get_telegram_file_url(file_id)
                message_text = message_data.get("caption", "")
                message_type = "image"
                mime_type = "image/jpeg"
                filename = f"photo_{message_data.get('message_id')}.jpg"
            elif "document" in message_data:
                doc = message_data["document"]
                file_id = doc.get("file_id")
                media_url = self._get_telegram_file_url(file_id)
                filename = doc.get("file_name", "Document")
                message_text = message_data.get("caption", "")
                message_type = "file"
                mime_type = doc.get("mime_type", "application/octet-stream")
            elif "audio" in message_data:
                audio = message_data["audio"]
                file_id = audio.get("file_id")
                media_url = self._get_telegram_file_url(file_id)
                message_text = message_data.get("caption", "")
                message_type = "audio"
                mime_type = audio.get("mime_type", "audio/mpeg")
                filename = audio.get(
                    "file_name", f"audio_{message_data.get('message_id')}.mp3"
                )
            elif "voice" in message_data:
                voice = message_data["voice"]
                file_id = voice.get("file_id")
                media_url = self._get_telegram_file_url(file_id)
                caption = message_data.get("caption", "")
                message_text = caption if caption else self.env._("🎤 Voice message")
                message_type = "audio"
                mime_type = voice.get("mime_type", "audio/ogg")
                filename = f"voice_{message_data.get('message_id')}.ogg"
            else:
                message_text = self.env._("Unsupported message type")

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

            attachment_id = False
            if media_url and message_type in ["audio", "image", "file"]:
                try:
                    file_response = requests.get(media_url, timeout=30)
                    if file_response.status_code == 200:
                        file_content = file_response.content
                        file_b64 = base64.b64encode(file_content)
                        attachment = self.env["ir.attachment"].create(
                            {
                                "name": filename or "file",
                                "datas": file_b64,
                                "mimetype": mime_type or "application/octet-stream",
                                "res_model": "chatroom.message",
                                "res_id": 0,
                            }
                        )
                        attachment_id = attachment.id
                except Exception as e:
                    _logger.warning(f"Failed to download media from Telegram: {e}")

            message_vals = {
                "room_id": room.id,
                "body": message_text or "",
                "direction": "incoming",
                "author_name": sender_name,
                "message_type": message_type,
                "external_id": str(message_data.get("message_id", "")),
                "attachment_id": attachment_id,
                "filename": filename,
                "mime_type": mime_type,
            }

            if message_type == "audio" and room.ai_enabled:
                message_vals["is_transcribing"] = True
                message_vals["body"] = ""

            message = self.env["chatroom.message"].create(message_vals)

            self.sudo().write(
                {
                    "messages_received": self.messages_received + 1,
                    "last_sync": fields.Datetime.now(),
                }
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
