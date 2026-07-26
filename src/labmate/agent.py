"""M0: the bare agent loop.

One Anthropic Messages-API loop, shared by every specialist. What differs
per specialist right now is just which system prompt the orchestrator's
(hardcoded, M0) routing selects — no tools exist yet, so the model answers
from its own training knowledge only. Tool calling arrives in M1.
"""

import argparse

from anthropic import Anthropic

from labmate.orchestrator import route
from labmate.specialists import literature, safety, vision

SPECIALISTS = {
    "literature": literature,
    "vision": vision,
    "safety": safety,
}


def run(user_input: str, image_path: str | None = None) -> str:
    specialist_name = route(user_input, has_image=image_path is not None)
    specialist = SPECIALISTS[specialist_name]

    client = Anthropic()
    response = client.messages.create(
        model="claude-sonnet-5",
        max_tokens=1024,
        system=specialist.SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_input}],
    )
    text = "".join(block.text for block in response.content if block.type == "text")
    return f"[routed to: {specialist_name}]\n{text}"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("message")
    parser.add_argument("--image", default=None, help="path to a sample image (routes to vision)")
    args = parser.parse_args()
    print(run(args.message, args.image))


if __name__ == "__main__":
    main()
