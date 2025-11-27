"""OpenAI Provider Implementation"""

import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class ChatroomAIProvider(models.Model):
    _inherit = "chatroom.ai.provider"

    provider_type = fields.Selection(
        selection_add=[("openai", "OpenAI")],
        ondelete={"openai": "cascade"},
    )

    def _test_provider_connection(self):
        if self.provider_type != "openai":
            return super()._test_provider_connection()

        try:
            import openai

            client = openai.OpenAI(
                api_key=self.api_key,
                base_url=self.api_base_url if self.api_base_url else None,
                organization=self.organization_id if self.organization_id else None,
            )

            test_params = {
                "model": self.default_model or "gpt-3.5-turbo",
                "messages": [{"role": "user", "content": "Hi"}],
            }

            model_name = test_params["model"].lower()
            uses_completion_tokens = (
                "4o" in model_name
                or "gpt-4" in model_name
                or "gpt-5" in model_name
                or "o1" in model_name
                or "o3" in model_name
            )

            if uses_completion_tokens:
                test_params["max_completion_tokens"] = 5
            else:
                test_params["max_tokens"] = 5

            response = client.chat.completions.create(**test_params)

            return {"success": True, "response": response}

        except ImportError:
            return {
                "success": False,
                "error": (
                    "openai package not installed. Install with: pip install openai"
                ),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _generate_completion_impl(
        self, messages, model, temperature, max_tokens, tools=None, **kwargs
    ):
        if self.provider_type != "openai":
            return super()._generate_completion_impl(
                messages, model, temperature, max_tokens, tools, **kwargs
            )

        try:
            import openai

            client = openai.OpenAI(
                api_key=self.api_key,
                base_url=self.api_base_url if self.api_base_url else None,
                organization=self.organization_id if self.organization_id else None,
            )

            params = {
                "model": model,
                "messages": messages,
            }

            model_lower = model.lower()
            is_reasoning_model = (
                "gpt-5" in model_lower or "o1" in model_lower or "o3" in model_lower
            )
            uses_completion_tokens = (
                "4o" in model_lower
                or "gpt-4" in model_lower
                or "gpt-5" in model_lower
                or "o1" in model_lower
                or "o3" in model_lower
            )

            if not is_reasoning_model:
                params["temperature"] = temperature

            # Only set max_tokens if specified (0 means use OpenAI's default)
            if max_tokens:
                if uses_completion_tokens:
                    params["max_completion_tokens"] = max_tokens
                else:
                    params["max_tokens"] = max_tokens

            if tools:
                params["tools"] = tools
                params["tool_choice"] = "auto"

            response = client.chat.completions.create(**params)

            choice = response.choices[0]
            message = choice.message

            result = {
                "content": message.content or "",
                "model": response.model,
                "usage": {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens,
                },
            }

            if hasattr(message, "tool_calls") and message.tool_calls:
                result["tool_calls"] = []
                for tool_call in message.tool_calls:
                    result["tool_calls"].append(
                        {
                            "id": tool_call.id,
                            "type": "function",
                            "function": {
                                "name": tool_call.function.name,
                                "arguments": tool_call.function.arguments,
                            },
                        }
                    )

            return result

        except Exception as e:
            error_str = str(e)
            if (
                "max_tokens" in error_str.lower()
                and "output limit" in error_str.lower()
            ):
                _logger.error(f"OpenAI API error (max_tokens limit): {error_str}")
                return {
                    "content": "",
                    "model": model,
                    "usage": {
                        "prompt_tokens": 0,
                        "completion_tokens": max_tokens or 0,
                        "total_tokens": max_tokens or 0,
                    },
                    "truncated": True,
                }
            _logger.error(f"OpenAI API error: {error_str}")
            raise

    def format_tool_for_provider(self, tool):
        if self.provider_type != "openai":
            return super().format_tool_for_provider(tool)

        tool_def = tool.get_tool_definition()

        return {
            "type": "function",
            "function": {
                "name": tool_def["name"],
                "description": tool_def["description"],
                "parameters": tool_def["parameters"],
            },
        }

    def transcribe_audio(self, audio_data, mime_type=None):
        if self.provider_type != "openai":
            return (
                super().transcribe_audio(audio_data, mime_type)
                if hasattr(super(), "transcribe_audio")
                else None
            )

        try:
            import base64

            import openai

            client = openai.OpenAI(
                api_key=self.api_key,
                base_url=self.api_base_url if self.api_base_url else None,
                organization=self.organization_id if self.organization_id else None,
            )

            audio_len = len(audio_data) if audio_data else 0
            _logger.info(f"audio_data type: {type(audio_data)}, len: {audio_len}")

            if isinstance(audio_data, str):
                _logger.info("Decoding from string")
                audio_bytes = base64.b64decode(audio_data)
            elif isinstance(audio_data, bytes):
                _logger.info("Already bytes, checking if base64...")
                try:
                    decoded = base64.b64decode(audio_data)
                    if decoded[:4] == b"OggS" or decoded[:4] == b"RIFF":
                        _logger.info("Was base64 encoded bytes, decoded successfully")
                        audio_bytes = decoded
                    else:
                        _logger.info("Already raw bytes")
                        audio_bytes = audio_data
                except Exception:
                    _logger.info("Not base64, using as-is")
                    audio_bytes = audio_data
            else:
                audio_bytes = audio_data

            import tempfile

            extension = "ogg"
            if mime_type:
                if "mp3" in mime_type or "mpeg" in mime_type:
                    extension = "mp3"
                elif "wav" in mime_type:
                    extension = "wav"
                elif "m4a" in mime_type:
                    extension = "m4a"
                elif "webm" in mime_type:
                    extension = "webm"
                elif "flac" in mime_type:
                    extension = "flac"

            with tempfile.NamedTemporaryFile(
                delete=False, suffix=f".{extension}", mode="wb"
            ) as temp_file:
                temp_file.write(audio_bytes)
                temp_file_path = temp_file.name

            _logger.info(
                f"Created temp file: {temp_file_path}, "
                f"size: {len(audio_bytes)}, extension: {extension}"
            )
            _logger.info(f"First 4 bytes: {audio_bytes[:4].hex()}")

            try:
                with open(temp_file_path, "rb") as audio_file:
                    _logger.info(f"Sending to OpenAI: filename={audio_file.name}")
                    response = client.audio.transcriptions.create(
                        model="whisper-1",
                        file=audio_file,
                        language="es",
                    )
                _logger.info("Transcription successful")
                return response.text
            finally:
                import os

                if os.path.exists(temp_file_path):
                    os.unlink(temp_file_path)

        except ImportError:
            _logger.error(
                "openai package not installed. Install with: pip install openai"
            )
            return None
        except Exception as e:
            _logger.error(
                f"OpenAI Whisper transcription error: {str(e)}", exc_info=True
            )
            return None
