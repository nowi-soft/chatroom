import random

from odoo import http
from odoo.http import request


class ChatroomSimulator(http.Controller):
    @http.route("/chatroom/simulate/message", type="jsonrpc", auth="user")
    def simulate_incoming_message(self, room_id=None, **kw):
        sample_messages = [
            "Hi! I want to ask about a product",
            "Do you have stock of product X?",
            "What's the price?",
            "Do you ship?",
            "Thanks for the attention",
            "Can I pay with card?",
            "Is it available in other colors?",
            "How long does shipping take?",
        ]

        if not room_id:
            room = request.env["chatroom.room"].search(
                [("state", "=", "unassigned")], limit=1
            )

            if not room:
                room = request.env["chatroom.room"].create(
                    {
                        "name": f"Customer {random.randint(1000, 9999)}",
                        "external_id": f"+549{random.randint(1000000000, 9999999999)}",
                        "state": "unassigned",
                    }
                )
            room_id = room.id

        message = request.env["chatroom.message"].create(
            {
                "room_id": room_id,
                "body": random.choice(sample_messages),
                "direction": "incoming",
                "message_type": "text",
            }
        )

        return {"success": True, "message_id": message.id, "room_id": room_id}

    @http.route("/chatroom/simulate/new_chat", type="jsonrpc", auth="user")
    def simulate_new_chat(self, **kw):
        room = request.env["chatroom.room"].create(
            {
                "name": f"New Customer {random.randint(1000, 9999)}",
                "external_id": f"+549{random.randint(1000000000, 9999999999)}",
                "state": "unassigned",
            }
        )

        request.env["chatroom.message"].create(
            {
                "room_id": room.id,
                "body": "Hello! I have a question...",
                "direction": "incoming",
                "message_type": "text",
            }
        )

        return {"success": True, "room_id": room.id}

    @http.route("/chatroom/simulate/batch", type="jsonrpc", auth="user")
    def simulate_batch(self, count=5, **kw):
        rooms = []
        for _i in range(count):
            result = self.simulate_new_chat()
            rooms.append(result["room_id"])

        return {"success": True, "rooms_created": len(rooms), "room_ids": rooms}
