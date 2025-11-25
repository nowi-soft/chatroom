"""Chatroom Room extensions for CRM"""

from odoo import fields, models


class ChatroomRoom(models.Model):
    _inherit = "chatroom.room"

    related_lead_ids = fields.Many2many(
        "crm.lead",
        "crm_lead_chatroom_room_rel",
        "room_id",
        "lead_id",
        string="Related Leads",
        help="Leads linked to this chat room",
    )

    def action_create_lead_wizard(self):
        self.ensure_one()

        return {
            "type": "ir.actions.act_window",
            "name": "Create Lead",
            "res_model": "chatroom.create.lead.wizard",
            "view_mode": "form",
            "views": [[False, "form"]],
            "target": "new",
            "context": {
                "default_room_id": self.id,
                "default_name": self.name,
                "default_partner_id": self.partner_ids[0].id
                if self.partner_ids
                else False,
            },
        }
