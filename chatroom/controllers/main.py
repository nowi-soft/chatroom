import base64

from odoo import http
from odoo.http import request


class ChatroomController(http.Controller):
    @http.route("/chatroom/rooms", type="jsonrpc", auth="user")
    def get_rooms(self, **kw):
        rooms = request.env["chatroom.room"].search(
            [("state", "!=", "closed")], order="last_message_date desc"
        )

        return [
            {
                "id": room.id,
                "name": room.name,
                "assigned_to_id": room.assigned_to_id.id
                if room.assigned_to_id
                else False,
                "state": room.state,
                "message_count": room.message_count,
                "last_message_date": room.last_message_date.isoformat()
                if room.last_message_date
                else False,
                "last_message_preview": room.last_message_preview,
            }
            for room in rooms
        ]

    @http.route("/chatroom/messages/<int:room_id>", type="jsonrpc", auth="user")
    def get_messages(self, room_id, **kw):
        room = request.env["chatroom.room"].browse(room_id)
        if not room.exists():
            return {"error": "Room not found"}

        messages = room.message_ids.sorted("create_date")

        return [
            {
                "id": msg.id,
                "body": msg.body,
                "direction": msg.direction,
                "author_name": msg.author_name,
                "message_type": msg.message_type,
                "create_date": msg.create_date.isoformat(),
                "product": {
                    "id": msg.product_id.id,
                    "name": msg.product_name,
                    "price": msg.product_price,
                    "image": msg.product_image,
                }
                if msg.product_id
                else False,
            }
            for msg in messages
        ]

    @http.route("/chatroom/send", type="jsonrpc", auth="user")
    def send_message(self, room_id, body, product_id=None, **kw):
        room = request.env["chatroom.room"].browse(room_id)
        if not room.exists():
            return {"error": "Room not found"}

        vals = {
            "room_id": room_id,
            "body": body,
            "direction": "outgoing",
            "user_id": request.env.user.id,
        }

        if product_id:
            vals["message_type"] = "product"
            vals["product_id"] = product_id

        message = request.env["chatroom.message"].create(vals)

        return {
            "success": True,
            "message_id": message.id,
        }

    @http.route(
        "/chatroom/room/<int:room_id>/create_partner", type="jsonrpc", auth="user"
    )
    def create_partner_from_chat(self, room_id, **kw):
        room = request.env["chatroom.room"].browse(room_id)
        if not room.exists():
            return {"error": "Room not found"}

        room.action_create_partner_from_chat()

        return {
            "success": True,
            "partner_id": room.partner_id.id,
            "partner_name": room.partner_id.name,
        }

    @http.route("/chatroom/room/<int:room_id>/link_record", type="jsonrpc", auth="user")
    def link_record(self, room_id, field_name, record_id, **kw):
        room = request.env["chatroom.room"].browse(room_id)
        if not room.exists():
            return {"error": "Room not found"}

        if field_name in ["partner_id"]:
            room.write({field_name: record_id})

        elif field_name.endswith("_ids"):
            room.write({field_name: [(4, record_id)]})

        return {
            "success": True,
            "related_records": room.get_related_records(),
        }

    @http.route(
        "/chatroom/room/<int:room_id>/unlink_record", type="jsonrpc", auth="user"
    )
    def unlink_record(self, room_id, field_name, record_id, **kw):
        room = request.env["chatroom.room"].browse(room_id)
        if not room.exists():
            return {"error": "Room not found"}

        if field_name in ["partner_id"]:
            room.write({field_name: False})

        elif field_name.endswith("_ids"):
            room.write({field_name: [(3, record_id)]})

        return {
            "success": True,
            "related_records": room.get_related_records(),
        }

    @http.route(
        "/chatroom/room/<int:room_id>/get_related_records", type="jsonrpc", auth="user"
    )
    def get_related_records(self, room_id, **kw):
        room = request.env["chatroom.room"].browse(room_id)
        if not room.exists():
            return {"error": "Room not found"}

        return {
            "success": True,
            "related_records": room.get_related_records(),
        }

    @http.route(
        "/chatroom/upload_file", type="http", auth="user", methods=["POST"], csrf=True
    )
    def upload_file(self, **kwargs):
        files = request.httprequest.files.getlist("files")
        attachments = []

        for file in files:
            file_content = file.read()
            file_b64 = base64.b64encode(file_content)

            attachment = request.env["ir.attachment"].create(
                {
                    "name": file.filename,
                    "datas": file_b64,
                    "mimetype": file.content_type,
                    "res_model": "chatroom.message",
                    "res_id": 0,
                }
            )

            attachments.append(
                {
                    "id": attachment.id,
                    "name": attachment.name,
                    "mimetype": attachment.mimetype,
                }
            )

        return request.make_json_response({"attachments": attachments})

    @http.route(
        "/chatroom/file/<int:attachment_id>",
        type="http",
        auth="user",
        methods=["GET"],
        csrf=False,
    )
    def get_file(self, attachment_id, **kwargs):
        attachment = request.env["ir.attachment"].browse(attachment_id)
        if not attachment.exists():
            return request.not_found()

        file_content = base64.b64decode(attachment.datas)

        headers = [
            ("Content-Type", attachment.mimetype or "application/octet-stream"),
            ("Content-Length", str(len(file_content))),
            ("Accept-Ranges", "bytes"),
            ("Cache-Control", "public, max-age=31536000"),
        ]

        return request.make_response(file_content, headers=headers)
