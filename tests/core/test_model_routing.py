from __future__ import annotations

import pytest

from tests.conftest import build_test_agent_loop, build_test_vibe_config
from tests.mock.utils import mock_llm_chunk
from tests.stubs.fake_backend import FakeBackend
from vibe.core.config import ModelConfig, RoutingConfig
from vibe.core.model_routing import AdaptiveModelRouter
from vibe.core.types import ModelRoutingEvent


def _models() -> dict[str, ModelConfig]:
    return {
        "fast": ModelConfig(name="small", provider="local", alias="fast"),
        "capable": ModelConfig(name="large", provider="mistral", alias="capable"),
    }


def _router() -> AdaptiveModelRouter:
    return AdaptiveModelRouter(
        RoutingConfig(fast_model="fast", capable_model="capable"),
        _models(),
        default_model="capable",
    )


def test_router_uses_a_local_model_without_routing_configuration() -> None:
    models = {
        "fast": ModelConfig(name="small", provider="local-11434", alias="fast"),
        "capable": _models()["capable"],
    }
    decision = AdaptiveModelRouter(None, models, default_model="capable").start_turn(
        "Explain this function"
    )

    assert decision is not None
    assert decision.model.alias == "fast"

    fallback = AdaptiveModelRouter(None, models, default_model="fast")
    fallback.start_turn("Explain this function")
    decision = fallback.observe_model_failure()

    assert decision is not None
    assert decision.model.alias == "capable"
    assert decision.reason == "model request failed"


def test_router_uses_a_different_selected_local_model_as_capable_fallback() -> None:
    models = {
        "qwen": ModelConfig(name="qwen", provider="local-11434", alias="qwen"),
        "remote": ModelConfig(name="remote", provider="mistral", alias="remote"),
        "selected": ModelConfig(
            name="mistral", provider="local-11434", alias="selected"
        ),
    }
    router = AdaptiveModelRouter(None, models, default_model="selected")
    first = router.start_turn("Hello there")
    fallback = router.observe_model_failure()

    assert first is not None
    assert first.model.alias == "qwen"
    assert fallback is not None
    assert fallback.model.alias == "selected"


def test_router_uses_the_default_model_without_a_local_model() -> None:
    models = {"capable": _models()["capable"]}
    decision = AdaptiveModelRouter(None, models, default_model="capable").start_turn(
        "Explain this function"
    )

    assert decision is not None
    assert decision.model.alias == "capable"


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


def test_router_treats_idea_analysis_as_complex_work() -> None:
    decision = _router().start_turn("Analyze the idea that I want to develop")

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


def test_router_does_not_cycle_through_unrelated_models_after_failures() -> None:
    models = {
        **_models(),
        "backup": ModelConfig(name="backup", provider="mistral", alias="backup"),
    }
    router = AdaptiveModelRouter(
        RoutingConfig(fast_model="fast", capable_model="capable"),
        models,
        default_model="capable",
    )
    router.start_turn("Explain this function")

    capable = router.observe_model_failure()
    assert capable is not None
    assert capable.model.alias == "capable"
    assert router.observe_model_failure() is None


@pytest.mark.asyncio
async def test_disabled_routing_uses_the_selected_model_without_routing_events() -> (
    None
):
    models = list(_models().values())
    config = build_test_vibe_config(
        models=models,
        active_model="capable",
        routing=RoutingConfig(fast_model="fast", capable_model="capable"),
    )
    agent_loop = build_test_agent_loop(
        config=config, backend=FakeBackend(mock_llm_chunk(content="Hello"))
    )
    agent_loop.set_adaptive_routing_enabled(False)

    events = [event async for event in agent_loop.act("Hello there")]

    assert not any(isinstance(event, ModelRoutingEvent) for event in events)
