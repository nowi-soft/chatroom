"""Extension of chatroom.room for AI integration"""

from odoo import fields, models


class ChatroomRoom(models.Model):
    _inherit = "chatroom.room"

    ai_agent_id = fields.Many2one(
        "chatroom.ai.agent",
        string="AI Agent",
        help="AI Agent assigned to this chat",
    )
    ai_enabled = fields.Boolean(
        string="AI Enabled",
        default=False,
        help="Enable AI auto-responses for this chat",
    )
    ai_conversation_ids = fields.One2many(
        "chatroom.ai.conversation",
        "room_id",
        string="AI Conversations",
    )
    ai_conversation_state = fields.Selection(
        related="ai_conversation_ids.state",
        string="AI Status",
        readonly=True,
    )

    def action_enable_ai(self):
        self.ensure_one()

        if not self.ai_agent_id:
            agent = self.env["chatroom.ai.agent"].search(
                [
                    ("active", "=", True),
                ],
                limit=1,
            )

            if agent:
                self.ai_agent_id = agent

        self.ai_enabled = True

        self._notify_ai_state_change()

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "message": "AI Agent enabled for this chat",
                "type": "success",
            },
        }

    def action_disable_ai(self):
        self.ensure_one()
        self.ai_enabled = False

        active_convs = self.ai_conversation_ids.filtered(lambda c: c.state == "active")
        active_convs.write({"state": "paused"})

        self._notify_ai_state_change()

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "message": "AI Agent disabled for this chat",
                "type": "info",
            },
        }

    def action_view_ai_conversations(self):
        self.ensure_one()

        return {
            "type": "ir.actions.act_window",
            "name": "AI Conversations",
            "res_model": "chatroom.ai.conversation",
            "view_mode": "tree,form",
            "domain": [("room_id", "=", self.id)],
            "context": {"default_room_id": self.id},
        }

    def write(self, vals):
        result = super().write(vals)

        if "assigned_to_id" in vals:
            for room in self:
                if vals["assigned_to_id"]:
                    if room.ai_enabled:
                        room.action_disable_ai()

                else:
                    if not room.ai_enabled and room.ai_agent_id:
                        room.action_enable_ai()

        return result

    def _notify_ai_state_change(self):
        self.ensure_one()

        partners = self.env["res.partner"].search(
            [
                ("user_ids", "!=", False),
            ]
        )

        for partner in partners:
            self.env["bus.bus"]._sendone(
                partner,
                "chatroom/ai_state_changed",
                {
                    "room_id": self.id,
                    "ai_enabled": self.ai_enabled,
                },
            )
