"""M1: the agent loop, now with real tool calling.

Still one Anthropic Messages-API loop shared by every specialist -- what
differs per specialist is its system prompt and which tool subset it's
given (see specialists/*.py). Routing is still the M0 hardcoded keyword net
(orchestrator.py); a real LLM router replaces it in M5, alongside the M0
net, not instead of it.
"""

import argparse
import json

from anthropic import Anthropic

from labmate.mcp_server.tools import dispatch_tool
from labmate.orchestrator import route
from labmate.specialists import literature, safety, vision

SPECIALISTS = {
    "literature": literature,
    "vision": vision,
    "safety": safety,
}

MAX_TURNS = 6


def run(user_input: str, image_path: str | None = None) -> str:
    specialist_name = route(user_input, has_image=image_path is not None)
    specialist = SPECIALISTS[specialist_name]

    user_content = user_input
    if image_path and specialist_name == "vision":
        user_content = f"{user_input}\n\n(image path: {image_path})"

    client = Anthropic()
    messages = [{"role": "user", "content": user_content}]

    for _ in range(MAX_TURNS):
        response = client.messages.create(
            model="claude-sonnet-5",
            max_tokens=2048,
            system=specialist.SYSTEM_PROMPT,
            tools=specialist.TOOL_SCHEMAS,
            messages=messages,
        )
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use":
            text = "".join(block.text for block in response.content if block.type == "text")
            return f"[routed to: {specialist_name}]\n{text}"

        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            result = dispatch_tool(block.name, block.input)
            tool_results.append(
                {"type": "tool_result", "tool_use_id": block.id, "content": json.dumps(result)}
            )
        messages.append({"role": "user", "content": tool_results})

    raise RuntimeError(f"did not converge within {MAX_TURNS} turns")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("message")
    parser.add_argument("--image", default=None, help="path to a sample image (routes to vision)")
    args = parser.parse_args()
    print(run(args.message, args.image))


if __name__ == "__main__":
    main()
