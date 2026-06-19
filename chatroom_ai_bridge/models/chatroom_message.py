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

    def _chatroom_bot_user(self):
        return self.env.ref(
            "chatroom_ai_bridge.user_chatroom_bot", raise_if_not_found=False
        )

    def _ai_bot_display_name(self):
        return (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("chatroom_ai_bridge.bot_display_name", "")
            or ""
        ).strip()

    @api.depends("user_id", "direction")
    def _compute_author_name(self):
        """Bot messages use the configurable bot name (empty -> no name)."""
        bot = self._chatroom_bot_user()
        bot_msgs = self.filtered(
            lambda m: m.direction == "outgoing" and bot and m.user_id.id == bot.id
        )
        name = self._ai_bot_display_name()
        for msg in bot_msgs:
            msg.author_name = name or False
        super(ChatroomMessage, self - bot_msgs)._compute_author_name()

    def _get_message_text_with_author(self):
        """For outbound bot messages, append the configurable bot name (only if
        Show Author Name is on and a name is set); otherwise nothing."""
        self.ensure_one()
        bot = self._chatroom_bot_user()
        if bot and self.user_id.id == bot.id:
            show = (
                self.env["ir.config_parameter"]
                .sudo()
                .get_param("chatroom.show_author_name", default="True")
            ) == "True"
            name = self._ai_bot_display_name()
            if show and name:
                return f"{self.body}\n\n- {name}"
            return self.body
        return super()._get_message_text_with_author()

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
