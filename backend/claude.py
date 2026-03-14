import json
import anthropic

from .image_utils import parse_image_data
from .prompts import SYSTEM_PROMPT, ANALYZE_PROMPT, DIMENSION_EXTRACTION_PROMPT


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


def _extract_dimensions(client: anthropic.Anthropic, image_b64: str) -> str | None:
    """Phase 1: Extract dimension text and room labels from the image."""
    media_type, image_data = parse_image_data(image_b64)
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
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
                {"type": "text", "text": DIMENSION_EXTRACTION_PROMPT},
            ],
        }],
    )
    text = message.content[0].text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1]
        if text.endswith("```"):
            text = text[:-3].strip()
    # Validate it's parseable JSON
    try:
        json.loads(text)
        return text
    except json.JSONDecodeError:
        return None


def generate_plan(prompt: str, image_b64: str | None = None) -> dict:
    """Send prompt (+ optional image) to Claude and return the parsed JSON plan.

    When an image is provided, uses a two-phase approach:
    1. Extract dimension text from the image
    2. Generate plan JSON using extracted dimensions as ground truth
    """
    client = anthropic.Anthropic()
    content = []

    # Phase 1: Extract dimensions if image is provided
    dimension_context = ""
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

        dim_json = _extract_dimensions(client, image_b64)
        if dim_json:
            dimension_context = (
                "DIMENSIONS EXTRACTED FROM THE IMAGE (use these as ground truth):\n"
                f"{dim_json}\n\n"
            )

    # Phase 2: Generate plan with dimension context
    full_prompt = dimension_context + prompt if dimension_context else prompt
    content.append({"type": "text", "text": full_prompt})

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
