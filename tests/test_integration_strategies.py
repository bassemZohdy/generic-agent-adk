"""Integration tests for strategy registry and configuration loader."""

import tempfile
from pathlib import Path

from google.adk.agents import (
    Agent,
    LlmAgent,
    LoopAgent,
    ParallelAgent,
    SequentialAgent,
)

import pytest

from basic_agent.config_loader import load_config_from_yaml
from basic_agent.strategies.base import RuntimeContext, AgentStrategyContext
from basic_agent.strategies.registry import get_default_registry
from basic_agent.use_cases.registry import get_default_registry as get_use_case_registry


def _strategy_for_use_case(use_case: str):
    """Return the strategy instance behind a canonical use-case key."""
    return get_use_case_registry().resolve(use_case)[1].strategy


def test_registry_integration_with_config_loader():
    """End-to-end: YAML config -> AgentConfig -> Strategy -> Agent."""

    with tempfile.TemporaryDirectory() as tmpdir:
        config_file = Path(tmpdir) / "agent.yaml"
        config_file.write_text("""
agent:
  use_case: assistant
  description: Direct test agent

model:
  provider: google
  name: gemini-2.0-flash

instructions:
  value: "Test instruction"

tools:
  enabled:
    - knowledge

state:
  enabled: true
""")

        config = load_config_from_yaml(config_file)

        # Resolve strategy via the use-case facade
        strategy = _strategy_for_use_case(config.use_case)
        assert strategy.agent_type == "DIRECT"

        # Build runtime context
        runtime = RuntimeContext(
            model=config.model.name,
            instruction=config.instructions.value,
            tools=[],
            description=config.description,
        )

        # Build agent via strategy
        context = AgentStrategyContext(agent_type=strategy.agent_type, runtime=runtime)
        agent = strategy.build(context)

        assert isinstance(agent, Agent)
        assert agent.model == "gemini-2.0-flash"
        assert agent.instruction == "Test instruction"


def test_registry_all_strategies_buildable():
    """Verify all registered strategies can build agents without errors."""
    registry = get_default_registry()

    runtime = RuntimeContext(
        model="test-model",
        instruction="Test",
        tools=[],
        description="Test agent",
        max_iterations=3,
        specialists=("research", "solution"),
    )

    for agent_type in registry.list_types():
        strategy = registry.get(agent_type)
        context = AgentStrategyContext(agent_type=agent_type, runtime=runtime)

        try:
            agent = strategy.build(context)
            assert agent is not None
            assert agent.name  # Should have a name
        except ValueError as e:
            # Some strategies have mandatory config
            # (e.g., ROUTER requires specialists, HUMAN_IN_LOOP requires approval)
            # This is expected for missing config
            if "required" in str(e).lower() or "require" in str(e).lower():
                continue
            raise


def test_sequential_strategy_with_config():
    """Test SEQUENTIAL strategy with configuration."""
    registry = get_default_registry()

    with tempfile.TemporaryDirectory() as tmpdir:
        config_file = Path(tmpdir) / "agent.yaml"
        config_file.write_text("""
agent:
  use_case: pipeline
  description: Sequential pipeline

model:
  provider: google
  name: gemini-2.0-flash

instructions:
  value: "Process step by step"

tools:
  enabled: []

execution:
  steps: 3

state:
  enabled: true
""")

        config = load_config_from_yaml(config_file)
        strategy = _strategy_for_use_case(config.use_case)
        assert strategy.agent_type == "SEQUENTIAL"

        runtime = RuntimeContext(
            model=config.model.name,
            instruction=config.instructions.value,
            tools=[],
            description=config.description,
        )

        context = AgentStrategyContext(
            agent_type=strategy.agent_type,
            runtime=runtime,
            extra_config={"steps": 3},
        )
        agent = strategy.build(context)

        assert isinstance(agent, SequentialAgent)
        assert len(agent.sub_agents) == 3


def test_parallel_strategy_with_config():
    """Test PARALLEL strategy with configuration."""
    registry = get_default_registry()

    with tempfile.TemporaryDirectory() as tmpdir:
        config_file = Path(tmpdir) / "agent.yaml"
        config_file.write_text("""
agent:
  use_case: multi_perspective
  description: Parallel workers

model:
  provider: google
  name: gemini-2.0-flash

instructions:
  value: "Work in parallel"

tools:
  enabled: []

execution:
  workers: 4

state:
  enabled: true
""")

        config = load_config_from_yaml(config_file)
        strategy = _strategy_for_use_case(config.use_case)
        assert strategy.agent_type == "PARALLEL"

        runtime = RuntimeContext(
            model=config.model.name,
            instruction=config.instructions.value,
            tools=[],
            description=config.description,
        )

        context = AgentStrategyContext(
            agent_type=strategy.agent_type,
            runtime=runtime,
            extra_config={"workers": 4},
        )
        agent = strategy.build(context)

        assert isinstance(agent, ParallelAgent)
        assert len(agent.sub_agents) == 4


