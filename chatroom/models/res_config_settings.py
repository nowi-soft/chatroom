from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    chatroom_show_author_name = fields.Boolean(
        string="Show Author Name in Messages",
        config_parameter="chatroom.show_author_name",
        default=True,
        help="Display the author name below each message in the chat interface",
    )
