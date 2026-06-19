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
            ("audio", "Audio"),
            ("file", "File"),
        ],
        default="text",
        required=True,
    )

    attachment_id = fields.Many2one(
        "ir.attachment",
        string="Attachment",
        ondelete="cascade",
        help="Attachment for audio, image or file messages",
    )
    filename = fields.Char(
        help="Original filename of the attachment",
    )
    mime_type = fields.Char(
        help="MIME type of the attachment",
    )
    file_url = fields.Char(
        string="File URL",
        compute="_compute_file_url",
        help="URL for the file (generated from attachment or external URL)",
    )
    media_duration = fields.Integer(
        help="Duration in seconds for audio/video files",
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

    @api.depends("attachment_id", "attachment_id.datas", "mime_type")
    def _compute_file_url(self):
        for msg in self:
            if msg.attachment_id and msg.attachment_id.datas:
                if msg.message_type == "file":
                    msg.file_url = f"/chatroom/file/{msg.attachment_id.id}"
                else:
                    mime_type = msg.mime_type or "application/octet-stream"
                    data_b64 = (
                        msg.attachment_id.datas.decode("utf-8")
                        if isinstance(msg.attachment_id.datas, bytes)
                        else msg.attachment_id.datas
                    )
                    msg.file_url = f"data:{mime_type};base64,{data_b64}"
            else:
                msg.file_url = False

    @api.model_create_multi
    def create(self, vals_list):
        messages = super().create(vals_list)

        rooms_to_notify = self.env["chatroom.room"]

        for message in messages:
            if message.direction == "incoming" and message.room_id.state == "closed":
                message.room_id.write(
                    {
                        "state": "unassigned",
                        "assigned_to_id": False,
                    }
                )

            message._notify_message_created()
            rooms_to_notify |= message.room_id

        self.env.flush_all()
        for room in rooms_to_notify:
            room._notify_room_updated()

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
            "filename": self.filename,
            "mime_type": self.mime_type,
            "file_url": self.file_url,
            "media_duration": self.media_duration,
            "attachment_id": self.attachment_id.id if self.attachment_id else False,
        }

        chatroom_users = self.env.ref("chatroom.group_chatroom_user").user_ids
        chatroom_managers = self.env.ref("chatroom.group_chatroom_manager").user_ids

        users_to_notify = chatroom_managers

        if self.room_id.assigned_to_id:
            if self.room_id.assigned_to_id in chatroom_users:
                users_to_notify |= self.room_id.assigned_to_id
        else:
            users_to_notify |= chatroom_users - chatroom_managers

        for user in users_to_notify:
            if user.partner_id:
                user.partner_id._bus_send("chatroom/message_created", payload)
