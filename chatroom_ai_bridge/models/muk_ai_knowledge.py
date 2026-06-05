from odoo import models


class MukAIKnowledge(models.Model):
    _inherit = "muk_ai.knowledge"

    def _get_customer_facing_agents(self):
        return self.mapped("agent_ids").filtered("is_customer_facing")

    def create(self, vals_list):
        records = super().create(vals_list)
        agents = records._get_customer_facing_agents()
        if agents:
            agents._sync_customer_facing_skills()
        return records

    def write(self, vals):
        result = super().write(vals)
        agents = self._get_customer_facing_agents()
        if agents:
            agents._sync_customer_facing_skills()
        return result

    def unlink(self):
        agents = self._get_customer_facing_agents()
        result = super().unlink()
        if agents:
            agents._sync_customer_facing_skills()
        return result
