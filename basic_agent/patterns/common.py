"""Shared construction helpers for separately defined pattern agents."""

from __future__ import annotations

from google.adk.agents import LlmAgent

from ..agent import tools
from ..config import settings


def worker(name: str, instruction: str, *, output_key: str | None = None) -> LlmAgent:
    return LlmAgent(
        name=name,
        model=settings.model,
        instruction=instruction,
        tools=tools,
        output_key=output_key,
    )
