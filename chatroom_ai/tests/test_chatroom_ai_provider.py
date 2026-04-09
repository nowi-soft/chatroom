from unittest import SkipTest
from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase


class TestChatroomAIProvider(TransactionCase):
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
                "state": "draft",
                "default_model": "test-model",
            }
        )

    def test_action_test_connection_success(self):
        provider_class = type(self.provider)
        with patch.object(
            provider_class,
            "_test_provider_connection",
            autospec=True,
            return_value={"success": True},
        ):
            action = self.provider.action_test_connection()

        self.assertEqual(self.provider.state, "active")
        self.assertEqual(action["tag"], "display_notification")
        self.assertEqual(action["params"]["type"], "success")

    def test_action_test_connection_error(self):
        provider_class = type(self.provider)
        with patch.object(
            provider_class,
            "_test_provider_connection",
            autospec=True,
            return_value={"success": False, "error": "boom"},
        ):
            action = self.provider.action_test_connection()

        self.assertEqual(self.provider.state, "error")
        self.assertEqual(action["params"]["type"], "danger")

    def test_generate_completion_requires_active_state(self):
        self.provider.state = "draft"
        with self.assertRaises(UserError):
            self.provider.generate_completion(messages=[{"role": "user", "content": "hi"}])

    def test_generate_completion_updates_stats(self):
        self.provider.state = "active"
        provider_class = type(self.provider)
        with patch.object(
            provider_class,
            "_generate_completion_impl",
            autospec=True,
            return_value={
                "content": "ok",
                "usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
            },
        ):
            result = self.provider.generate_completion(
                messages=[{"role": "user", "content": "hello"}],
                model="model-a",
            )

        self.assertEqual(result["content"], "ok")
        self.assertGreaterEqual(self.provider.total_requests, 1)
        self.assertGreaterEqual(self.provider.total_tokens_used, 3)
