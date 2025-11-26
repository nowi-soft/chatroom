from odoo import api, fields, models
from odoo.exceptions import ValidationError


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    chatroom_ai_message_batch_delay = fields.Integer(
        string="AI Message Batch Delay (seconds)",
        config_parameter="chatroom.ai_message_batch_delay",
        default=15,
    )

    @api.constrains("chatroom_ai_message_batch_delay")
    def _check_chatroom_ai_message_batch_delay(self):
        for record in self:
            if record.chatroom_ai_message_batch_delay < 0:
                raise ValidationError(
                    self.env._("AI Message Batch Delay cannot be negative.")
                )
