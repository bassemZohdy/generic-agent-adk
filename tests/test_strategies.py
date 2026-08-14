"""Tests for agent strategy registry and implementations."""

import pytest
from google.adk.agents import Agent, LlmAgent, LoopAgent, ParallelAgent, SequentialAgent

from basic_agent.strategies.base import (
    AgentStrategyContext,
    RoleConfig,
    RuntimeContext,
)
from basic_agent.strategies.registry import AgentStrategyRegistry, get_default_registry
from basic_agent.strategies import (
    DirectStrategy,
    EvaluatorOptimizerStrategy,
    HumanInLoopStrategy,
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


def test_llm_builder_applies_role_overrides():
    strategy = DirectStrategy()
    rt = RuntimeContext(
        model="base-model",
        instruction="Base instruction",
        tools=[lambda: "shared"],
        description="Base description",
    )

    # Full override: every role field wins
    override_tool = lambda: "override"
    agent = strategy.llm(
        rt,
        name="overridden",
        role=RoleConfig(
            instruction="Override instruction",
            model="override-model",
            tools=[override_tool],
        ),
    )
    assert agent.instruction == "Override instruction"
    assert agent.model == "override-model"
    assert agent.tools == [override_tool]

    # Partial override: unset role fields fall back to shared values
    partial = strategy.llm(rt, name="partial", role=RoleConfig(model="partial-model"))
    assert partial.instruction == "Base instruction"
    assert partial.model == "partial-model"
    assert partial.tools[0] is rt.tools[0]

    # No role: shared runtime values everywhere; description arg wins
    shared = strategy.llm(rt, name="shared", description="Explicit description")
    assert shared.instruction == "Base instruction"
    assert shared.model == "base-model"
    assert shared.tools[0] is rt.tools[0]
    assert shared.description == "Explicit description"
    assert strategy.llm(rt, name="default_desc").description == "Base description"


def test_router_specialists_get_distinct_instructions_with_roles():
    strategy = RouterStrategy()
    runtime = RuntimeContext(
        model="test-model",
        instruction="Router main instruction",
        tools=[],
        description="Test agent",
        specialists=("research", "solution"),
        roles={"research": RoleConfig(instruction="Research-only instruction")},
    )
    context = AgentStrategyContext(agent_type="ROUTER", runtime=runtime)

    agent = strategy.build(context)

    research, solution = agent.sub_agents
    assert research.instruction == "Research-only instruction"
    assert solution.instruction == (
        "You are the solution specialist. Handle requests in your domain."
    )
    assert research.instruction != agent.instruction
    assert solution.instruction != agent.instruction
    assert research.instruction != solution.instruction


def test_router_specialists_get_generated_prompts_without_roles():
    strategy = RouterStrategy()
    runtime = RuntimeContext(
        model="test-model",
        instruction="Router main instruction",
        tools=[],
        description="Test agent",
        specialists=("research", "solution"),
    )
    context = AgentStrategyContext(agent_type="ROUTER", runtime=runtime)

    agent = strategy.build(context)

    research, solution = agent.sub_agents
    assert research.instruction == (
        "You are the research specialist. Handle requests in your domain."
    )
    assert solution.instruction == (
        "You are the solution specialist. Handle requests in your domain."
    )
    assert research.instruction != agent.instruction
    assert solution.instruction != agent.instruction


def test_router_specialist_roles_override_model_and_tools():
    strategy = RouterStrategy()
    specialist_tool = lambda: "specialist"
    runtime = RuntimeContext(
        model="base-model",
        instruction="Router main instruction",
        tools=[],
        description="Test agent",
        specialists=("research",),
        roles={
            "research": RoleConfig(model="specialist-model", tools=[specialist_tool])
        },
    )
    context = AgentStrategyContext(agent_type="ROUTER", runtime=runtime)

    agent = strategy.build(context)

    specialist = agent.sub_agents[0]
    assert specialist.model == "specialist-model"
    assert specialist.tools == [specialist_tool]


def test_human_in_loop_strategy_requires_approval():
    strategy = HumanInLoopStrategy()
    runtime = RuntimeContext(
        model="test-model",
        instruction="Test instruction",
        tools=[],
        description="Test agent",
        require_approval=False,
    )
    context = AgentStrategyContext(agent_type="HUMAN_IN_LOOP", runtime=runtime)

    with pytest.raises(ValueError, match="HUMAN_IN_LOOP"):
        strategy.validate(context)


def test_evaluator_optimizer_strategy_requires_max_iterations():
    strategy = EvaluatorOptimizerStrategy()
    runtime = RuntimeContext(
        model="test-model",
        instruction="Test instruction",
        tools=[],
        description="Test agent",
        max_iterations=0,  # Invalid
    )
    context = AgentStrategyContext(agent_type="EVALUATOR_OPTIMIZER", runtime=runtime)

    with pytest.raises(ValueError, match="max_iterations"):
        strategy.validate(context)
