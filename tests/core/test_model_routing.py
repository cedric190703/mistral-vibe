from __future__ import annotations

from vibe.core.config import ModelConfig, RoutingConfig
from vibe.core.model_routing import AdaptiveModelRouter


def _models() -> dict[str, ModelConfig]:
    return {
        "fast": ModelConfig(name="small", provider="local", alias="fast"),
        "capable": ModelConfig(name="large", provider="mistral", alias="capable"),
    }


def _router() -> AdaptiveModelRouter:
    return AdaptiveModelRouter(
        RoutingConfig(fast_model="fast", capable_model="capable"), _models()
    )


def test_router_chooses_fast_model_for_a_simple_prompt() -> None:
    decision = _router().start_turn("Explain this function")

    assert decision is not None
    assert decision.model.alias == "fast"
    assert decision.reason == "simple task"


def test_router_chooses_capable_model_for_complex_work() -> None:
    decision = _router().start_turn(
        "Refactor the architecture across @src/a.py @src/b.py @tests/test_a.py"
    )

    assert decision is not None
    assert decision.model.alias == "capable"
    assert decision.reason == "complex task"


def test_router_escalates_once_after_a_bad_tool_call() -> None:
    router = _router()
    router.start_turn("Fix this typo")

    decision = router.observe_tool_failure()

    assert decision is not None
    assert decision.model.alias == "capable"
    assert decision.escalated
    assert decision.reason == "tool call failed"
    assert router.observe_tool_failure() is None


def test_router_escalates_after_repeating_the_same_tool_call() -> None:
    router = _router()
    router.start_turn("Find the configuration")

    assert router.observe_tool_call("read_file", {"file_path": "config.toml"}) is None
    assert router.observe_tool_call("read_file", {"file_path": "config.toml"}) is None
    decision = router.observe_tool_call("read_file", {"file_path": "config.toml"})

    assert decision is not None
    assert decision.escalated
    assert decision.reason == "repeated tool call"
