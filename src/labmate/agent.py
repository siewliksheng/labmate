"""M1/M2/M3/M4: the agent loop -- real tool calling, automatic memory
writes, every draft response passing through the Hard Safety Gate, and
(M4) auto-tagging with whichever experiment session is currently active.

One tool-calling loop shared by every specialist -- what differs per
specialist is its system prompt and which tool subset it's given (see
specialists/*.py). Routing is still the M0 hardcoded keyword net
(orchestrator.py); a real LLM router replaces it in M6, alongside the M0
net, not instead of it.

The model call itself goes through labmate.llm_client, which is pluggable
(Anthropic or a local Ollama model via LLM_BACKEND -- see .env.example)
without any change to this loop's code.

Every completed exchange is recorded to memory unconditionally, AFTER the
gate has run -- memory reflects what the user actually saw, never a
pre-gate draft that got escalated instead of released. If an experiment is
active (labmate.experiment.start_experiment set it), the Q&A row is
tagged with its id automatically, so a later Report can pull ad-hoc Lab
questions back without the user threading an experiment_id through every
CLI call.
"""

import argparse
import json

from labmate.guardrails import enforce_safety_gate
from labmate.llm_client import create_message
from labmate.memory.store import get_active_experiment_id, record_qa
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

    messages = [{"role": "user", "content": user_content}]
    tool_call_log = []

    for _ in range(MAX_TURNS):
        response = create_message(
            system=specialist.SYSTEM_PROMPT, messages=messages, tools=specialist.TOOL_SCHEMAS, max_tokens=2048
        )
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use":
            draft_text = "".join(block.text for block in response.content if block.type == "text")
            gate_result = enforce_safety_gate(specialist_name, user_input, tool_call_log, draft_text)
            record_qa(
                specialist_name,
                user_input,
                gate_result["response_text"],
                experiment_id=get_active_experiment_id(),
            )
            return f"[routed to: {specialist_name}]\n{gate_result['response_text']}"

        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            result = dispatch_tool(block.name, block.input)
            tool_call_log.append({"name": block.name, "input": block.input, "result": result})
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
