from odoo import models


class ChatroomRoom(models.Model):
    _inherit = "chatroom.room"

    def action_create_partner_from_chat(self):
        result = super().action_create_partner_from_chat()

        if self.connector_id and self.connector_id.connector_type == "evolution":
            if self.external_id:
                result["context"]["default_phone"] = self.external_id

        return result
