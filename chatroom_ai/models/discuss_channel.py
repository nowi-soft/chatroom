"""Extend discuss.channel to intercept messages in AI agent setup channels."""

import re
import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class DiscussChannel(models.Model):
    _inherit = "discuss.channel"

    setup_session_id = fields.Many2one(
        "chatroom.ai.agent.setup.session",
        string="Setup Session",
        ondelete="set null",
    )

    def _message_post_after_hook(self, message, msg_vals):
        super()._message_post_after_hook(message, msg_vals)
        session = self.setup_session_id
        if not session:
            return
        # Avoid processing the bot's own replies (prevent recursion)
        if message.author_id.id == session.bot_partner_id.id:
            return

        KB_STEPS = {"kb_manage", "kb_awaiting_update"}
        ACTIVE_STEPS = {
            "business_name", "agent_name", "business_type", "business_description",
            "objective", "lead_threshold", "tone", "extra_instructions", "confirm", "done",
        } | KB_STEPS

        if session.step not in ACTIVE_STEPS:
            return

        # Handle file attachments when in KB management mode
        if message.sudo().attachment_ids and session.step in KB_STEPS:
            session.process_user_attachment(message)
            return

        # Process text message
        body = re.sub(r"<[^>]+>", "", message.body or "").strip()
        if body:
            session.process_user_message(body)
