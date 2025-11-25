from odoo import api, fields, models


class ChatroomMessage(models.Model):
    _name = "chatroom.message"
    _description = "Chat Message"
    _order = "create_date asc, id asc"

    room_id = fields.Many2one(
        "chatroom.room", required=True, ondelete="cascade", index=True
    )
    body = fields.Html(required=True, sanitize=False)

    direction = fields.Selection(
        [
            ("incoming", "Incoming"),
            ("outgoing", "Outgoing"),
        ],
        default="outgoing",
        required=True,
    )

    user_id = fields.Many2one(
        "res.users", string="User", default=lambda self: self.env.user
    )
    author_name = fields.Char(
        compute="_compute_author_name", store=True, readonly=False
    )

    message_type = fields.Selection(
        [
            ("text", "Text"),
            ("image", "Image"),
        ],
        default="text",
        required=True,
    )

    is_internal = fields.Boolean(
        "Internal Note",
        default=False,
        help=(
            "If checked, this message is an internal note and won't be "
            "sent to external services"
        ),
    )

    @api.depends("user_id", "direction")
    def _compute_author_name(self):
        for msg in self:
            if msg.direction == "outgoing" and msg.user_id:
                msg.author_name = msg.user_id.name
            else:
                msg.author_name = msg.room_id.name or "Customer"

    @api.model_create_multi
    def create(self, vals_list):
        messages = super().create(vals_list)

        for message in messages:
            if message.direction == "incoming" and message.room_id.state == "closed":
                message.room_id.write(
                    {
                        "state": "unassigned",
                        "assigned_to_id": False,
                    }
                )
                message.room_id._notify_room_updated()

            message._notify_message_created()
        return messages

    def _get_message_text_with_author(self):
        self.ensure_one()
        show_author_name = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("chatroom.show_author_name", default="True")
        )
        message_text = self.body

        if show_author_name == "True" and self.user_id:
            message_text = f"{self.body}\n\n- {self.user_id.name}"

        return message_text

    def _notify_message_created(self):
        self.ensure_one()
        payload = {
            "id": self.id,
            "room_id": self.room_id.id,
            "body": self.body,
            "direction": self.direction,
            "author_name": self.author_name,
            "message_type": self.message_type,
            "create_date": self.create_date.isoformat() if self.create_date else False,
        }

        self.env.cr.execute(
            """
            SELECT DISTINCT uid
            FROM res_groups_users_rel
            WHERE gid IN %s
        """,
            (
                tuple(
                    [
                        self.env.ref("chatroom.group_chatroom_user").id,
                        self.env.ref("chatroom.group_chatroom_manager").id,
                    ]
                ),
            ),
        )
        user_ids = [row[0] for row in self.env.cr.fetchall()]
        users_to_notify = self.env["res.users"].browse(user_ids)

        managers = users_to_notify.filtered(
            lambda u: u.has_group("chatroom.group_chatroom_manager")
        )

        regular_users = users_to_notify - managers
        if self.room_id.assigned_to_id:
            regular_users = regular_users.filtered(
                lambda u: u.id == self.room_id.assigned_to_id.id
            )

        for user in managers | regular_users:
            if user.partner_id:
                user.partner_id._bus_send("chatroom/message_created", payload)

        self.room_id._notify_room_updated()
