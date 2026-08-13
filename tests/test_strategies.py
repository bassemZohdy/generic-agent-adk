"""Tests for agent strategy registry and implementations."""

import pytest
from google.adk.agents import Agent, LlmAgent, LoopAgent, ParallelAgent, SequentialAgent

from basic_agent.strategies.base import AgentStrategyContext, RuntimeContext
from basic_agent.strategies.registry import AgentStrategyRegistry, get_default_registry
from basic_agent.strategies import (
    DirectStrategy,
    ReactStrategy,
    SequentialAgentStrategy,
    ParallelAgentStrategy,
    LoopAgentStrategy,
    RouterStrategy,
    SupervisorStrategy,
)


def test_strategy_registry_register_and_retrieve():
    registry = AgentStrategyRegistry()
    strategy = DirectStrategy()
    registry.register(strategy)

    assert registry.has("DIRECT")
    assert registry.get("DIRECT") is strategy
    assert registry.get("NONEXISTENT") is None


def test_strategy_registry_rejects_duplicate_registration():
    registry = AgentStrategyRegistry()
    strategy = DirectStrategy()
    registry.register(strategy)

    with pytest.raises(ValueError, match="already registered"):
        registry.register(strategy)


def test_strategy_registry_lists_types():
    registry = AgentStrategyRegistry()
    registry.register(DirectStrategy())
    registry.register(ReactStrategy())

    types = registry.list_types()
    assert "DIRECT" in types
    assert "REACT" in types
    assert types == sorted(types)


def test_default_registry_initializes_builtin_strategies():
    registry = get_default_registry()

    expected_types = {
        "DIRECT",
        "REACT",
        "SEQUENTIAL",
        "PARALLEL",
        "LOOP",
        "ROUTER",
        "SUPERVISOR",
        "PLAN_EXECUTE",
        "EVALUATOR_OPTIMIZER",
        "HUMAN_IN_LOOP",
    }

    for strategy_type in expected_types:
        assert registry.has(strategy_type), f"Strategy {strategy_type} not registered"


def test_direct_strategy_builds_single_agent():
    strategy = DirectStrategy()
    runtime = RuntimeContext(
        model="test-model",
        instruction="Test instruction",
        tools=[],
        description="Test agent",
    )
    context = AgentStrategyContext(agent_type="DIRECT", runtime=runtime)

    agent = strategy.build(context)

    assert isinstance(agent, Agent)
    assert agent.model == "test-model"
    assert agent.instruction == "Test instruction"


def test_react_strategy_builds_agent_with_tools():
    strategy = ReactStrategy()
    tools = [lambda: "test"]  # Mock tool

    runtime = RuntimeContext(
        model="test-model",
        instruction="Test instruction",
        tools=tools,
        description="Test agent",
    )
    context = AgentStrategyContext(agent_type="REACT", runtime=runtime)

    agent = strategy.build(context)

    assert isinstance(agent, Agent)
    assert agent.tools == tools


def test_sequential_strategy_builds_sequential_agent():
    strategy = SequentialAgentStrategy()
    runtime = RuntimeContext(
        model="test-model",
        instruction="Test instruction",
        tools=[],
        description="Test agent",
    )
    context = AgentStrategyContext(agent_type="SEQUENTIAL", runtime=runtime)

    agent = strategy.build(context)

    assert isinstance(agent, SequentialAgent)


def test_parallel_strategy_builds_parallel_agent():
    strategy = ParallelAgentStrategy()
    runtime = RuntimeContext(
        model="test-model",
        instruction="Test instruction",
        tools=[],
        description="Test agent",
    )
    context = AgentStrategyContext(agent_type="PARALLEL", runtime=runtime)

    agent = strategy.build(context)

    assert isinstance(agent, ParallelAgent)


def test_loop_strategy_validates_max_iterations():
    strategy = LoopAgentStrategy()
    runtime = RuntimeContext(
        model="test-model",
        instruction="Test instruction",
        tools=[],
        description="Test agent",
        max_iterations=0,  # Invalid
    )
    context = AgentStrategyContext(agent_type="LOOP", runtime=runtime)

    with pytest.raises(ValueError, match="max_iterations"):
        strategy.build(context)


def test_loop_strategy_builds_loop_agent():
    strategy = LoopAgentStrategy()
    runtime = RuntimeContext(
        model="test-model",
        instruction="Test instruction",
        tools=[],
        description="Test agent",
        max_iterations=5,
    )
    context = AgentStrategyContext(agent_type="LOOP", runtime=runtime)

    agent = strategy.build(context)

    assert isinstance(agent, LoopAgent)
    assert agent.max_iterations == 5


def test_router_strategy_validates_specialists():
    strategy = RouterStrategy()
    runtime = RuntimeContext(
        model="test-model",
        instruction="Test instruction",
        tools=[],
        description="Test agent",
        specialists=(),  # Empty
    )
    context = AgentStrategyContext(agent_type="ROUTER", runtime=runtime)

    with pytest.raises(ValueError, match="specialist"):
        strategy.build(context)


def test_router_strategy_builds_with_specialists():
    strategy = RouterStrategy()
    runtime = RuntimeContext(
        model="test-model",
        instruction="Test instruction",
        tools=[],
        description="Test agent",
        specialists=("research", "solution"),
    )
    context = AgentStrategyContext(agent_type="ROUTER", runtime=runtime)

    agent = strategy.build(context)

    assert isinstance(agent, LlmAgent)
    assert agent.sub_agents  # Should have sub-agents


def test_supervisor_strategy_builds_supervisor_agent():
    strategy = SupervisorStrategy()
    runtime = RuntimeContext(
        model="test-model",
        instruction="Test instruction",
        tools=[],
        description="Test agent",
    )
    context = AgentStrategyContext(agent_type="SUPERVISOR", runtime=runtime)

    agent = strategy.build(context)

    assert isinstance(agent, LlmAgent)
    assert agent.sub_agents  # Should have workers
