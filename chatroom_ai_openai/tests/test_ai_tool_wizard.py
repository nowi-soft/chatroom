from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase


class TestAIToolWizard(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.provider = cls.env["chatroom.ai.provider"].create(
            {
                "name": "OpenAI Provider Wizard",
                "provider_type": "openai",
                "state": "active",
                "default_model": "gpt-4o-mini",
                "api_key": "test-key",
            }
        )
        cls.agent = cls.env["chatroom.ai.agent"].create(
            {
                "name": "Wizard Agent",
                "provider_id": cls.provider.id,
                "system_prompt": "Prompt",
            }
        )
        cls.tool = cls.env["chatroom.ai.tool"].create(
            {
                "name": "Wizard Tool",
                "code_name": "wizard_tool",
                "description": "desc",
                "parameters_schema": '{"type": "object"}',
                "python_code": "result = {'success': True, 'from_wizard': True}",
            }
        )

    def test_action_run_test_with_valid_json(self):
        wizard = self.env["chatroom.ai.tool.test.wizard"].create(
            {
                "tool_id": self.tool.id,
                "agent_id": self.agent.id,
                "test_params": '{"x": 1}',
            }
        )

        action = wizard.action_run_test()
        self.assertEqual(action["type"], "ir.actions.act_window")
        self.assertEqual(wizard.state, "done")
        self.assertIn("from_wizard", wizard.result)

    def test_action_run_test_invalid_json(self):
        wizard = self.env["chatroom.ai.tool.test.wizard"].create(
            {
                "tool_id": self.tool.id,
                "agent_id": self.agent.id,
                "test_params": "{bad",
            }
        )

        with self.assertRaises(UserError):
            wizard.action_run_test()
