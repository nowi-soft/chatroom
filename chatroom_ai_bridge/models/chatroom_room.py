import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class ChatroomRoom(models.Model):
    _inherit = "chatroom.room"

    muk_ai_agent_id = fields.Many2one(
        "muk_ai.agent",
        string="AI Agent",
        help=(
            "AI agent that responds to incoming messages in this room. "
            "Leave empty to disable auto-response."
        ),
    )
    muk_ai_session_id = fields.Many2one(
        "muk_ai.session",
        string="AI Session",
        readonly=True,
        copy=False,
        help="Active muk_ai.session running for this room.",
    )

    def _ensure_ai_session(self):
        """Create (or return) the muk_ai.session that drives this room."""
        self.ensure_one()
        if self.muk_ai_session_id and self.muk_ai_session_id.state not in (
            "stopped",
            "error",
        ):
            return self.muk_ai_session_id
        bot = self.env.ref("chatroom_ai_bridge.user_chatroom_bot")
        session = (
            self.env["muk_ai.session"]
            .with_user(bot)
            .sudo()
            .create({
                "name": f"Chatroom Room #{self.id} — {self.name or ''}".strip(" —"),
                "agent_id": self.muk_ai_agent_id.id,
                "override_approval_mode": "off",
                "user_context": {"chatroom_room_id": self.id},
            })
        )
        self.sudo().muk_ai_session_id = session.id
        return session
