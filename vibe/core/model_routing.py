from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import json
import re

from vibe.core.config.models import ModelConfig, RoutingConfig

_COMPLEXITY_KEYWORDS = {
    "architecture",
    "design",
    "migration",
    "multi-file",
    "refactor",
    "redesign",
}
_FILE_REFERENCE = re.compile(r"(?<!\w)@[^\s]+")
_CAPABLE_MODEL_SCORE = 3
_LONG_PROMPT_CHARS = 600
_MEDIUM_PROMPT_CHARS = 250
_MANY_FILE_REFERENCES = 3
_REPEATED_TOOL_CALLS = 3
_MANY_TOOL_CALLS = 5


@dataclass(frozen=True)
class ModelRoutingDecision:
    model: ModelConfig
    reason: str
    complexity: int
    escalated: bool = False


class AdaptiveModelRouter:
    def __init__(
        self, routing: RoutingConfig | None, models: Mapping[str, ModelConfig]
    ) -> None:
        self._routing = routing
        self._models = models
        self._current_model: ModelConfig | None = None
        self._escalated = False
        self._tool_calls = 0
        self._failed_tools = 0
        self._tool_fingerprints: dict[str, int] = {}

    @property
    def current_model(self) -> ModelConfig | None:
        return self._current_model

    def start_turn(
        self, prompt: str, *, has_images: bool = False
    ) -> ModelRoutingDecision | None:
        if self._routing is None:
            return None
        complexity = self._complexity(prompt, has_images=has_images)
        if complexity >= _CAPABLE_MODEL_SCORE:
            self._current_model = self._models[self._routing.capable_model]
            return ModelRoutingDecision(
                model=self._current_model, reason="complex task", complexity=complexity
            )
        self._current_model = self._models[self._routing.fast_model]
        return ModelRoutingDecision(
            model=self._current_model, reason="simple task", complexity=complexity
        )

    def observe_tool_call(
        self, tool_name: str, args: Mapping[str, object] | None
    ) -> ModelRoutingDecision | None:
        if self._current_model is None:
            return None
        self._tool_calls += 1
        fingerprint = (
            f"{tool_name}:{json.dumps(args or {}, sort_keys=True, default=str)}"
        )
        self._tool_fingerprints[fingerprint] = (
            self._tool_fingerprints.get(fingerprint, 0) + 1
        )
        if self._tool_fingerprints[fingerprint] >= _REPEATED_TOOL_CALLS:
            return self._escalate("repeated tool call")
        if self._tool_calls >= _MANY_TOOL_CALLS:
            return self._escalate("task needs several tool steps")
        return None

    def observe_tool_failure(self) -> ModelRoutingDecision | None:
        if self._current_model is None:
            return None
        self._failed_tools += 1
        if self._failed_tools >= 1:
            return self._escalate("tool call failed")
        return None

    def observe_model_failure(self) -> ModelRoutingDecision | None:
        return self._escalate("fast model request failed")

    def _escalate(self, reason: str) -> ModelRoutingDecision | None:
        if (
            self._routing is None
            or self._escalated
            or self._current_model is None
            or self._current_model.alias != self._routing.fast_model
        ):
            return None
        self._escalated = True
        self._current_model = self._models[self._routing.capable_model]
        return ModelRoutingDecision(
            model=self._current_model, reason=reason, complexity=0, escalated=True
        )

    @staticmethod
    def _complexity(prompt: str, *, has_images: bool) -> int:
        lowered = prompt.lower()
        score = 3 if has_images else 0
        score += (
            2
            if len(prompt) >= _LONG_PROMPT_CHARS
            else 1
            if len(prompt) >= _MEDIUM_PROMPT_CHARS
            else 0
        )
        score += (
            2
            if len(_FILE_REFERENCE.findall(prompt)) >= _MANY_FILE_REFERENCES
            else 1
            if "@" in prompt
            else 0
        )
        score += 3 if any(keyword in lowered for keyword in _COMPLEXITY_KEYWORDS) else 0
        return score
