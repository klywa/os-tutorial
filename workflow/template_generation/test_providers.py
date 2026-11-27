import json
import os
from pathlib import Path
from subprocess import CompletedProcess
import unittest
from unittest.mock import patch

from workflow.template_generation import providers


class ProviderTests(unittest.TestCase):
    def test_codex_receives_exact_prompt_in_empty_directory(self):
        prompt = "正文\n仅返回 JSON。"
        def respond(args, input, cwd, **kwargs):
            self.assertEqual(input, prompt.encode())
            self.assertFalse(list(Path(cwd).iterdir()))
            self.assertIn("read-only", args)
            self.assertNotIn("--model", args)
            Path(args[args.index("-o") + 1]).write_text('{"ok": true}', encoding="utf-8")
            return CompletedProcess(args, 0, b'{"type":"turn.completed"}\n', b"")
        with patch.object(providers.shutil, "which", return_value="codex"), \
                patch.object(providers.subprocess, "run", side_effect=respond):
            self.assertTrue(json.loads(providers.generate("codex", "default", prompt))["ok"])

    def test_gemini_excludes_thought_parts(self):
        envelope = {"candidates": [{"finishReason": "STOP", "content": {"parts": [
            {"thought": True, "text": "scratch"}, {"text": "{}"}]}}]}
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test"}, clear=True), \
                patch.object(providers, "_post", return_value=envelope) as post:
            self.assertEqual(providers.generate("gemini", "model", "原文"), "{}")
            self.assertEqual(post.call_args.args[2]["contents"][0]["parts"][0]["text"], "原文")

    def test_compatible_truncated_response_fails(self):
        with patch.dict(os.environ, {"OPENAI_BASE_URL": "http://127.0.0.1:1234/v1"}, clear=True), \
                patch.object(providers, "_post", return_value={"choices": [{"finish_reason": "length"}]}) as post:
            with self.assertRaisesRegex(RuntimeError, "完整"):
                providers.generate("openai", "model", "原文")
            self.assertEqual(post.call_args.args[2]["messages"], [{"role": "user", "content": "原文"}])

    def test_explicit_endpoint_uses_only_its_own_key(self):
        envelope = {"choices": [{"finish_reason": "stop", "message": {"content": "{}"}}]}
        with patch.dict(os.environ, {"OPENAI_API_KEY": "global", "NODE_TOKEN": "node"}, clear=True), \
                patch.object(providers, "_post", return_value=envelope) as post:
            url = "http://192.168.1.10:8000/v1"
            options = {"base_url": url, "allow_http": True}
            providers.generate("openai", "custom", "原文", **options)
            self.assertEqual(post.call_args.args[:2], (url + "/chat/completions", {}))
            providers.generate("openai", "custom", "原文", api_key_env="NODE_TOKEN", **options)
            self.assertEqual(post.call_args.args[1], {"Authorization": "Bearer node"})
            with self.assertRaisesRegex(ValueError, "MISSING_TOKEN"):
                providers.generate("openai", "custom", "原文", api_key_env="MISSING_TOKEN", **options)
            with self.assertRaisesRegex(ValueError, "HTTPS"):
                providers.generate("openai", "custom", "原文", base_url=url)
            self.assertEqual(post.call_count, 2)
