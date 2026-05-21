import logging

from odoo import models

_logger = logging.getLogger(__name__)


class MukAISession(models.Model):
    _inherit = "muk_ai.session"

    def _append_event(self, entry):
        """When an assistant text event fires on a session tied to a chatroom.room,
        materialize an outgoing chatroom.message so the connector can deliver it."""
        result = super()._append_event(entry)
        try:
            kind = (entry or {}).get("kind")
            content = (entry or {}).get("content")
            if kind == "text" and content:
                room = self._resolve_chatroom_room()
                if room:
                    self.env["chatroom.message"].sudo().create({
                        "room_id": room.id,
                        "body": content,
                        "direction": "outgoing",
                        "message_type": "text",
                    })
        except Exception as e:
            _logger.exception("Failed to emit outgoing chatroom message: %s", e)
        return result

    def _resolve_chatroom_room(self):
        """Find the chatroom.room linked to this session, if any."""
        self.ensure_one()
        ctx = self.user_context or {}
        room_id = ctx.get("chatroom_room_id") if isinstance(ctx, dict) else None
        if room_id:
            room = self.env["chatroom.room"].sudo().browse(room_id)
            if room.exists():
                return room
        return self.env["chatroom.room"].sudo().search(
            [("muk_ai_session_id", "=", self.id)], limit=1
        )
