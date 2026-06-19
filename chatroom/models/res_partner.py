from odoo import api, fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    chatroom_ids = fields.Many2many(
        "chatroom.room",
        "chatroom_room_partner_rel",
        "partner_id",
        "room_id",
        string="Chat Rooms",
        help="Chat rooms where this contact is involved",
    )
    chatroom_count = fields.Integer(string="# Chats", compute="_compute_chatroom_count")

    @api.model_create_multi
    def create(self, vals_list):
        partners = super().create(vals_list)

        chatroom_room_id = self.env.context.get("default_chatroom_room_id")
        if chatroom_room_id:
            room = self.env["chatroom.room"].browse(chatroom_room_id)
            if room.exists():
                room.write({"partner_ids": [(4, partner.id) for partner in partners]})

        return partners

    def _compute_chatroom_count(self):
        for partner in self:
            partner.chatroom_count = len(partner.chatroom_ids)

    def action_view_chatrooms(self):
        self.ensure_one()
        return {
            "type": "ir.actions.client",
            "tag": "chatroom.app",
            "params": {
                "partner_id": self.id,
                "partner_name": self.name,
            },
        }

    def action_open_first_chatroom(self):
        self.ensure_one()
        action = {"type": "ir.actions.client", "tag": "chatroom.app"}
        if self.chatroom_ids:
            action["params"] = {"room_id": self.chatroom_ids[0].id}
        return action