def test_router_strategy_with_specialists():
    """Test ROUTER strategy with specialist configuration."""

    with tempfile.TemporaryDirectory() as tmpdir:
        config_file = Path(tmpdir) / "agent.yaml"
        config_file.write_text("""
agent:
  use_case: expert_dispatch
  description: Router with specialists

model:
  provider: google
  name: gemini-2.0-flash

instructions:
  value: "Route to specialist"

tools:
  enabled: []

execution:
  specialists:
    - research
    - implementation
    - security

state:
  enabled: true
""")

        config = load_config_from_yaml(config_file)
        strategy = _strategy_for_use_case(config.use_case)
        assert strategy.agent_type == "ROUTER"

        runtime = RuntimeContext(
            model=config.model.name,
            instruction=config.instructions.value,
            tools=[],
            description=config.description,
            specialists=tuple(config.execution.specialists),
        )

        context = AgentStrategyContext(agent_type=strategy.agent_type, runtime=runtime)
        agent = strategy.build(context)

        assert isinstance(agent, LlmAgent)
        assert len(agent.sub_agents) == 3


def test_loop_strategy_respects_max_iterations():
    """Test LOOP strategy with iteration limits."""

    with tempfile.TemporaryDirectory() as tmpdir:
        config_file = Path(tmpdir) / "agent.yaml"
        config_file.write_text("""
agent:
  use_case: refine_until_good
  description: Loop with limit

model:
  provider: google
  name: gemini-2.0-flash

instructions:
  value: "Iterate"

tools:
  enabled: []

execution:
  max_iterations: 10

state:
  enabled: true
""")

        config = load_config_from_yaml(config_file)
        strategy = _strategy_for_use_case(config.use_case)
        assert strategy.agent_type == "EVALUATOR_OPTIMIZER"

        runtime = RuntimeContext(
            model=config.model.name,
            instruction=config.instructions.value,
            tools=[],
            description=config.description,
            max_iterations=10,
        )

        context = AgentStrategyContext(agent_type=strategy.agent_type, runtime=runtime)
        agent = strategy.build(context)

        assert isinstance(agent, LoopAgent)
        assert agent.max_iterations == 10


def test_all_examples_are_loadable():
    """Verify all example YAML files are loadable and valid."""
    examples_dir = Path(__file__).parent.parent / "examples"

    if not examples_dir.exists():
        # Examples don't exist yet, skip
        return

    for yaml_file in examples_dir.glob("*.yaml"):
        config = load_config_from_yaml(yaml_file)
        assert config.use_case  # Should have a use case
        assert config.model  # Should have model config
        config.validate()  # Should validate without errors


EXAMPLE_USE_CASES = [
    ("assistant.yaml", "assistant", LlmAgent),
    ("pipeline.yaml", "pipeline", SequentialAgent),
    ("multi-perspective.yaml", "multi_perspective", ParallelAgent),
    ("refine-until-good.yaml", "refine_until_good", LoopAgent),
    ("expert-dispatch.yaml", "expert_dispatch", LlmAgent),
    ("team-coordinator.yaml", "team_coordinator", LlmAgent),
    ("plan-and-execute.yaml", "plan_and_execute", SequentialAgent),
    ("approval-gate.yaml", "approval_gate", SequentialAgent),
]


@pytest.mark.parametrize("filename,use_case,root_type", EXAMPLE_USE_CASES)
def test_example_yaml_loads_and_builds(filename, use_case, root_type):
    """Every example file loads via load_config_from_yaml and builds via the registry."""
    path = Path(__file__).parent.parent / "examples" / filename

    config = load_config_from_yaml(path)
    assert config.use_case == use_case

    runtime = RuntimeContext(
        model=config.model.name if config.model else "test",
        instruction=config.instructions.value if config.instructions else "test",
        tools=[],
        description=config.description or "test",
        max_iterations=config.execution.max_iterations if config.execution else 3,
        require_approval=(
            config.execution.require_approval if config.execution else False
        ),
        specialists=tuple(config.execution.specialists) if config.execution else (),
        roles=dict(config.roles),
    )

    agent = get_use_case_registry().resolve(config.use_case)[1].build(runtime)
    assert agent is not None
    assert isinstance(agent, root_type)


def test_strategy_builder_pattern_composability():
    """Verify strategy pattern allows composition and extension."""
    registry = get_default_registry()

    # Retrieve different strategies
    direct = registry.get("DIRECT")
    react = registry.get("REACT")
    sequential = registry.get("SEQUENTIAL")

    # All should be buildable
    runtime = RuntimeContext(
        model="test",
        instruction="Test",
        tools=[],
        description="Test",
    )

    for strategy in [direct, react, sequential]:
        context = AgentStrategyContext(agent_type=strategy.agent_type, runtime=runtime)
        agent = strategy.build(context)
        assert agent is not None

    # Demonstrates new strategies can be added without modifying test
    # or core runtime
