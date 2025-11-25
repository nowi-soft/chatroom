from odoo import fields, models


class ChatroomRoom(models.Model):
    _inherit = "chatroom.room"

    connector_id = fields.Many2one(
        "chatroom.connector",
        string="Connector",
        help="External messaging platform connector",
    )
    external_id = fields.Char(
        string="External ID",
        help="Unique identifier in the external platform (phone number, user ID, etc.)",
    )
