"""Wizard to create CRM Lead from Chat"""

from odoo import fields, models


class ChatroomCreateLeadWizard(models.TransientModel):
    _name = "chatroom.create.lead.wizard"
    _description = "Create Lead from Chat"

    room_id = fields.Many2one("chatroom.room", required=True, readonly=True)
    name = fields.Char("Lead Title", required=True)
    partner_id = fields.Many2one("res.partner", "Customer")
    contact_name = fields.Char()
    email = fields.Char()
    phone = fields.Char()
    description = fields.Text()
    expected_revenue = fields.Float()
    priority = fields.Selection(
        [("0", "Low"), ("1", "Medium"), ("2", "High"), ("3", "Very High")],
        default="1",
    )

    def action_create_lead(self):
        self.ensure_one()

        lead_vals = {
            "name": self.name,
            "partner_id": self.partner_id.id if self.partner_id else False,
            "contact_name": self.contact_name
            or (self.partner_id.name if self.partner_id else False),
            "email_from": self.email
            or (self.partner_id.email if self.partner_id else False),
            "phone": self.phone
            or (self.partner_id.phone if self.partner_id else False),
            "description": self.description,
            "expected_revenue": self.expected_revenue,
            "priority": self.priority,
            "chatroom_room_id": self.room_id.id,
            "chatroom_room_ids": [(4, self.room_id.id)],
            "user_id": self.room_id.assigned_to_id.id
            if self.room_id.assigned_to_id
            else self.env.user.id,
        }

        lead = self.env["crm.lead"].create(lead_vals)

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Lead Created",
                "message": f"Lead '{lead.name}' created successfully",
                "type": "success",
                "next": {
                    "type": "ir.actions.act_window",
                    "res_model": "crm.lead",
                    "res_id": lead.id,
                    "views": [[False, "form"]],
                    "target": "current",
                },
            },
        }
