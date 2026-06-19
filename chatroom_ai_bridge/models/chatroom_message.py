import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class ChatroomMessage(models.Model):
    _inherit = "chatroom.message"

    ai_dispatched = fields.Boolean(
        string="Dispatched to AI",
        default=False,
        copy=False,
        help="Set once this incoming message has been forwarded to the AI agent.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        messages = super().create(vals_list)
        for message in messages:
            message._maybe_dispatch_to_ai()
        return messages

    def _maybe_dispatch_to_ai(self):
        """If this is an incoming message on a room with an active AI agent,
        forward it to the room's muk_ai.session — immediately, or after the
        configured debounce delay (resetting the timer on each new message)."""
        self.ensure_one()
        if self.direction != "incoming":
            return
        room = self.room_id
        if not room or not room.muk_ai_agent_id or not room.ai_active:
            return
        if room._ai_response_delay() > 0:
            # Debounced: leave ai_dispatched=False; the cron gathers the burst.
            room._schedule_ai_dispatch(room._ai_response_delay())
            return
        try:
            self.ai_dispatched = True
            room._dispatch_to_ai(self.body or "")
        except Exception as e:
            _logger.exception(
                "Failed to dispatch chatroom.message id=%s to AI: %s", self.id, e
            )
