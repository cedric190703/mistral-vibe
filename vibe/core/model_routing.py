from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import json
import re

from vibe.core.config.models import ModelConfig, RoutingConfig

_COMPLEXITY_KEYWORDS = {
    "analyse",
    "analyze",
    "architecture",
    "build",
    "design",
    "develop",
    "idea",
    "implement",
    "migration",
    "multi-file",
    "project",
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
        self,
        routing: RoutingConfig | None,
        models: Mapping[str, ModelConfig],
        *,
        default_model: str,
    ) -> None:
        self._models = models
        self._routing = routing or self._default_routing(default_model)
        self._current_model: ModelConfig | None = None
        self._candidate_aliases: list[str] = []
        self._candidate_index = -1
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
        preferred_model = (
            self._routing.capable_model
            if complexity >= _CAPABLE_MODEL_SCORE
            else self._routing.fast_model
        )
        self._candidate_aliases = self._candidate_order(preferred_model)
        self._candidate_index = 0
        self._current_model = self._models[self._candidate_aliases[0]]
        return ModelRoutingDecision(
            model=self._current_model,
            reason="complex task"
            if complexity >= _CAPABLE_MODEL_SCORE
            else "simple task",
            complexity=complexity,
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
        return self._advance_model("model request failed")

    def _escalate(self, reason: str) -> ModelRoutingDecision | None:
        if (
            self._routing is None
            or self._current_model is None
            or self._current_model.alias != self._routing.fast_model
        ):
            return None
        return self._advance_model(reason)

    def _advance_model(self, reason: str) -> ModelRoutingDecision | None:
        if self._candidate_index + 1 >= len(self._candidate_aliases):
            return None
        self._candidate_index += 1
        self._current_model = self._models[
            self._candidate_aliases[self._candidate_index]
        ]
        return ModelRoutingDecision(
            model=self._current_model, reason=reason, complexity=0, escalated=True
        )

    def _candidate_order(self, preferred_model: str) -> list[str]:
        assert self._routing is not None
        preferred = [preferred_model]
        routing_models = [self._routing.capable_model, self._routing.fast_model]
        return list(dict.fromkeys([*preferred, *routing_models]))

    def _default_routing(self, default_model: str) -> RoutingConfig:
        fast_model = next(
            (
                alias
                for alias, model in self._models.items()
                if model.provider.startswith("local-")
            ),
            default_model,
        )
        capable_model = default_model
        if capable_model == fast_model:
            capable_model = next(
                (
                    alias
                    for alias, model in self._models.items()
                    if alias != fast_model and not model.provider.startswith("local-")
                ),
                next(
                    (alias for alias in self._models if alias != fast_model),
                    default_model,
                ),
            )
        return RoutingConfig(fast_model=fast_model, capable_model=capable_model)

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
