from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    chatroom_ai_response_delay = fields.Integer(
        string="AI Response Delay (seconds)",
        config_parameter="chatroom_ai_bridge.ai_response_delay",
        default=0,
        help=(
            "Seconds the AI waits after the last incoming message before "
            "replying. Each new incoming message resets the timer, so a burst "
            "of quick messages gets a single combined reply. 0 = reply "
            "immediately."
        ),
    )
