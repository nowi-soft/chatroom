import logging

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class ChatroomAIProvider(models.Model):
    _name = "chatroom.ai.provider"
    _description = "AI Provider Configuration"
    _order = "name"

    name = fields.Char(required=True)
    provider_type = fields.Selection(
        [],
        required=True,
    )
    active = fields.Boolean(default=True)

    api_key = fields.Char(groups="chatroom.group_chatroom_manager")
    api_base_url = fields.Char(help="Optional custom endpoint")
    organization_id = fields.Char(help="For providers that support it")

    default_model = fields.Char(
        help="e.g., gpt-4, claude-3-opus-20240229, gemini-pro",
    )
    default_temperature = fields.Float(
        default=0.7,
        help="Controls randomness (0.0 = deterministic, 1.0 = creative)",
    )
    default_max_tokens = fields.Integer(
        default=1000,
        help="Maximum tokens in response (0 = use provider default, min 500)",
    )

    @api.constrains("default_max_tokens")
    def _check_default_max_tokens(self):
        for record in self:
            if record.default_max_tokens < 0:
                raise ValidationError(self.env._("Max tokens cannot be negative."))
            if 0 < record.default_max_tokens < 500:
                raise ValidationError(
                    self.env._(
                        "Max tokens must be at least 500 or 0 to use provider default."
                    )
                )

    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("active", "Active"),
            ("error", "Error"),
        ],
        default="draft",
    )
    error_message = fields.Text("Last Error")
    total_requests = fields.Integer(default=0, readonly=True)
    total_tokens_used = fields.Integer(default=0, readonly=True)
    last_request_date = fields.Datetime(readonly=True)

    extra_config = fields.Json()

    @api.model
    def _get_provider_implementation(self, provider_type):
        return None

    def action_test_connection(self):
        self.ensure_one()
        try:
            result = self._test_provider_connection()
            if result.get("success"):
                self.write({"state": "active", "error_message": False})
                return {
                    "type": "ir.actions.client",
                    "tag": "display_notification",
                    "params": {
                        "message": "Connection successful!",
                        "type": "success",
                        "sticky": False,
                        "next": {"type": "ir.actions.act_window_close"},
                    },
                }
            else:
                self.write({"state": "error", "error_message": result.get("error")})
                return {
                    "type": "ir.actions.client",
                    "tag": "display_notification",
                    "params": {
                        "message": f"Connection failed: {result.get('error')}",
                        "type": "danger",
                        "sticky": True,
                        "next": {"type": "ir.actions.act_window_close"},
                    },
                }
        except Exception as e:
            error_msg = str(e)
            self.write({"state": "error", "error_message": error_msg})
            raise UserError(self.env._("Connection test failed: %s", error_msg)) from e

    def _test_provider_connection(self):
        raise NotImplementedError("Provider must implement _test_provider_connection")

    def generate_completion(
        self,
        messages,
        model=None,
        temperature=None,
        max_tokens=None,
        tools=None,
        **kwargs,
    ):
        self.ensure_one()

        if self.state != "active":
            raise UserError(
                self.env._("Provider is not active. Test connection first.")
            )

        model = model or self.default_model
        temperature = (
            temperature if temperature is not None else self.default_temperature
        )
        max_tokens = max_tokens or self.default_max_tokens

        try:
            result = self._generate_completion_impl(
                messages=messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                tools=tools,
                **kwargs,
            )

            usage = result.get("usage", {})
            self.sudo().write(
                {
                    "total_requests": self.total_requests + 1,
                    "total_tokens_used": self.total_tokens_used
                    + usage.get("total_tokens", 0),
                    "last_request_date": fields.Datetime.now(),
                }
            )

            return result

        except Exception as e:
            _logger.error(f"AI completion failed: {str(e)}")
            self.write({"error_message": str(e)})
            raise

    def _generate_completion_impl(
        self, messages, model, temperature, max_tokens, tools=None, **kwargs
    ):
        raise NotImplementedError("Provider must implement _generate_completion_impl")

    def format_tool_for_provider(self, tool):
        raise NotImplementedError("Provider must implement format_tool_for_provider")
