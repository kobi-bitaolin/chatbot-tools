"""The LLM client: Google Gemini through the `google-genai` SDK (spec v0.7, D9).

This is the only code that knows Gemini's format (FR-37). The chat service
speaks one internal format:
- messages: `{"role": "user" | "assistant", "content": str | [blocks]}`
- blocks: `text`, `thinking`, `tool_use {id, name, input}`,
  `tool_result {tool_use_id, content, is_error?}`
and gets back a neutral `LLMResult` (or an `LLMUnavailableError`), never SDK
objects. So switching provider means changing this file and two settings.

It gets plain values (key, model), not the app's Settings, so it doesn't
depend on the rest of the app (NFR-12). app/main.py does the wiring.
Tests swap this class for the fake LLM in tests/fake_llm.py.
"""

import base64
import json

import httpx
from google import genai
from google.genai import errors, types

from app.llm.result import LLMResult, LLMToolCall, LLMUnavailableError

MAX_TOKENS = 16_000  # FR-36

# Internal tool choice → Gemini function-calling mode (FR-10, FR-15).
TOOL_MODES = {"auto": "AUTO", "none": "NONE"}

# Gemini finish reason → internal stop reason (FR-37). Anything else keeps its
# own name, which the chat service treats as unexpected (FR-26).
STOP_REASONS = {
    "STOP": "end_turn",
    "MAX_TOKENS": "max_tokens",
    "SAFETY": "refusal",
    "PROHIBITED_CONTENT": "refusal",
    "BLOCKLIST": "refusal",
    "SPII": "refusal",
}


class LLMClient:
    def __init__(self, api_key: str | None, model: str, sdk=None):
        """`sdk` replaces the real `genai.Client` (tests pass a recording stub)."""
        self._api_key = api_key
        self._model = model
        self._sdk = sdk

    def _client(self):
        # Created on first use, not at startup, so the app (and the tests)
        # start without an API key (AC-47).
        if self._sdk is None:
            if not self._api_key:
                raise LLMUnavailableError("GEMINI_API_KEY is not configured")
            self._sdk = genai.Client(api_key=self._api_key)
        return self._sdk

    def complete(self, system: str, messages: list, tools: list, tool_choice: dict) -> LLMResult:
        """One LLM call. Any failure is raised as LLMUnavailableError (FR-25)."""
        config = types.GenerateContentConfig(
            system_instruction=system,
            max_output_tokens=MAX_TOKENS,
        )
        if tools:
            config.tools = [types.Tool(function_declarations=[to_declaration(t) for t in tools])]
            config.tool_config = types.ToolConfig(
                function_calling_config=types.FunctionCallingConfig(mode=TOOL_MODES[tool_choice["type"]])
            )
        try:
            response = self._client().models.generate_content(
                model=self._model, contents=to_contents(messages), config=config
            )
        except (errors.APIError, httpx.HTTPError) as exc:
            # HTTP errors (429, 5xx, ...) after the SDK's retries, or no connection at all.
            raise LLMUnavailableError(str(exc)) from exc
        return to_llm_result(response)


# ---------------------------------------------------------------- out: to Gemini


def to_declaration(tool: dict) -> types.FunctionDeclaration:
    """FR-33: the internal `input_schema` goes to Gemini unchanged."""
    return types.FunctionDeclaration(
        name=tool["name"], description=tool["description"], parameters_json_schema=tool["input_schema"]
    )


def to_contents(messages: list) -> list[types.Content]:
    """Internal messages → Gemini Contents (FR-37)."""
    tool_names = {}  # tool_use id → tool name; Gemini wants the name on each result too
    contents = []
    for message in messages:
        role = "model" if message["role"] == "assistant" else "user"
        blocks = message["content"]
        if isinstance(blocks, str):
            parts = [types.Part(text=blocks)]
        else:
            for block in blocks:
                if block["type"] == "tool_use":
                    tool_names[block["id"]] = block["name"]
            # All blocks of one message go in one Content: a round's results
            # are sent together (FR-13).
            parts = [to_part(block, tool_names) for block in blocks]
        contents.append(types.Content(role=role, parts=parts))
    return contents


def to_part(block: dict, tool_names: dict) -> types.Part:
    kind = block["type"]
    if kind == "text":
        part = types.Part(text=block["text"])
    elif kind == "thinking":
        part = types.Part(text=block["thinking"], thought=True)
    elif kind == "tool_use":
        part = types.Part(
            function_call=types.FunctionCall(id=block["id"], name=block["name"], args=block["input"])
        )
    elif kind == "tool_result":
        if block.get("is_error"):
            response = {"error": block["content"]}
        else:
            response = {"result": parse_json(block["content"])}
        # Built directly: `Part.from_function_response` in google-genai 3.0.0
        # takes no `id`, and the id is what pairs a result with its call.
        part = types.Part(
            function_response=types.FunctionResponse(
                id=block["tool_use_id"], name=tool_names.get(block["tool_use_id"], ""), response=response
            )
        )
    else:
        raise ValueError(f"Unknown block type: {kind}")
    if "signature" in block:
        # A3: the signature goes back on the same part, byte for byte.
        part.thought_signature = base64.b64decode(block["signature"])
    return part


def parse_json(text: str):
    """Tool outputs are stored as JSON text; Gemini takes them as a JSON value."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


# --------------------------------------------------------------- in: from Gemini


def to_llm_result(response: types.GenerateContentResponse) -> LLMResult:
    """A Gemini response → the neutral LLMResult (AC-60, AC-63)."""
    usage = response.usage_metadata
    input_tokens = (usage.prompt_token_count or 0) if usage else 0
    output_tokens = ((usage.candidates_token_count or 0) + (usage.thoughts_token_count or 0)) if usage else 0

    if not response.candidates:
        # The prompt itself was blocked: Gemini returns no answer at all.
        return LLMResult(text="", tool_calls=[], stop_reason="refusal",
                         input_tokens=input_tokens, output_tokens=output_tokens, blocks=[])

    candidate = response.candidates[0]
    parts = (candidate.content.parts if candidate.content else None) or []
    blocks = [to_block(part) for part in parts]

    if any(b["type"] == "tool_use" for b in blocks):
        stop_reason = "tool_use"  # Gemini says STOP even when it calls tools
    else:
        name = candidate.finish_reason.name if candidate.finish_reason else "NONE"
        stop_reason = STOP_REASONS.get(name, name)

    return LLMResult(
        text="".join(b["text"] for b in blocks if b["type"] == "text"),
        tool_calls=[
            LLMToolCall(id=b["id"], name=b["name"], input=b["input"]) for b in blocks if b["type"] == "tool_use"
        ],
        stop_reason=stop_reason,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        blocks=blocks,
    )


def to_block(part: types.Part) -> dict:
    if part.function_call:
        call = part.function_call
        block = {"type": "tool_use", "id": call.id, "name": call.name, "input": dict(call.args or {})}
    elif part.thought:
        block = {"type": "thinking", "thinking": part.text or ""}
    else:
        block = {"type": "text", "text": part.text or ""}
    if part.thought_signature:
        # Bytes can't go into JSON (llm_blocks), so they're stored as base64 text.
        block["signature"] = base64.b64encode(part.thought_signature).decode()
    return block
