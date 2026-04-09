from odoo import api, fields, models


class ChatroomRoom(models.Model):
    _name = "chatroom.room"
    _description = "Chat Room"
    _inherit = ["bus.listener.mixin"]
    _order = "last_message_date desc, id desc"

    name = fields.Char(required=True, index=True)
    active = fields.Boolean(default=True)

    partner_ids = fields.Many2many(
        "res.partner",
        "chatroom_room_partner_rel",
        "room_id",
        "partner_id",
        string="Contacts",
    )

    assigned_to_id = fields.Many2one("res.users", string="Assigned To", index=True)
    state = fields.Selection(
        [
            ("unassigned", "Unassigned"),
            ("assigned", "Assigned"),
            ("closed", "Closed"),
        ],
        default="unassigned",
        required=True,
        index=True,
    )

    message_ids = fields.One2many("chatroom.message", "room_id", string="Messages")
    message_count = fields.Integer(compute="_compute_message_count", store=True)
    last_message_date = fields.Datetime(compute="_compute_last_message", store=True)
    last_message_preview = fields.Char(compute="_compute_last_message", store=True)

    @api.depends("message_ids")
    def _compute_message_count(self):
        if not self.ids:
            return
        counts = self.env["chatroom.message"].read_group(
            [("room_id", "in", self.ids)], ["room_id"], ["room_id"]
        )
        count_map = {r["room_id"][0]: r["room_id_count"] for r in counts}
        for room in self:
            room.message_count = count_map.get(room.id, 0)

    @api.depends("message_ids.create_date", "message_ids.body")
    def _compute_last_message(self):
        for room in self:
            last_msg = room.message_ids[-1:]
            room.last_message_date = last_msg.create_date if last_msg else False
            room.last_message_preview = last_msg.body[:50] if last_msg else ""

    def action_assign_to_me(self):
        self.write(
            {
                "assigned_to_id": self.env.user.id,
                "state": "assigned",
            }
        )
        self._notify_room_updated()
        return True

    def action_unassign(self):
        self.write(
            {
                "assigned_to_id": False,
                "state": "unassigned",
            }
        )
        self._notify_room_updated()
        return True

    def action_close(self):
        for room in self:
            note_body = self.env._("Chat closed")
            if room.assigned_to_id:
                note_body += self.env._(
                    " (was assigned to: %s)", room.assigned_to_id.name
                )

            self.env["chatroom.message"].create(
                {
                    "room_id": room.id,
                    "body": note_body,
                    "user_id": self.env.user.id,
                    "direction": "outgoing",
                    "is_internal": True,
                }
            )

            room.write(
                {
                    "state": "closed",
                    "assigned_to_id": False,
                }
            )

        self._notify_room_updated()
        return True

    def action_reopen(self):
        for room in self:
            room.state = "assigned" if room.assigned_to_id else "unassigned"
        self._notify_room_updated()
        return True

    def _notify_room_updated(self):
        for room in self:
            payload = {
                "id": room.id,
                "name": room.name,
                "assigned_to_id": [room.assigned_to_id.id, room.assigned_to_id.name]
                if room.assigned_to_id
                else False,
                "state": room.state,
                "message_count": room.message_count,
                "last_message_date": room.last_message_date.isoformat()
                if room.last_message_date
                else False,
                "last_message_preview": room.last_message_preview,
            }

            chatroom_users = self.env.ref("chatroom.group_chatroom_user").users
            chatroom_managers = self.env.ref("chatroom.group_chatroom_manager").users
            all_chatroom_users = chatroom_users | chatroom_managers

            if room.state in ["assigned", "unassigned"]:
                users_to_notify = all_chatroom_users
            else:
                users_to_notify = chatroom_managers
                if room.assigned_to_id and room.assigned_to_id in chatroom_users:
                    users_to_notify |= room.assigned_to_id

            for user in users_to_notify:
                if user.partner_id:
                    user.partner_id._bus_send("chatroom/room_updated", payload)

    def notify_room_updated(self):
        return self._notify_room_updated()

    def action_create_partner_from_chat(self):
        self.ensure_one()

        context = {
            "default_name": self.name,
        }

        return {
            "type": "ir.actions.act_window",
            "res_model": "res.partner",
            "view_mode": "form",
            "views": [[False, "form"]],
            "target": "current",
            "context": context,
        }

    def get_related_records(self):
        self.ensure_one()
        result = []

        for partner in self.partner_ids:
            result.append(
                {
                    "model": "res.partner",
                    "id": partner.id,
                    "name": partner.name,
                    "display_name": partner.display_name,
                    "field_name": "partner_ids",
                }
            )

        return result

    def action_open_chatroom(self):
        self.ensure_one()
        return {
            "type": "ir.actions.client",
            "tag": "chatroom.app",
            "params": {
                "room_id": self.id,
            },
        }
