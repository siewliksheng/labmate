"""The agent loop: bare Anthropic Messages API, no framework.

Phase 0 of the learning roadmap says build this by hand before reaching for
LangGraph/the Agent SDK. Keep it legible enough to draw on a whiteboard.
"""

import argparse
import json

from anthropic import Anthropic

from radreport_agent.mcp_server.tools import TOOL_SCHEMAS, dispatch_tool

SYSTEM_PROMPT = """\
You structure radiology reports for clinician review. You are not a diagnostic
tool: you extract, normalize, and flag — a radiologist or referring physician
makes every clinical decision. Every finding you report must cite the exact
sentence in the source report it came from. Compute critical-finding status
using the provided tools; never assert a Lung-RADS category or Fleischner
recommendation from your own reasoning.
"""

MAX_TURNS = 8


def run(report_text: str) -> dict:
    client = Anthropic()
    messages = [{"role": "user", "content": f"Structure this report:\n\n{report_text}"}]

    for _ in range(MAX_TURNS):
        response = client.messages.create(
            model="claude-sonnet-5",
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=TOOL_SCHEMAS,
            messages=messages,
        )
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use":
            return {"messages": messages, "final": response.content}

        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            result = dispatch_tool(block.name, block.input)
            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(result),
                }
            )
        messages.append({"role": "user", "content": tool_results})

    raise RuntimeError(f"did not converge within {MAX_TURNS} turns")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", required=True, help="path to a report text file")
    args = parser.parse_args()

    with open(args.report, encoding="utf-8") as f:
        report_text = f.read()

    result = run(report_text)
    print(result["final"])


if __name__ == "__main__":
    main()
