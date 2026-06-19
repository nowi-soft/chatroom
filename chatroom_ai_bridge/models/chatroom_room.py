import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

_TERMINAL_STATES = {"stopped", "error"}


class ChatroomRoom(models.Model):
    _inherit = "chatroom.room"

    muk_ai_agent_id = fields.Many2one(
        "muk_ai.agent",
        string="AI Agent",
        help="AI agent that responds to incoming messages. Leave empty to disable.",
    )
    muk_ai_session_id = fields.Many2one(
        "muk_ai.session",
        string="AI Session",
        readonly=True,
        copy=False,
    )
    ai_active = fields.Boolean(
        string="AI Responding",
        default=True,
        help=(
            "Uncheck to stop AI auto-responses and handle this "
            "conversation manually. Automatically turned off when "
            "the AI escalates to a human operator."
        ),
    )

    @api.model_create_multi
    def create(self, vals_list):
        """Auto-assign the connector's default AI agent to new rooms.

        When a room is created for a connector that has a default_ai_agent_id
        (e.g. an inbound WhatsApp/Telegram chat), the agent is assigned
        automatically so the AI starts responding without manual setup.
        An explicit muk_ai_agent_id in vals (including False) is respected.
        """
        Connector = self.env["chatroom.connector"]
        for vals in vals_list:
            if "muk_ai_agent_id" in vals or not vals.get("connector_id"):
                continue
            connector = Connector.browse(vals["connector_id"])
            if connector.default_ai_agent_id:
                vals["muk_ai_agent_id"] = connector.default_ai_agent_id.id
        return super().create(vals_list)

    def _room_updated_payload_extras(self):
        self.ensure_one()
        return {"ai_active": self.ai_active}

    def write(self, vals):
        ai_fields = {"ai_active", "needs_attention"}
        needs_notify = bool(ai_fields & set(vals))
        result = super().write(vals)
        if needs_notify:
            self._notify_room_updated()
        return result

    def _ensure_ai_session(self):
        """Return the active muk_ai.session for this room, creating a new one
        if the current session is absent or in a terminal state."""
        self.ensure_one()
        session = self.muk_ai_session_id
        if session and session.state not in _TERMINAL_STATES:
            return session
        bot = self.env.ref("chatroom_ai_bridge.user_chatroom_bot")
        partner = self.partner_ids[:1]
        new_session = (
            self.env["muk_ai.session"]
            .with_user(bot)
            .sudo()
            .create({
                "name": f"Chatroom #{self.id} — {self.name or ''}".strip(" —"),
                "agent_id": self.muk_ai_agent_id.id,
                "override_approval_mode": "off",
                "user_context": {
                    "chatroom_room_id": self.id,
                    "customer_name": partner.name or self.name or "",
                    "customer_phone": partner.phone or "",
                },
            })
        )
        self.sudo().muk_ai_session_id = new_session.id
        return new_session

    def action_toggle_ai(self):
        for room in self:
            room.ai_active = not room.ai_active
