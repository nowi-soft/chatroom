"""Wizard for testing AI tools"""

import json
import logging

from odoo import fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class ChatroomAIToolTestWizard(models.TransientModel):
    _name = "chatroom.ai.tool.test.wizard"
    _description = "Test AI Tool"

    tool_id = fields.Many2one("chatroom.ai.tool", required=True, readonly=True)
    agent_id = fields.Many2one(
        "chatroom.ai.agent",
        string="AI Agent",
        required=True,
        domain=[("active", "=", True)],
        help="Select the agent to use for testing",
    )
    room_id = fields.Many2one(
        "chatroom.room",
        string="Test Chat Room",
        required=False,
        help=(
            "Optional: Select a chat room to use for testing. "
            "If not provided, a temporary test room will be created."
        ),
    )
    test_params = fields.Text(
        string="Test Parameters (JSON)",
        default="{}",
        help="JSON object with test parameters",
    )
    result = fields.Text(string="Test Result", readonly=True)
    state = fields.Selection([("setup", "Setup"), ("done", "Done")], default="setup")

    def action_run_test(self):
        self.ensure_one()

        try:
            params = json.loads(self.test_params or "{}")
        except json.JSONDecodeError as e:
            raise UserError(
                self.env._("Invalid JSON in test parameters: %s", str(e))
            ) from e

        temp_room_created = False
        if not self.room_id:
            test_room = self.env["chatroom.room"].create(
                {
                    "name": f"Test Room - {self.tool_id.name}",
                    "state": "closed",
                }
            )
            temp_room_created = True
        else:
            test_room = self.room_id

        conversation = self.env["chatroom.ai.conversation"].create(
            {
                "room_id": test_room.id,
                "agent_id": self.agent_id.id,
                "state": "testing",
            }
        )

        try:
            result = self.tool_id.execute(test_room, params, conversation)

            result_text = json.dumps(result, indent=2, ensure_ascii=False)

            self.write({"result": result_text, "state": "done"})

            conversation.unlink()
            if temp_room_created:
                test_room.unlink()

            return {
                "type": "ir.actions.act_window",
                "res_model": self._name,
                "res_id": self.id,
                "view_mode": "form",
                "target": "new",
            }

        except Exception as e:
            if conversation.exists():
                conversation.unlink()
            if temp_room_created and test_room.exists():
                test_room.unlink()

            error_msg = f"Error: {str(e)}"
            self.write({"result": error_msg, "state": "done"})

            return {
                "type": "ir.actions.act_window",
                "res_model": self._name,
                "res_id": self.id,
                "view_mode": "form",
                "target": "new",
            }
