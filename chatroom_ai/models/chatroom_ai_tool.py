import json
import logging

from markupsafe import Markup

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools import misc

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

    implementation_type = fields.Selection(
        [
            ("python", "Python Code"),
            ("model_method", "Model Method"),
            ("server_action", "Server Action"),
        ],
        required=True,
        default="python",
    )

    python_code = fields.Text(
        string="Implementation Code",
        help="""Python code to execute. Available variables:
- env: Odoo environment
- room: chatroom.room record
- params: dict of parameters from AI
- conversation: chatroom.ai.conversation record
- agent: chatroom.ai.agent record

Must return a dict with result information.""",
    )
    python_code_source = fields.Text(
        string="Module Source Code",
        help=(
            "Code distributed from module data. This is updateable by module "
            "upgrades and acts as the reference source."
        ),
    )
    python_code_diff_html = fields.Html(
        string="Source vs Implementation Diff",
        compute="_compute_python_code_diff_html",
        sanitize=False,
        readonly=True,
    )
    python_code_in_sync = fields.Boolean(
        string="Implementation In Sync",
        compute="_compute_python_code_diff_html",
        readonly=True,
    )

    model_id = fields.Many2one("ir.model")
    method_name = fields.Char()

    server_action_id = fields.Many2one("ir.actions.server")

    agent_ids = fields.Many2many(
        "chatroom.ai.agent",
        "chatroom_ai_agent_tool_rel",
        "tool_id",
        "agent_id",
    )
    execution_count = fields.Integer(default=0, readonly=True)
    last_execution = fields.Datetime(readonly=True)

    example_usage = fields.Text(
        help="Example of how AI might call this tool",
    )

    @api.constrains("code_name")
    def _check_code_name(self):
        for tool in self:
            if not tool.code_name.replace("_", "").isalnum():
                raise UserError(
                    self.env._(
                        "Code name must contain only letters, numbers, and underscores"
                    )
                )

    @api.model_create_multi
    def create(self, vals_list):
        # Keep backward compatibility: first install should still have executable
        # implementation even if only module source is provided by data files.
        for vals in vals_list:
            source = vals.get("python_code_source")
            if source and not vals.get("python_code"):
                vals["python_code"] = source
        return super().create(vals_list)

    def write(self, vals):
        has_source_update = "python_code_source" in vals
        result = super().write(vals)

        # During upgrades, never override tenant-custom implementation.
        # But if implementation is empty, seed it from source automatically.
        if has_source_update:
            for tool in self:
                if not tool.python_code and tool.python_code_source:
                    super(ChatroomAITool, tool).write(
                        {"python_code": tool.python_code_source}
                    )

        return result

    @api.depends("python_code_source", "python_code")
    def _compute_python_code_diff_html(self):
        for tool in self:
            source_text = tool.python_code_source or ""
            implementation_text = tool.python_code or ""
            tool.python_code_in_sync = source_text == implementation_text

            if tool.python_code_in_sync:
                tool.python_code_diff_html = Markup(
                    "<p><strong>No differences.</strong> "
                    "Implementation is identical to module source.</p>"
                )
                continue

            table = misc.get_diff(
                (source_text, "Module source"),
                (implementation_text, "Implementation"),
            )
            tool.python_code_diff_html = Markup(table)

    def action_copy_source_to_implementation(self):
        self.ensure_one()
        if self.implementation_type != "python":
            raise UserError(self.env._("Copy is only available for Python tools."))

        if not self.python_code_source:
            raise UserError(self.env._("No module source code available to copy."))

        self.write({"python_code": self.python_code_source})
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": self.env._("Source Copied"),
                "message": self.env._(
                    "Module source code has been copied to implementation."
                ),
                "type": "success",
                "sticky": False,
            },
        }

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

        _logger.info(f"Executing tool {self.code_name} with params: {params}")

        try:
            result = None

            if self.implementation_type == "python":
                result = self._execute_python(room, params, conversation)

            elif self.implementation_type == "model_method":
                result = self._execute_model_method(room, params, conversation)

            elif self.implementation_type == "server_action":
                result = self._execute_server_action(room, params, conversation)

            self.sudo().write(
                {
                    "execution_count": self.execution_count + 1,
                    "last_execution": fields.Datetime.now(),
                }
            )

            return result or {"success": True}

        except Exception as e:
            _logger.error(f"Error executing tool {self.code_name}: {str(e)}")
            return {"error": str(e), "success": False}

    def _execute_python(self, room, params, conversation):
        code_to_execute = self.python_code or self.python_code_source
        if not code_to_execute:
            raise UserError(self.env._("No Python code defined"))

        agent = conversation.agent_id
        env = self.env

        eval_context = {
            "env": env,
            "room": room,
            "room_id": room.id if room else False,
            "params": params,
            "conversation": conversation,
            "conversation_id": conversation.id if conversation else False,
            "agent": agent,
            "agent_id": agent.id if agent else False,
            "json": json,
            "fields": fields,
            "UserError": UserError,
            "_logger": _logger,
        }

        exec(code_to_execute, eval_context)

        return eval_context.get("result", {"success": True})

    def _execute_model_method(self, room, params, conversation):
        if not self.model_id or not self.method_name:
            raise UserError(self.env._("Model and method name required"))

        model = self.env[self.model_id.model]
        method = getattr(model, self.method_name, None)

        if not method:
            raise UserError(
                self.env._(
                    "Method %(method)s not found on %(model)s",
                    method=self.method_name,
                    model=self.model_id.model,
                )
            )

        return method(room=room, params=params, conversation=conversation)

    def _execute_server_action(self, room, params, conversation):
        if not self.server_action_id:
            raise UserError(self.env._("No server action defined"))

        return self.server_action_id.with_context(
            active_id=room.id,
            active_model="chatroom.room",
            tool_params=params,
            conversation_id=conversation.id,
        ).run()

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
