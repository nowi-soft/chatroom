import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class ChatroomRoom(models.Model):
    _inherit = "chatroom.room"
    _order = "needs_attention desc, last_message_date desc, id desc"

    needs_attention = fields.Boolean(
        default=False,
        index=True,
        help="Chat requires urgent human attention (AI failed, error, etc.)",
    )

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

    @api.model_create_multi
    def create(self, vals_list):
        rooms = super().create(vals_list)

        for room in rooms:
            if not room.assigned_to_id:
                agent = self.env["chatroom.ai.agent"].search(
                    [("active", "=", True)], limit=1
                )
                if agent:
                    room.write(
                        {
                            "ai_agent_id": agent.id,
                            "ai_enabled": True,
                        }
                    )
                    room._notify_ai_state_change()

        return rooms

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

        self.write(
            {
                "ai_enabled": True,
                "needs_attention": False,
            }
        )

        self._notify_ai_state_change()
        self._notify_room_updated()

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
            "view_mode": "list,form",
            "domain": [("room_id", "=", self.id)],
            "context": {"default_room_id": self.id},
        }

    def write(self, vals):
        old_needs_attention = {room.id: room.needs_attention for room in self}
        result = super().write(vals)

        if "assigned_to_id" in vals:
            for room in self:
                if vals["assigned_to_id"]:
                    if room.ai_enabled:
                        room.action_disable_ai()

                else:
                    if not room.ai_enabled and room.ai_agent_id:
                        room.action_enable_ai()

        if "needs_attention" in vals and vals["needs_attention"]:
            for room in self:
                if not old_needs_attention.get(room.id):
                    room._notify_urgent_attention()

        return result

    def _notify_room_updated(self):
        for room in self:
            payload = {
                "id": room.id,
                "name": room.name,
                "assigned_to_id": [room.assigned_to_id.id, room.assigned_to_id.name]
                if room.assigned_to_id
                else False,
                "state": room.state,
                "needs_attention": room.needs_attention,
                "message_count": room.message_count,
                "last_message_date": room.last_message_date.isoformat()
                if room.last_message_date
                else False,
                "last_message_preview": room.last_message_preview,
            }

            chatroom_users = self.env.ref("chatroom.group_chatroom_user").user_ids
            chatroom_managers = self.env.ref("chatroom.group_chatroom_manager").user_ids
            all_chatroom_users = chatroom_users | chatroom_managers

            if room.state in ["assigned", "unassigned"]:
                users_to_notify = all_chatroom_users
            else:
                users_to_notify = chatroom_managers
                if room.assigned_to_id and room.assigned_to_id in chatroom_users:
                    users_to_notify |= room.assigned_to_id

            for user in users_to_notify:
                if user.partner_id:
                    user.partner_id._bus_send("chatroom/room_updated", payload)

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

    def _notify_urgent_attention(self):
        self.ensure_one()

        try:
            chatroom_users = self.env.ref("chatroom.group_chatroom_user").all_user_ids
        except Exception as e:
            _logger.error(f"Error getting chatroom users: {e}")
            chatroom_users = self.env["res.users"]

        notified_partners = set()
        for user in chatroom_users:
            if user.partner_id and user.partner_id.id not in notified_partners:
                notified_partners.add(user.partner_id.id)
                self.env["bus.bus"]._sendone(
                    user.partner_id,
                    "chatroom/ai_urgent_attention",
                    {
                        "room_id": self.id,
                        "room_name": self.name,
                    },
                )

    def action_pause_ai_and_request_attention(self):
        self.ensure_one()

        if self.ai_conversation_ids:
            active_convs = self.ai_conversation_ids.filtered(
                lambda c: c.state == "active"
            )
            active_convs.write({"state": "paused"})

        self.write(
            {
                "ai_enabled": False,
                "state": "unassigned",
                "needs_attention": True,
            }
        )

        agent_name = (
            self.ai_agent_id.name if self.ai_agent_id else self.env._("AI Agent")
        )
        self.env["chatroom.message"].create(
            {
                "room_id": self.id,
                "body": self.env._("⚠️ AI Agent paused: Human intervention required."),
                "direction": "outgoing",
                "is_internal": True,
                "user_id": self.env.ref("base.user_admin").id,
                "author_name": agent_name,
            }
        )

        self._notify_room_updated()
