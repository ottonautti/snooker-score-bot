"""LLM interface: reads a score message into structured data with Gemini on Vertex AI."""

import logging
import os

from snooker_score_bot.models import InferredMatch, SnookerPlayer
from snooker_score_bot.settings import Settings

from . import prompts

# Structured output: the model must answer with JSON in exactly this shape.
RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "players": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"options": {"type": "array", "items": {"type": "string"}}},
                "required": ["options"],
            },
        },
        "player1_score": {"type": "integer", "nullable": True},
        "player2_score": {"type": "integer", "nullable": True},
        "breaks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"player": {"type": "integer"}, "points": {"type": "integer"}},
                "required": ["player", "points"],
            },
        },
    },
    "required": ["players", "player1_score", "player2_score", "breaks"],
}


class SnookerScoresLLM:
    """Extracts snooker scores from messages."""

    def __init__(self, model: str, project: str, location: str, thinking_level: str = "minimal", timeout_s=20):
        from google import genai
        from google.genai import types

        self.model = model
        self.client = genai.Client(
            vertexai=True,
            project=project,
            location=location,
            http_options=types.HttpOptions(timeout=int(timeout_s * 1000)),
        )
        self.config = types.GenerateContentConfig(
            temperature=0,
            max_output_tokens=500,
            response_mime_type="application/json",
            response_schema=RESPONSE_SCHEMA,
            thinking_config=types.ThinkingConfig(thinking_level=thinking_level),
        )
        self.verbose = bool(os.getenv("LLM_VERBOSE"))

    def infer(self, passage: str, known_players: list[SnookerPlayer]) -> InferredMatch:
        """Read the match result in the passage, choosing names from known_players."""
        prompt = prompts.build_prompt(
            players_list="\n".join(plr.__llm_str__() for plr in known_players), passage=passage
        )
        if self.verbose:
            logging.info("LLM prompt:\n%s", prompt)
        response = self.client.models.generate_content(model=self.model, contents=prompt, config=self.config)
        logging.info("%s output: %s", self.model, response.text)
        return InferredMatch.model_validate_json(response.text)


def get_llm_client(settings: Settings) -> SnookerScoresLLM:
    """Get the LLM client based on the settings."""
    return SnookerScoresLLM(
        model=settings.LLM_MODEL,
        project=settings.GCP_PROJECT,
        location=settings.LLM_LOCATION,
        thinking_level=settings.LLM_THINKING_LEVEL,
    )
