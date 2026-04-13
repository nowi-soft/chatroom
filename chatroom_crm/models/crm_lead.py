"""CRM Lead extensions for ChatRoom"""

from odoo import api, fields, models


class CrmLead(models.Model):
    _inherit = "crm.lead"

    chatroom_room_ids = fields.Many2many(
        "chatroom.room",
        "crm_lead_chatroom_room_rel",
        "lead_id",
        "room_id",
        string="Chat Rooms",
        help="All chat rooms linked to this lead",
    )
    chatroom_room_count = fields.Integer(
        string="# Chat Rooms",
        compute="_compute_chatroom_room_count",
    )

    @api.depends("chatroom_room_ids")
    def _compute_chatroom_room_count(self):
        for lead in self:
            lead.chatroom_room_count = len(lead.chatroom_room_ids)

    def action_view_chatroom_rooms(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id(
            "chatroom.action_chatroom_room"
        )
        action["domain"] = [("id", "in", self.chatroom_room_ids.ids)]
        action["context"] = {
            "default_related_lead_id": self.id,
        }
        return action
