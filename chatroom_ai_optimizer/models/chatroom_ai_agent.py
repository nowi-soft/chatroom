from odoo import fields, models


class ChatroomAIAgent(models.Model):
    _inherit = "chatroom.ai.agent"

    optimizer_id = fields.Many2one(
        "chatroom.ai.prompt.optimizer",
        string="Prompt Optimizer",
        help="Optimizer for auto-tuning this agent's prompt",
    )

    def action_setup_optimizer(self):
        self.ensure_one()

        if not self.optimizer_id:
            optimizer = self.env["chatroom.ai.prompt.optimizer"].create(
                {
                    "name": f"Optimizer for {self.name}",
                    "agent_id": self.id,
                }
            )
            self.optimizer_id = optimizer.id

        return {
            "type": "ir.actions.act_window",
            "name": "Prompt Optimizer",
            "res_model": "chatroom.ai.prompt.optimizer",
            "view_mode": "form",
            "res_id": self.optimizer_id.id,
        }
