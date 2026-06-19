import logging
from datetime import timedelta

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
    ai_dispatch_due = fields.Datetime(
        string="AI Dispatch Due",
        readonly=True,
        copy=False,
        help=(
            "When set, the AI reply for this room is scheduled for this time "
            "(debounce). Each new incoming message pushes it forward."
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

    # ------------------------------------------------------------------
    # AI dispatch (immediate or debounced)
    # ------------------------------------------------------------------
    def _ai_response_delay(self):
        """Configured debounce delay in seconds (0 = reply immediately)."""
        param = self.env["ir.config_parameter"].sudo().get_param(
            "chatroom_ai_bridge.ai_response_delay", "0"
        )
        try:
            return max(0, int(float(param)))
        except (TypeError, ValueError):
            return 0

    def _dispatch_to_ai(self, content):
        """Send a user message to the room's AI session, starting it if new."""
        self.ensure_one()
        if not self.muk_ai_agent_id or not self.ai_active:
            return
        content = (content or "").strip()
        if not content:
            return
        session = self._ensure_ai_session()
        bot = self.env.ref("chatroom_ai_bridge.user_chatroom_bot")
        session_user = session.with_user(bot).sudo()
        if session.state == "new":
            session_user.start(content)
        else:
            session_user.send_message(content)

    def _schedule_ai_dispatch(self, delay):
        """(Re)arm the debounce timer: reply `delay` seconds from now unless a
        newer incoming message pushes it forward again."""
        self.ensure_one()
        due = fields.Datetime.now() + timedelta(seconds=delay)
        self.sudo().ai_dispatch_due = due
        self.env.ref("chatroom_ai_bridge.cron_dispatch_due_ai").sudo()._trigger(at=due)

    def _dispatch_pending_to_ai(self):
        """Send all not-yet-dispatched incoming messages of this room as a
        single combined turn, then let the AI reply once."""
        self.ensure_one()
        self.sudo().ai_dispatch_due = False
        Message = self.env["chatroom.message"].sudo()
        msgs = Message.search(
            [
                ("room_id", "=", self.id),
                ("direction", "=", "incoming"),
                ("ai_dispatched", "=", False),
            ],
            order="id asc",
        )
        if not msgs:
            return
        msgs.write({"ai_dispatched": True})
        if not (self.muk_ai_agent_id and self.ai_active):
            return
        combined = "\n".join(m.body for m in msgs if m.body)
        if combined.strip():
            self._dispatch_to_ai(combined)

    @api.model
    def _cron_dispatch_due_ai(self):
        """Cron entrypoint: dispatch every room whose debounce window elapsed."""
        now = fields.Datetime.now()
        rooms = self.search(
            [
                ("ai_dispatch_due", "!=", False),
                ("ai_dispatch_due", "<=", now),
                ("muk_ai_agent_id", "!=", False),
                ("ai_active", "=", True),
            ]
        )
        for room in rooms:
            try:
                room._dispatch_pending_to_ai()
            except Exception as e:
                _logger.exception(
                    "AI debounced dispatch failed for room %s: %s", room.id, e
                )
