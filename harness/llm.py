"""LLM provider boundary.

Every model call in this harness goes through ``call_llm(prompt, tools)``.
Swap the body of ``call_llm`` (or set ``LLM_MODEL``) without touching
``run_eval.py`` scoring or the MCP loop.

Default: gemini-3.7-flash via Google AI Studio (``GEMINI_API_KEY``), temperature 0.
``gemini-1.5-flash`` and ``gemini-2.5-flash`` 404 for new AI Studio keys; override with ``LLM_MODEL``.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Any


DEFAULT_MODEL = os.environ.get("LLM_MODEL", "gemini-3.7-flash")
DEFAULT_TEMPERATURE = 0.0


@dataclass
class ToolCall:
    name: str
    args: dict[str, Any]


@dataclass
class LLMTurn:
    text: str
    tool_calls: list[ToolCall] = field(default_factory=list)


class LLMError(RuntimeError):
    """Raised when the provider cannot be reached or is misconfigured."""


def _sanitize_schema(schema: Any) -> Any:
    """Narrow JSON Schema to the subset google.generativeai accepts.

    Jaeger MCP advertises nullable unions such as ``span_ids: ["null",
    "array"]``. The old Gemini SDK does ``type.upper()`` and crashes on a list.
    """
    if not isinstance(schema, dict):
        return schema
    out: dict[str, Any] = {}
    for key, value in schema.items():
        if key not in {"type", "properties", "required", "description", "items", "enum"}:
            continue
        if key == "type" and isinstance(value, list):
            non_null = [item for item in value if item != "null"]
            out["type"] = non_null[0] if non_null else "string"
        elif key == "properties" and isinstance(value, dict):
            out["properties"] = {name: _sanitize_schema(prop) for name, prop in value.items()}
        elif key == "items":
            out["items"] = _sanitize_schema(value)
        else:
            out[key] = value
    if "type" not in out and "properties" in out:
        out["type"] = "object"
    return out


def _gemini_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    declarations = []
    for tool in tools:
        parameters = tool.get("parameters") or tool.get("inputSchema") or {
            "type": "object",
            "properties": {},
        }
        if isinstance(parameters, dict):
            parameters = _sanitize_schema(parameters)
            if "type" not in parameters:
                parameters["type"] = "object"
        declarations.append(
            {
                "name": tool["name"],
                "description": tool.get("description") or "",
                "parameters": parameters,
            }
        )
    return [{"function_declarations": declarations}] if declarations else []


def call_llm(
    prompt: str | list[dict[str, Any]],
    tools: list[dict[str, Any]],
    *,
    chat: Any | None = None,
    system: str | None = None,
) -> tuple[LLMTurn, Any]:
    """Send ``prompt`` to the configured model with optional MCP tool schemas.

    ``prompt`` is a user string on the first turn, or a function-response
    payload on subsequent turns. ``tools`` is a list of
    ``{name, description, parameters|inputSchema}`` dicts (Jaeger MCP shapes).

    Returns ``(LLMTurn, chat)``. Pass ``chat`` back in on the next turn to
    keep the conversation. Temperature is always 0.
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise LLMError(
            "GEMINI_API_KEY is not set. Export a Google AI Studio key "
            "before running the harness."
        )

    try:
        import google.generativeai as genai
    except ImportError as exc:
        raise LLMError(
            "google-generativeai is not installed. "
            "Run: pip install -r harness/requirements.txt"
        ) from exc

    genai.configure(api_key=api_key)

    if chat is None:
        model = genai.GenerativeModel(
            model_name=DEFAULT_MODEL,
            tools=_gemini_tools(tools) or None,
            generation_config=genai.GenerationConfig(temperature=DEFAULT_TEMPERATURE),
            system_instruction=system,
        )
        chat = model.start_chat(enable_automatic_function_calling=False)

    last_exc: Exception | None = None
    for attempt in range(4):
        try:
            response = chat.send_message(prompt)
            last_exc = None
            break
        except Exception as exc:  # provider / network / safety
            last_exc = exc
            msg = str(exc)
            if "429" in msg and "PerDay" not in msg and attempt < 3:
                delay = 20 * (attempt + 1)
                print(f"LLM 429; retrying in {delay}s (attempt {attempt + 1}/3)", flush=True)
                time.sleep(delay)
                continue
            raise LLMError(f"{DEFAULT_MODEL} request failed: {exc}") from exc
    if last_exc is not None:
        raise LLMError(f"{DEFAULT_MODEL} request failed: {last_exc}") from last_exc

    text_parts: list[str] = []
    tool_calls: list[ToolCall] = []
    candidates = getattr(response, "candidates", None) or []
    if not candidates:
        return LLMTurn(text=(getattr(response, "text", None) or "").strip()), chat

    for part in candidates[0].content.parts:
        function_call = getattr(part, "function_call", None)
        if function_call and getattr(function_call, "name", ""):
            args = {}
            raw_args = getattr(function_call, "args", None) or {}
            try:
                args = {k: _coerce(v) for k, v in raw_args.items()}
            except Exception:
                args = dict(raw_args)
            tool_calls.append(ToolCall(name=function_call.name, args=args))
        elif getattr(part, "text", None):
            text_parts.append(part.text)

    text = "".join(text_parts).strip()
    if not text and not tool_calls:
        try:
            text = (response.text or "").strip()
        except Exception:
            text = ""
    return LLMTurn(text=text, tool_calls=tool_calls), chat


def function_response_prompt(name: str, result: str) -> list[dict[str, Any]]:
    """Build the follow-up payload ``call_llm`` expects after a tool call."""
    return [
        {
            "function_response": {
                "name": name,
                "response": {"result": result},
            }
        }
    ]


def _coerce(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _coerce(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_coerce(v) for v in value]
    if isinstance(value, (str, bytes, int, float, bool)) or value is None:
        return value
    if hasattr(value, "items"):
        try:
            return {k: _coerce(v) for k, v in value.items()}
        except Exception:
            pass
    if hasattr(value, "__iter__"):
        try:
            return [_coerce(v) for v in list(value)]
        except TypeError:
            pass
    return str(value)
