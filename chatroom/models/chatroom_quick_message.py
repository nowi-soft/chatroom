from odoo import fields, models


class ChatroomQuickMessage(models.Model):
    _name = "chatroom.quick.message"
    _description = "Quick Message"
    _order = "sequence, name"

    name = fields.Char(required=True, string="Title")
    message = fields.Text(required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
