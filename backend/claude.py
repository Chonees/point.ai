import json
import anthropic

from .prompts import SYSTEM_PROMPT, ANALYZE_PROMPT


def parse_image_data(raw: str) -> tuple[str, str]:
    """Extract media_type and base64 data from a data-URI string."""
    media_type = "image/png"
    image_data = raw
    if "," in raw:
        header, image_data = raw.split(",", 1)
        if "jpeg" in header:
            media_type = "image/jpeg"
        elif "webp" in header:
            media_type = "image/webp"
    return media_type, image_data


def analyze_image(image_b64: str) -> str:
    """Send an image to Claude Vision and get a text description."""
    media_type, image_data = parse_image_data(image_b64)
    client = anthropic.Anthropic()
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": media_type,
                        "data": image_data,
                    },
                },
                {"type": "text", "text": ANALYZE_PROMPT},
            ],
        }],
    )
    return message.content[0].text.strip()


def generate_plan(prompt: str, image_b64: str | None = None) -> dict:
    """Send prompt (+ optional image) to Claude and return the parsed JSON plan."""
    content = []

    if image_b64:
        media_type, image_data = parse_image_data(image_b64)
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": media_type,
                "data": image_data,
            },
        })

    content.append({"type": "text", "text": prompt})

    client = anthropic.Anthropic()
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": content}],
    )

    response_text = message.content[0].text.strip()
    if response_text.startswith("```"):
        response_text = response_text.split("\n", 1)[1]
        if response_text.endswith("```"):
            response_text = response_text[:-3].strip()

    return json.loads(response_text)
