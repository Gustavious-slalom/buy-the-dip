# backend/app/agent/loop.py
import json
from datetime import datetime, timezone
from anthropic import AsyncAnthropic
from app.config import settings
from app.agent.tools import TOOLS, dispatch
from app.agent.prompts import SYSTEM_PROMPT


def _new_client() -> AsyncAnthropic:
    api_key = settings.anthropic_api_key.strip()
    if api_key:
        return AsyncAnthropic(api_key=api_key)
    # Let the SDK resolve ANTHROPIC_AUTH_TOKEN / credentials providers when no key is set.
    return AsyncAnthropic()

def _evt(type_: str, **data) -> dict:
    return {"type": type_, "ts": datetime.now(timezone.utc).isoformat(), "data": data}

async def run_session(emit, session_id: str, user_message: str) -> None:
    client = _new_client()
    messages = [{"role": "user", "content": user_message}]
    await emit(_evt("agent.status", message=f"Starting analysis for: {user_message}"))

    cached_tools = [
        {**t, "cache_control": {"type": "ephemeral"}} if i == len(TOOLS) - 1 else t
        for i, t in enumerate(TOOLS)
    ]
    cached_system = [{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}]

    for _ in range(12):  # safety cap
        # Stream the assistant turn token-by-token so the UI renders in real time.
        try:
            async with client.messages.stream(
                model=settings.anthropic_model,
                max_tokens=2048,
                system=cached_system,
                tools=cached_tools,
                messages=messages,
            ) as stream:
                async for delta in stream.text_stream:
                    await emit(_evt("agent.thinking", delta=delta))
                final = await stream.get_final_message()
        except Exception as e:
            msg = str(e)
            if "Could not resolve authentication method" in msg:
                await emit(_evt(
                    "agent.error",
                    message=(
                        "Anthropic authentication is not configured. Set ANTHROPIC_API_KEY, "
                        "ANTHROPIC_AUTH_TOKEN, or credentials in your environment."
                    ),
                ))
                return
            await emit(_evt("agent.error", message=msg))
            return

        assistant_blocks = []
        tool_uses = []
        for block in final.content:
            btype = getattr(block, "type", None)
            if btype == "text":
                assistant_blocks.append({"type": "text", "text": block.text})
            elif btype == "tool_use":
                await emit(_evt("agent.tool_call",
                                tool_use_id=block.id, name=block.name, input=block.input))
                tool_uses.append(block)
                assistant_blocks.append({"type": "tool_use", "id": block.id,
                                         "name": block.name, "input": block.input})

        messages.append({"role": "assistant", "content": assistant_blocks})

        if final.stop_reason != "tool_use":
            await emit(_evt("agent.complete"))
            return

        tool_results = []
        for tu in tool_uses:
            try:
                result = await dispatch(tu.name, tu.input, session_id)
                await emit(_evt("agent.tool_result",
                                tool_use_id=tu.id, name=tu.name, output=result))
                if tu.name == "propose_trade":
                    await emit(_evt("agent.proposal", **result))
                tool_results.append({"type": "tool_result", "tool_use_id": tu.id,
                                     "content": json.dumps(result, default=str)})
            except Exception as e:
                await emit(_evt("agent.tool_result",
                                tool_use_id=tu.id, name=tu.name, output=None, error=str(e)))
                tool_results.append({"type": "tool_result", "tool_use_id": tu.id,
                                     "content": f"error: {e}", "is_error": True})

        messages.append({"role": "user", "content": tool_results})

    await emit(_evt("agent.error", message="loop cap reached"))
    return
