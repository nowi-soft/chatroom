from unittest import SkipTest

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase
from odoo.tools import mute_logger


class TestChatroomAITool(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        selection = cls.env["chatroom.ai.provider"]._fields["provider_type"].selection
        selection_keys = {item[0] for item in selection}
        if "openai" not in selection_keys:
            raise SkipTest("openai provider type not available in chatroom_ai stage")

        cls.provider = cls.env["chatroom.ai.provider"].create(
            {
                "name": "Provider",
                "provider_type": "openai",
                "state": "active",
                "default_model": "test-model",
            }
        )
        cls.agent = cls.env["chatroom.ai.agent"].create(
            {
                "name": "Tool Agent",
                "provider_id": cls.provider.id,
                "system_prompt": "Prompt",
            }
        )
        cls.room = cls.env["chatroom.room"].create({"name": "Tool Room"})
        cls.conversation = cls.env["chatroom.ai.conversation"].create(
            {
                "agent_id": cls.agent.id,
                "room_id": cls.room.id,
            }
        )

    def test_tool_definition_normalizes_schema(self):
        tool = self.env["chatroom.ai.tool"].create(
            {
                "name": "Normalize",
                "code_name": "normalize_tool",
                "description": "desc",
                "parameters_schema": '{"foo": 1}',
                "implementation_type": "python",
                "python_code": "result = {'success': True}",
            }
        )

        with mute_logger("odoo.addons.chatroom_ai.models.chatroom_ai_tool"):
            definition = tool.get_tool_definition()
        self.assertEqual(definition["name"], "normalize_tool")
        self.assertEqual(definition["parameters"]["type"], "object")
        self.assertIsInstance(definition["parameters"]["properties"], dict)

    def test_execute_python(self):
        tool = self.env["chatroom.ai.tool"].create(
            {
                "name": "Exec",
                "code_name": "exec_tool",
                "description": "desc",
                "parameters_schema": '{"type": "object", "properties": {}}',
                "implementation_type": "python",
                "python_code": "result = {'success': True, 'value': params.get('x')}",
            }
        )

        result = tool.execute(self.room, {"x": 99}, self.conversation)
        self.assertEqual(result["value"], 99)
        self.assertGreaterEqual(tool.execution_count, 1)

    def test_execute_model_method_missing(self):
        model = self.env["ir.model"]._get("chatroom.room")
        tool = self.env["chatroom.ai.tool"].create(
            {
                "name": "ModelMethod",
                "code_name": "model_method_tool",
                "description": "desc",
                "parameters_schema": '{"type": "object"}',
                "implementation_type": "model_method",
                "model_id": model.id,
                "method_name": "not_existing_method",
            }
        )

        result = tool.execute(self.room, {}, self.conversation)
        self.assertFalse(result["success"])
        self.assertIn("error", result)

    def test_copy_source_to_implementation(self):
        tool = self.env["chatroom.ai.tool"].create(
            {
                "name": "Copy",
                "code_name": "copy_tool",
                "description": "desc",
                "parameters_schema": '{"type": "object"}',
                "implementation_type": "python",
                "python_code_source": "result = {'success': True}",
                "python_code": "",
            }
        )

        action = tool.action_copy_source_to_implementation()
        self.assertIn("result", tool.python_code)
        self.assertEqual(action["tag"], "display_notification")

    def test_copy_source_requires_python_tool(self):
        tool = self.env["chatroom.ai.tool"].create(
            {
                "name": "BadCopy",
                "code_name": "bad_copy_tool",
                "description": "desc",
                "parameters_schema": '{"type": "object"}',
                "implementation_type": "server_action",
            }
        )

        with self.assertRaises(UserError):
            tool.action_copy_source_to_implementation()
