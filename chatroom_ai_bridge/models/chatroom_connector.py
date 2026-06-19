from odoo import fields, models


class ChatroomConnector(models.Model):
    _inherit = "chatroom.connector"

    default_ai_agent_id = fields.Many2one(
        "muk_ai.agent",
        string="Default AI Agent",
        help=(
            "AI agent automatically assigned to new rooms created by this "
            "connector (e.g. inbound WhatsApp/Telegram chats). Leave empty "
            "to create rooms without an agent and assign one manually."
        ),
    )
