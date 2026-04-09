import base64

from odoo.tests.common import TransactionCase


class TestAIKnowledge(TransactionCase):
    def test_process_text_and_html(self):
        text_knowledge = self.env["chatroom.ai.knowledge"].create(
            {
                "name": "Text KB",
                "content_type": "text",
                "content": "plain content",
            }
        )
        text_knowledge.action_process_content()
        self.assertEqual(text_knowledge.processing_status, "success")
        self.assertEqual(text_knowledge.processed_content, "plain content")

        html_knowledge = self.env["chatroom.ai.knowledge"].create(
            {
                "name": "Html KB",
                "content_type": "html",
                "content": "<p>Hello <b>world</b></p>",
            }
        )
        html_knowledge.action_process_content()
        self.assertEqual(html_knowledge.processing_status, "success")
        self.assertIn("Hello", html_knowledge.processed_content)

    def test_process_file_and_format(self):
        file_knowledge = self.env["chatroom.ai.knowledge"].create(
            {
                "name": "File KB",
                "description": "desc",
                "content_type": "file",
                "file_name": "sample.txt",
                "file": base64.b64encode(b"line 1\nline 2").decode("ascii"),
            }
        )

        file_knowledge.action_process_content()
        self.assertEqual(file_knowledge.processing_status, "success")
        self.assertIn("line 1", file_knowledge.processed_content)
        self.assertGreater(file_knowledge.char_count, 0)

        formatted = file_knowledge.get_formatted_content()
        self.assertIn("Document: File KB", formatted)
        self.assertIn("desc", formatted)

    def test_process_unsupported_file_type(self):
        file_knowledge = self.env["chatroom.ai.knowledge"].create(
            {
                "name": "Bad File",
                "content_type": "file",
                "file_name": "sample.bin",
                "file": base64.b64encode(b"binary").decode("ascii"),
            }
        )

        file_knowledge.action_process_content()
        self.assertEqual(file_knowledge.processing_status, "error")
        self.assertIn("Unsupported file type", file_knowledge.processing_message)
