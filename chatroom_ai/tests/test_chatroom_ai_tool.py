from odoo.tests.common import TransactionCase
from odoo.tools import mute_logger


class TestChatroomAITool(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        selection = cls.env["chatroom.ai.provider"]._fields["provider_type"].selection
        selection_keys = {item[0] for item in selection}
        if "openai" not in selection_keys:
            raise Exception("openai provider type not available")

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
        cls.conversation = cls.room  # room holds AI context directly

    def test_tool_definition_normalizes_schema(self):
        tool = self.env["chatroom.ai.tool"].create(
            {
                "name": "Normalize",
                "code_name": "normalize_tool",
                "description": "desc",
                "parameters_schema": '{"foo": 1}',
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
                "python_code": "result = {'success': True, 'value': params.get('x')}",
            }
        )

        result = tool.execute(self.room, {"x": 99}, self.conversation)
        self.assertEqual(result["value"], 99)
        self.assertGreaterEqual(tool.execution_count, 1)
