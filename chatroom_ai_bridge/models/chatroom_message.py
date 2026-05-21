import logging

from odoo import api, models

_logger = logging.getLogger(__name__)


class ChatroomMessage(models.Model):
    _inherit = "chatroom.message"

    @api.model_create_multi
    def create(self, vals_list):
        messages = super().create(vals_list)
        for message in messages:
            message._maybe_dispatch_to_ai()
        return messages

    def _maybe_dispatch_to_ai(self):
        """If this is an incoming message on a room with an AI agent assigned,
        forward it to the room's muk_ai.session."""
        self.ensure_one()
        if self.direction != "incoming":
            return
        room = self.room_id
        if not room or not room.muk_ai_agent_id:
            return
        try:
            session = room._ensure_ai_session()
            bot = self.env.ref("chatroom_ai_bridge.user_chatroom_bot")
            content = self.body or ""
            session_user = session.with_user(bot).sudo()
            if session.state == "new":
                session_user.start(content)
            else:
                session_user.send_message(content)
        except Exception as e:
            _logger.exception(
                "Failed to dispatch chatroom.message id=%s to AI: %s", self.id, e
            )
