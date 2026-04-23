import json
import logging

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class ChatroomAITool(models.Model):
    _name = "chatroom.ai.tool"
    _description = "AI Agent Tool/Action"
    _order = "sequence, name"

    name = fields.Char(required=True)
    code_name = fields.Char(
        required=True,
        help="Unique identifier used by AI (e.g., 'create_lead', 'send_email')",
    )
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    description = fields.Text(
        required=True,
        help="Clear description of what this tool does (shown to AI)",
    )

    parameters_schema = fields.Text(
        "Parameters Schema (JSON)",
        required=True,
        default='{"type": "object", "properties": {}, "required": []}',
        help="JSON Schema defining the parameters this tool accepts",
    )

    python_code = fields.Text(
        help="Python code to execute. Available: env, room, params, agent. Must set result dict.",  # noqa: E501
    )

    agent_ids = fields.Many2many(
        "chatroom.ai.agent",
        "chatroom_ai_agent_tool_rel",
        "tool_id",
        "agent_id",
    )
    example_usage = fields.Text(
        help="Example of how AI might call this tool",
    )

    @api.constrains("code_name")
    def _check_code_name(self):
        for tool in self:
            if not tool.code_name:
                raise UserError(self.env._("Tool code name is required."))

    def get_tool_definition(self):
        self.ensure_one()

        try:
            raw_schema = json.loads(self.parameters_schema)
        except (json.JSONDecodeError, ValueError):
            raw_schema = {}

        if isinstance(raw_schema, dict) and isinstance(
            raw_schema.get("parameters"), dict
        ):
            parameters = raw_schema.get("parameters")
        elif isinstance(raw_schema, dict):
            parameters = raw_schema
        else:
            parameters = {}

        if parameters.get("type") != "object":
            _logger.warning(
                "Tool %s has non-object schema type (%s). Forcing object schema.",
                self.code_name,
                parameters.get("type"),
            )
            parameters["type"] = "object"

        if not isinstance(parameters.get("properties"), dict):
            parameters["properties"] = {}

        if not isinstance(parameters.get("required"), list):
            parameters["required"] = []

        return {
            "name": self.code_name,
            "description": self.description,
            "parameters": parameters,
        }

    def execute(self, room, params, conversation):
        self.ensure_one()

        _logger.info("Executing tool %s with params: %s", self.code_name, params)

        try:
            result = self._execute_python(room, params, conversation)
            return result or {"success": True}

        except Exception as e:
            _logger.error("Error executing tool %s: %s", self.code_name, e)
            return {"error": str(e), "success": False}

    def _execute_python(self, room, params, conversation):
        code_to_execute = self.python_code
        if not code_to_execute:
            raise UserError(self.env._("No Python code defined"))

        agent = room.ai_agent_id if room else self.env["chatroom.ai.agent"]
        env = self.env

        eval_context = {
            "env": env,
            "room": room,
            "room_id": room.id if room else False,
            "params": params,
            "conversation": room,
            "conversation_id": room.id if room else False,
            "agent": agent,
            "agent_id": agent.id if agent else False,
            "json": json,
            "fields": fields,
            "UserError": UserError,
            "_logger": _logger,
        }

        exec(code_to_execute, eval_context)

        return eval_context.get("result", {"success": True})

    def action_test_tool(self):
        self.ensure_one()

        default_agent = (
            self.agent_ids[:1]
            if self.agent_ids
            else self.env["chatroom.ai.agent"].search([("active", "=", True)], limit=1)
        )

        default_room = self.env["chatroom.room"].search(
            [("state", "!=", "closed")], limit=1
        )

        wizard = self.env["chatroom.ai.tool.test.wizard"].create(
            {
                "tool_id": self.id,
                "agent_id": default_agent.id if default_agent else False,
                "room_id": default_room.id if default_room else False,
                "test_params": "{}",
            }
        )

        return {
            "type": "ir.actions.act_window",
            "name": f"Test Tool: {self.name}",
            "res_model": "chatroom.ai.tool.test.wizard",
            "res_id": wizard.id,
            "view_mode": "form",
            "target": "new",
        }
