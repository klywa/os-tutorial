"""Model transports. Each call consumes the prompt rendered by the node verbatim."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from urllib import error, parse, request


TIMEOUT = 300


class _DirectEndpoint(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # A redirected request must not carry the document or API credentials.
        return None


def _json_bytes(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")


def _post(url, headers, body):
    req = request.Request(url, data=_json_bytes(body),
                          headers={"Content-Type": "application/json", **headers})
    try:
        with request.build_opener(_DirectEndpoint()).open(req, timeout=TIMEOUT) as response:
            return json.load(response)
    except error.HTTPError as exc:
        # Error bodies can echo authorization data or a full knowledge document.
        raise RuntimeError(f"模型 API 返回 HTTP {exc.code} ({exc.reason})") from None


def _codex(model, prompt):
    binary = shutil.which("codex")
    if not binary:
        raise ValueError("找不到 codex CLI；请检查 PATH。")
    with tempfile.TemporaryDirectory(prefix="wxq-codex-") as directory:
        reply = Path(directory) / "response.txt"
        command = [binary, "exec", "--ephemeral", "--ignore-user-config",
                   "--skip-git-repo-check", "--sandbox", "read-only",
                   "--disable", "shell_tool", "--disable", "unified_exec",
                   "--disable", "apps", "--disable", "plugins",
                   "-c", 'web_search="disabled"', "-c", 'approval_policy="never"',
                   "--json", "-o", str(reply)]
        if model != "default":
            command.extend(["--model", model])
        command.append("-")
        proc = subprocess.run(command, input=prompt.encode(), cwd=directory,
                              capture_output=True, timeout=TIMEOUT)
        if proc.returncode:
            raise RuntimeError(f"Codex CLI 调用失败（退出码 {proc.returncode}）；请检查 codex login status、模型名称与网络。")
        for line in proc.stdout.splitlines():
            event = json.loads(line)
            item = event.get("item", {})
            if item.get("type") in {"command_execution", "mcp_tool_call", "web_search",
                                    "file_change", "collab_tool_call", "dynamic_tool_call"}:
                raise RuntimeError("Codex 节点发起了工具调用，已拒绝本次结果。")
        return reply.read_text(encoding="utf-8")


def _gemini(model, prompt):
    key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if key:
        model_path = parse.quote(model.removeprefix("models/"), safe="")
        envelope = _post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model_path}:generateContent",
            {"x-goog-api-key": key},
            {"contents": [{"parts": [{"text": prompt}]}],
             "generationConfig": {"responseMimeType": "application/json"}},
        )
        candidates = envelope.get("candidates", [])
        if candidates and candidates[0].get("finishReason") == "STOP":
            return "".join(p["text"] for p in candidates[0]["content"]["parts"]
                           if "text" in p and not p.get("thought"))
        raise RuntimeError("Gemini 未返回完整回答。")
    binary = shutil.which("gemini-api")
    if not binary:
        raise ValueError("请设置 GEMINI_API_KEY 或配置 gemini-api CLI。")
    body = {"model": model, "input": prompt, "store": False,
            "response_format": {"type": "text", "mime_type": "application/json"}}
    proc = subprocess.run([binary, "generate", "--body", "@-", "--stream=false",
                           "--output-format", "json", "--no-interactive",
                           "--timeout", f"{TIMEOUT}s"], input=_json_bytes(body),
                          capture_output=True, timeout=TIMEOUT + 5)
    if proc.returncode:
        raise RuntimeError(f"gemini-api 调用失败（退出码 {proc.returncode}）；请检查登录、额度、模型及网络。")
    envelope = json.loads(proc.stdout)
    if envelope.get("status") != "completed":
        raise RuntimeError("gemini-api 未返回完整回答。")
    parts = envelope.get("outputs", [])
    if "steps" in envelope:
        parts = [p for s in envelope["steps"] if s.get("type") == "model_output"
                 for p in s.get("content", [])]
    return "".join(p["text"] for p in parts if p.get("type") == "text")


def _compatible(model, prompt):
    base = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    key = os.getenv("OPENAI_API_KEY")
    parts = parse.urlsplit(base)
    if parts.scheme != "https" and not (
        parts.scheme == "http" and parts.hostname in {"localhost", "127.0.0.1", "::1"}
    ):
        raise ValueError("OPENAI_BASE_URL 需使用 HTTPS，本地回环地址可使用 HTTP。")
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    envelope = _post(base + "/chat/completions", headers,
                     {"model": model, "messages": [{"role": "user", "content": prompt}]})
    choices = envelope.get("choices", [])
    if not choices or choices[0].get("finish_reason") != "stop":
        raise RuntimeError("兼容 API 未返回完整回答。")
    return choices[0]["message"]["content"]


def generate(provider, model, prompt):
    transports = {"codex": _codex, "gemini": _gemini, "openai": _compatible}
    if provider not in transports:
        raise ValueError("provider 应为 codex、gemini 或 openai")
    result = transports[provider](model, prompt)
    if not isinstance(result, str) or not result.strip():
        raise RuntimeError("模型返回空正文。")
    return result
