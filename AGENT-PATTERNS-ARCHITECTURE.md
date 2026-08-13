# Agent Patterns Architecture Guide

**Document**: Comprehensive breakdown of all 10 execution strategies  
**Date**: 2026-08-13  
**Purpose**: Understand characteristics, worker configuration, and consolidation for each pattern

---

## Quick Reference Table

| Pattern | Type | Workers | System Prompt | LLM Model | Consolidation |
|---------|------|---------|---------------|-----------|----------------|
| **DIRECT** | Single | 1 | Shared | Shared | One-shot |
| **REACT** | Single | 1 | Shared | Shared | Iterative tools |
| **SEQUENTIAL** | Multi | N agents | Shared | Shared | Ordered output |
| **PARALLEL** | Multi | N agents | Shared | Shared | Aggregated |
| **LOOP** | Iterative | 1 agent | Shared | Shared | Max iterations |
| **ROUTER** | Hierarchical | N specialists | Different | Shared | LLM routing |
| **SUPERVISOR** | Hierarchical | N workers | Shared | Shared | LLM coordination |
| **PLANNER_EXECUTOR** | Staged | 2 agents | **Different** | Shared | Sequential steps |
| **EVALUATOR_OPTIMIZER** | Iterative | 1 agent | Special | Shared | Continuous improve |
| **HUMAN_IN_LOOP** | Gated | 2 agents | **Different** | Shared | Human approval |

---

## 1. DIRECT Strategy

### Overview
Single LlmAgent without agentic tool looping. Pure one-shot execution.

```
User Input
    ↓
[DIRECT Agent]
    ↓
Output
```

### Characteristics
- **Workers**: 1 agent
- **System Prompt**: Single shared prompt from configuration
- **LLM Model**: Shared configuration model
- **Tools**: Enabled but no looping (ADK handles if needed)
- **State Management**: Uses provided state_schema
- **Callbacks**: Supports before/after callbacks

### Consolidation
- **Method**: One-shot execution
- **Output**: Direct LLM response
- **No aggregation needed**: Single agent, single response
- **Use Case**: Simple, deterministic tasks

### Configuration Example
```yaml
agent:
  pattern: direct
  model: gemini-2.0-flash
  instruction: "You are a helpful assistant."
  tools: [knowledge, search]
```

### When to Use
- ✅ Simple requests with single best answer
- ✅ Fast response needed (no multi-step)
- ✅ User preferences clear in instruction
- ❌ Complex reasoning required
- ❌ Multiple viewpoints needed

---

## 2. REACT Strategy

### Overview
Single LlmAgent with iterative tool use. Reason-Act-Observe loop.

```
User Input
    ↓
[REACT Agent Loop]
├─ Think/Reason
├─ Use Tool
├─ Observe Output
└─ Loop until done
    ↓
Output
```

### Characteristics
- **Workers**: 1 agent
- **System Prompt**: Single shared prompt
- **LLM Model**: Shared model
- **Tools**: Enabled with iterative looping
- **Iteration**: Built into ADK framework (reasoning loop)
- **State**: Maintains across tool calls

### Consolidation
- **Method**: Iterative refinement via tool use
- **Tool Feedback**: Each tool output informs next step
- **Terminal Condition**: LLM decides when done
- **Output Quality**: Improved by iterative reasoning
- **Use Case**: Tool-heavy tasks, information gathering

### Configuration Example
```yaml
agent:
  pattern: react
  model: gemini-2.0-flash
  instruction: "Think step-by-step. Use tools to gather information."
  tools: [knowledge, search, code_execution]
```

### When to Use
- ✅ Multi-step information gathering
- ✅ Tool-heavy workflows
- ✅ Need reasoning with observation
- ✅ Flexible task execution
- ❌ Low latency critical
- ❌ Deterministic flow required

---

## 3. SEQUENTIAL Strategy

### Overview
Multiple agents running in strict order. Each agent's output feeds into the next.

```
User Input
    ↓
[Agent Step 1] → [Agent Step 2] → [Agent Step 3]
    ↓
Output
```

### Characteristics
- **Workers**: N agents (configurable, default 2)
- **System Prompt**: ALL agents get SAME prompt
- **LLM Model**: ALL agents use SHARED model
- **Tools**: All agents access SAME tools
- **Order**: Strict sequential execution
- **Information Flow**: Output of step N → Input of step N+1

### Consolidation
- **Method**: Last agent's output is final result
- **Context Passing**: Automatic via sequential flow
- **No Merging**: Each step builds on previous
- **Intermediate Results**: Available but not merged
- **Use Case**: Pipeline-style workflows

### Code Implementation
```python
# All agents have:
# - SAME instruction: rt.instruction
# - SAME model: rt.model
# - SAME tools: rt.tools
# - Sequential execution order

agents = [
    Agent(instruction=rt.instruction, model=rt.model, tools=rt.tools) 
    for i in range(num_steps)
]
```

### Configuration Example
```yaml
agent:
  pattern: sequential
  model: gemini-2.0-flash
  instruction: "You are step ${STEP_NUMBER} of a pipeline."
  tools: [knowledge, search]
execution:
  steps: 3  # Create 3 sequential steps
```

### When to Use
- ✅ Linear workflow (step 1 → step 2 → step 3)
- ✅ Each step refines previous output
- ✅ Dependency chain clear
- ❌ Multiple perspectives needed
- ❌ Parallel exploration needed
- ❌ Independent sub-tasks

### Example Workflow
```
1. Researcher Agent: Gather information
   Input: User query
   Output: Research summary
         ↓
2. Analyst Agent: Analyze information
   Input: Research summary
   Output: Analysis with insights
         ↓
3. Synthesizer Agent: Create recommendations
   Input: Analysis
   Output: Final recommendations
```

---

## 4. PARALLEL Strategy

### Overview
Multiple independent agents running concurrently. Results aggregated.

```
User Input
    ↓
├─ [Worker 1] ─┐
├─ [Worker 2] ─┼─→ [Aggregation]
└─ [Worker N] ─┘
    ↓
Output
```

### Characteristics
- **Workers**: N agents (configurable, default 2)
- **System Prompt**: ALL agents get SAME prompt
- **LLM Model**: ALL agents use SHARED model
- **Tools**: All agents access SAME tools
- **Execution**: Parallel/concurrent
- **Independence**: Agents are independent
- **Synchronization**: Wait for all agents to complete

### Consolidation
- **Method**: ADK's ParallelAgent aggregates results
- **Strategy**: Combines all worker outputs
- **Merging**: Default ADK behavior (detailed in docs)
- **Ordering**: Workers run concurrently (unordered)
- **Use Case**: Multiple perspectives on same problem
- **Latency**: Single longest worker

### Code Implementation
```python
# Create N identical workers
workers = [
    Agent(
        name=f"parallel_worker_{i}",
        model=rt.model,
        instruction=rt.instruction,
        tools=rt.tools
    )
    for i in range(num_workers)
]

# Aggregate via ParallelAgent
agent = ParallelAgent(
    name="parallel_agent",
    sub_agents=workers  # All run concurrently
)
```

### Configuration Example
```yaml
agent:
  pattern: parallel
  model: gemini-2.0-flash
  instruction: "You are an expert in your domain."
  tools: [knowledge, search]
execution:
  workers: 3  # Run 3 workers in parallel
```

### When to Use
- ✅ Multiple viewpoints on same query
- ✅ Diverse expert opinions
- ✅ Parallel exploration beneficial
- ✅ Error recovery (if one fails)
- ❌ Sequential dependencies
- ❌ Resource constraints
- ❌ Latency critical

### Example Use Case
```
Question: "Analyze this investment opportunity"

Worker 1 (Financial Expert):
  - Balance sheet analysis
  - ROI calculation
  - Risk metrics

Worker 2 (Market Analyst):
  - Market trends
  - Competition analysis
  - Growth potential

Worker 3 (Operational Expert):
  - Execution feasibility
  - Operational risks
  - Timeline assessment

→ All run in parallel
→ Results merged into comprehensive analysis
```

---

## 5. LOOP Strategy

### Overview
Single agent executing iteratively up to max iterations.

```
User Input
    ↓
Iteration 1:
[Agent] → Evaluate → Continue?
    ↓
Iteration 2:
[Agent] → Evaluate → Continue?
    ↓
...
Iteration N (max):
[Agent] → Stop
    ↓
Output
```

### Characteristics
- **Workers**: 1 agent (repeated)
- **System Prompt**: SAME prompt every iteration
- **LLM Model**: SHARED model
- **Tools**: SAME tools available
- **Max Iterations**: Configurable (default 3)
- **Termination**: Max iterations or self-stopping
- **State**: Maintained across iterations

### Consolidation
- **Method**: Automatic by LoopAgent framework
- **Iteration Logic**: LLM decides continuation
- **Refinement**: Each loop refines previous result
- **Output**: Final iteration result
- **Use Case**: Refinement, retries, gradual improvement

### Code Implementation
```python
# Single worker repeated
worker = Agent(
    name="loop_worker",
    model=rt.model,
    instruction=rt.instruction,
    tools=rt.tools
)

# Loop runs same agent multiple times
agent = LoopAgent(
    name="loop_agent",
    sub_agents=[worker],
    max_iterations=rt.max_iterations  # e.g., 3
)
```

### Configuration Example
```yaml
agent:
  pattern: loop
  model: gemini-2.0-flash
  instruction: "Refine your answer iteratively."
execution:
  max_iterations: 5  # Max 5 loops
```

### When to Use
- ✅ Iterative refinement needed
- ✅ Answer improvement with feedback
- ✅ Self-correction mechanism
- ✅ Retry failed attempts
- ❌ Fixed step count needed
- ❌ Different agents per step
- ❌ Fast response critical

### Example Iteration
```
Iteration 1:
  Input: "Write a blog post about AI"
  Output: 500-word draft
  Quality: Moderate
         ↓
Iteration 2:
  Input: "Make it more engaging and add examples"
  Output: 800-word version with examples
  Quality: Better
         ↓
Iteration 3:
  Input: "Add SEO optimization"
  Output: Final 1000-word SEO-optimized post
  Quality: Excellent (stop)
```

---

## 6. ROUTER Strategy

### Overview
Main LlmAgent intelligently routes to specialist sub-agents.

```
User Input
    ↓
[Router LlmAgent]
├─ Analyze request type
├─ Select best specialist
    ↓
[Specialist Agent 1] ─┐
[Specialist Agent 2] ─┼─→ [Consolidate]
[Specialist Agent N] ─┘
    ↓
Output
```

### Characteristics
- **Main Agent**: LlmAgent with routing logic
- **System Prompt**: DIFFERENT for main vs specialists
  - Main: "Route to best specialist"
  - Specialists: Shared general prompt
- **LLM Model**: SHARED for all (main + specialists)
- **Tools**: ALL agents access SAME tools
- **Specialists**: Named by configuration (e.g., "research", "analysis")
- **Routing**: LLM intelligently selects specialist

### Consolidation
- **Method**: LLM-based routing decision
- **Strategy**: One specialist selected and executed
- **Output Source**: Selected specialist's output
- **Selection Logic**: Main agent decides based on request
- **No Merging**: Single specialist per request
- **Efficiency**: Only relevant specialist runs
- **Use Case**: Different agents for different tasks

### Code Implementation
```python
# Main agent with routing instruction
agent = LlmAgent(
    name="router_agent",
    model=rt.model,
    instruction=(
        "Route the request to the best specialist. "
        f"Available specialists: {', '.join(specialists)}"
    ),
    tools=rt.tools,
    sub_agents=[  # Specialist agents
        Agent(
            name=f"router_specialist_{name}",
            model=rt.model,
            instruction=rt.instruction,  # SHARED prompt
            tools=rt.tools
        )
        for name in rt.specialists
    ]
)
```

### Configuration Example
```yaml
agent:
  pattern: router
  model: gemini-2.0-flash
  instruction: "Route request to appropriate specialist."
execution:
  specialists: [research, analysis, reporting]
  # Creates 3 specialist agents
```

### When to Use
- ✅ Multiple distinct task types
- ✅ Dynamic specialist selection
- ✅ Different flow per task
- ✅ Efficient resource use
- ✅ Expertise-based routing
- ❌ Need all perspectives
- ❌ Parallel exploration
- ❌ Fixed task sequence

### Example Routing
```
Request: "Find research papers on quantum computing"

Router Analysis:
├─ Type: Information gathering
├─ Complexity: High
└─ Best specialist: "research"
   ↓
[Research Specialist Agent]
├─ Search knowledge base
├─ Aggregate results
└─ Return formatted papers

Output: Research papers list
```

---

## 7. SUPERVISOR Strategy

### Overview
Main LlmAgent supervises multiple worker agents.

```
User Input
    ↓
[Supervisor LlmAgent]
├─ Coordinate workers
├─ Aggregate results
    ↓
[Worker 1]  ─┐
[Worker 2]  ─┼─→ [Supervisor Aggregates]
[Worker N]  ─┘
    ↓
Output
```

### Characteristics
- **Main Agent**: LlmAgent with supervision role
- **System Prompt**: SAME for supervisor and workers
- **LLM Model**: SHARED for all
- **Tools**: ALL agents access SAME tools
- **Workers**: N independent agents
- **Coordination**: Main agent coordinates results
- **Aggregation**: Supervisor explicitly merges outputs
- **Authority**: Supervisor makes final decisions

### Consolidation
- **Method**: Supervisor LLM aggregates results
- **Strategy**: Combines all worker outputs
- **Decision Making**: Supervisor synthesizes results
- **Conflict Resolution**: Supervisor handles disagreements
- **Output Quality**: Enhanced by multiple workers + synthesis
- **Latency**: All workers run, wait for all
- **Use Case**: Consensus building, oversight

### Code Implementation
```python
# Create N worker agents with SAME prompt
workers = [
    Agent(
        name=f"supervisor_worker_{i}",
        model=rt.model,
        instruction=rt.instruction,  # SHARED
        tools=rt.tools
    )
    for i in range(num_workers)
]

# Supervisor oversees them
agent = LlmAgent(
    name="supervisor_agent",
    model=rt.model,
    instruction=rt.instruction,  # SAME as workers
    tools=rt.tools,
    sub_agents=workers
)
```

### Configuration Example
```yaml
agent:
  pattern: supervisor
  model: gemini-2.0-flash
  instruction: "Coordinate with workers and synthesize results."
execution:
  workers: 3  # 3 workers + 1 supervisor
```

### When to Use
- ✅ Consensus-based decision making
- ✅ Oversight and validation
- ✅ Multiple workers collaboration
- ✅ Quality through aggregation
- ✅ Conflict resolution
- ❌ Strict sequential flow
- ❌ Different agents per role
- ❌ Fast response required

### Example Supervision
```
Task: "Make a hiring decision"

Supervisor coordinates:

Worker 1: Evaluate technical skills
  Output: "Excellent coding skills, strong algorithms"

Worker 2: Assess cultural fit
  Output: "Good alignment with team values"

Worker 3: Review communication
  Output: "Clear communicator, good at explanation"

Supervisor synthesizes:
  "All workers agree this candidate is strong. 
   Recommend hire with offer of $X."
```

---

## 8. PLANNER_EXECUTOR Strategy

### Overview
Two specialized agents: Planner (creates plan), Executor (executes plan).

```
User Input
    ↓
[Planner Agent]
├─ Instruction: "Create a step-by-step plan"
├─ Output: Detailed plan
    ↓
[Executor Agent]
├─ Instruction: "Execute the plan step by step"
├─ Input: The plan from planner
└─ Output: Execution results
    ↓
Final Output
```

### Characteristics
- **Agents**: 2 (planner + executor)
- **System Prompts**: **DIFFERENT**
  - Planner: "Create a step-by-step plan"
  - Executor: "Execute the plan step by step"
- **LLM Model**: SHARED for both
- **Tools**: SHARED for both
- **Sequence**: Planner → Executor (strict order)
- **Information**: Planner output becomes executor input
- **Specialization**: Each focused on specific role

### Consolidation
- **Method**: Sequential with information flow
- **Plan**: Created in step 1
- **Execution**: Based on step 1 plan
- **Output**: Executor's execution results
- **Quality**: High due to separation of concerns
- **Advantage**: Explicit planning before action
- **Use Case**: Complex projects, structured approach

### Code Implementation
```python
# DIFFERENT instructions per agent
planner = Agent(
    name="planner_agent",
    model=rt.model,
    instruction="Create a step-by-step plan to address the request.",
    tools=rt.tools
)

executor = Agent(
    name="executor_agent",
    model=rt.model,
    instruction="Execute the plan step by step.",  # DIFFERENT
    tools=rt.tools
)

# Sequential execution
agent = SequentialAgent(
    sub_agents=[planner, executor]
)
```

### Configuration Example
```yaml
agent:
  pattern: planner_executor
  model: gemini-2.0-flash
  instruction: "You are part of a planning system."
  tools: [knowledge, code_execution, search]
```

### When to Use
- ✅ Large/complex tasks
- ✅ Need explicit planning phase
- ✅ Clear execution phases
- ✅ Separation of concerns
- ✅ Structured approach required
- ❌ Simple one-step tasks
- ❌ Real-time decisions needed
- ❌ Plan cannot cover all cases

### Example Workflow
```
User: "Organize our team's summer vacation trip"

Step 1 - PLANNER:
  Creates plan:
  1. Determine budget and dates
  2. Research destinations
  3. Create itinerary
  4. Book accommodations
  5. Arrange transportation
  6. Create budget spreadsheet

Step 2 - EXECUTOR:
  Executes the plan:
  1. ✓ Budget and dates finalized
  2. ✓ Top 3 destinations researched
  3. ✓ 7-day itinerary created
  4. ✓ 3 hotels compared and booked
  5. ✓ Flight and car rental arranged
  6. ✓ Excel budget tracker created

Output: Complete trip plan with bookings
```

---

## 9. EVALUATOR_OPTIMIZER Strategy

### Overview
Single agent in iterative loop: generate, evaluate, improve.

```
User Input
    ↓
Iteration 1:
[Worker]
├─ Instruction: "Generate, evaluate, improve iteratively"
├─ Generate solution
├─ Self-evaluate critically
└─ Improve based on evaluation
    ↓
Iteration 2-N:
[Same worker repeats]
├─ Refine based on previous evaluation
└─ Continue until satisfied
    ↓
Final Output
```

### Characteristics
- **Workers**: 1 agent (iterated)
- **System Prompt**: SPECIALIZED instruction
  - "Generate solution, evaluate it critically, and improve it"
  - Emphasizes self-reflection and improvement
- **LLM Model**: SHARED
- **Tools**: SHARED
- **Iterations**: Up to max_iterations
- **Self-Improvement**: Built into instruction
- **Termination**: Max iterations or self-stopping

### Consolidation
- **Method**: Continuous self-improvement loop
- **Iteration Logic**: Agent evaluates own work
- **Quality**: Improves with each iteration
- **Output**: Final refined version
- **Process**: Generate → Evaluate → Improve → Repeat
- **Use Case**: Quality improvement, perfecting output

### Code Implementation
```python
worker = Agent(
    name="evaluator_optimizer_worker",
    model=rt.model,
    instruction=(
        "Generate a solution, evaluate it critically, and improve it. "
        "Repeat until satisfied."
    ),  # SPECIALIZED instruction
    tools=rt.tools
)

# Loop with self-improvement
agent = LoopAgent(
    sub_agents=[worker],
    max_iterations=rt.max_iterations
)
```

### Configuration Example
```yaml
agent:
  pattern: evaluator_optimizer
  model: gemini-2.0-flash
  instruction: "Focus on quality and continuous improvement."
execution:
  max_iterations: 4  # Allow 4 refinement cycles
```

### When to Use
- ✅ Output quality critical
- ✅ Perfecting required
- ✅ Complex generation task
- ✅ Self-review beneficial
- ✅ High standards needed
- ❌ Fast response required
- ❌ Deterministic output
- ❌ Real-time interactions

### Example Iteration
```
Task: "Write a technical proposal"

Iteration 1 - GENERATE & EVALUATE:
  Generated: Draft proposal (technical but dry)
  Evaluation: 
    - ✓ Technically correct
    - ✗ Lacks clarity for non-technical stakeholders
    - ✗ Missing business value statement
  Improvement needed: Add business context

Iteration 2 - REGENERATE & EVALUATE:
  Generated: Revised proposal (added business value)
  Evaluation:
    - ✓ Technically correct
    - ✓ Business value clear
    - ✗ Budget section lacks detail
  Improvement needed: Expand budget breakdown

Iteration 3 - REGENERATE & EVALUATE:
  Generated: Final proposal (complete)
  Evaluation:
    - ✓ Technically sound
    - ✓ Business value prominent
    - ✓ Detailed budget
    - ✓ Clear timeline
  Status: Satisfied (STOP)

Output: High-quality, comprehensive proposal
```

---

## 10. HUMAN_IN_LOOP Strategy

### Overview
Two specialized agents with human approval gate between them.

```
User Input
    ↓
[Proposer Agent]
├─ Instruction: "Propose a clear, actionable solution"
├─ Output: Proposed solution
    ↓
[HUMAN APPROVAL GATE]
├─ User reviews and approves/rejects
    ↓
[Completer Agent]
├─ Instruction: "Complete the user-approved action"
├─ Input: User-approved proposal
└─ Output: Completed task
    ↓
Final Output
```

### Characteristics
- **Agents**: 2 (proposer + completer)
- **System Prompts**: **DIFFERENT**
  - Proposer: "Propose a clear, actionable solution"
  - Completer: "Complete the user-approved action"
- **LLM Model**: SHARED for both
- **Tools**: SHARED for both
- **Approval Gate**: Human review between steps
- **Dependency**: Completer depends on human approval
- **Specialization**: Each focused on specific role

### Consolidation
- **Method**: Sequential with human validation
- **Proposal**: Proposer creates draft
- **Human Review**: Human evaluates and approves
- **Execution**: Completer executes approved plan
- **Output**: Completed approved action
- **Validation**: Human ensures safety/appropriateness
- **Use Case**: High-stakes decisions, compliance

### Code Implementation
```python
proposer = Agent(
    name="human_in_loop_proposer",
    model=rt.model,
    instruction="Propose a clear, actionable solution for the user's request.",
    tools=rt.tools
)

completer = Agent(
    name="human_in_loop_completer",
    model=rt.model,
    instruction="Complete the user-approved action.",  # DIFFERENT
    tools=rt.tools
)

# Sequential with human approval between them
agent = SequentialAgent(
    sub_agents=[proposer, completer]
    # Note: Human approval gate is configured separately
)
```

### Configuration Example
```yaml
agent:
  pattern: human_in_loop
  model: gemini-2.0-flash
  instruction: "Consider safety and compliance."
execution:
  require_approval: true  # REQUIRED for this pattern
```

### When to Use
- ✅ High-risk decisions
- ✅ Compliance requirements
- ✅ Security sensitive tasks
- ✅ Financial transactions
- ✅ User consent needed
- ✅ Audit trail required
- ❌ Autonomous tasks
- ❌ Time-critical decisions
- ❌ Too many decisions to review

### Example Workflow
```
Task: "Process refund request for $5000"

Step 1 - PROPOSER:
  Analysis:
  - Customer order #12345
  - Purchase date: 30 days ago
  - Reason: Product defective
  
  Proposal:
  "Issue $5000 refund and send replacement item"

  ↓
[HUMAN APPROVAL GATE]
  Reviewer: Finance Manager
  Review: Checks policy, customer history, inventory
  Decision: ✓ APPROVED
  Reason: "Within policy, customer has good history"
  
  ↓
Step 2 - COMPLETER:
  Execution:
  - ✓ Created refund transaction ($5000)
  - ✓ Initiated return shipping
  - ✓ Marked item for replacement
  - ✓ Sent customer notification
  - ✓ Logged in audit system

Output: Refund processed and logged for compliance
```

---

## Summary Comparison

### By Consolidation Strategy

**One-Shot (No Consolidation)**
- DIRECT: Single response
- REACT: Iterative tool use (but single agent)

**Sequential Consolidation**
- SEQUENTIAL: Last step output
- PLANNER_EXECUTOR: Execute based on plan
- HUMAN_IN_LOOP: Execute after approval

**Parallel Consolidation**
- PARALLEL: Aggregate multiple outputs
- SUPERVISOR: Supervisor merges results

**Intelligent Consolidation**
- ROUTER: LLM selects specialist
- LOOP: Self-refinement consolidation
- EVALUATOR_OPTIMIZER: Self-improvement consolidation

### By System Prompt Variation

**Shared System Prompt (All workers identical)**
- DIRECT, REACT, SEQUENTIAL, PARALLEL, LOOP, SUPERVISOR
- Advantage: Consistent behavior, predictable scaling

**Different System Prompts (Specialized roles)**
- ROUTER: Main + specialists
- PLANNER_EXECUTOR: Planner vs Executor
- HUMAN_IN_LOOP: Proposer vs Completer
- EVALUATOR_OPTIMIZER: Special self-evaluation instruction
- Advantage: Clear role separation, focused expertise

### By Execution Model

**Single Agent**
- DIRECT, REACT, LOOP, EVALUATOR_OPTIMIZER

**Multiple Sequential**
- SEQUENTIAL, PLANNER_EXECUTOR, HUMAN_IN_LOOP

**Multiple Parallel**
- PARALLEL, SUPERVISOR

**Intelligent Routing**
- ROUTER

---

## Selection Decision Tree

```
What do you need?

1. Simple one-shot response?
   → DIRECT or REACT

2. Multiple steps in order?
   → SEQUENTIAL

3. Different phases with different instructions?
   → PLANNER_EXECUTOR (if 2 phases)
   → HUMAN_IN_LOOP (if approval needed)

4. Multiple perspectives on same question?
   → PARALLEL (concurrent)
   → SUPERVISOR (with oversight)

5. Route to specialist based on request?
   → ROUTER

6. Iterative improvement?
   → LOOP (generic iterations)
   → EVALUATOR_OPTIMIZER (with self-evaluation)

7. Need human approval before action?
   → HUMAN_IN_LOOP
```

---

## Production Deployment Considerations

### Performance Implications

**Fastest**
- DIRECT: Single call, immediate response
- REACT: Single agent, variable iterations

**Moderate Speed**
- LOOP, EVALUATOR_OPTIMIZER: Self-contained iterations
- SEQUENTIAL: Ordered steps

**Slower (Latency-wise)**
- PARALLEL, SUPERVISOR: Wait for all workers
- ROUTER, PLANNER_EXECUTOR: Multiple sequential calls

### Resource Usage

**Minimal**
- DIRECT, REACT: 1 agent call

**Moderate**
- SEQUENTIAL, PLANNER_EXECUTOR, HUMAN_IN_LOOP: 2-3 calls
- ROUTER: 2-3 calls (main + selected specialist)
- LOOP, EVALUATOR_OPTIMIZER: N calls (up to max_iterations)

**High**
- PARALLEL, SUPERVISOR: N workers running concurrently
- EVALUATOR_OPTIMIZER: N iterations × 1 agent

### Cost Considerations

**Lower cost**: Fewer agents or iterations (DIRECT < REACT < SEQUENTIAL)
**Medium cost**: Parallelization adds concurrent calls (PARALLEL, SUPERVISOR)
**Variable cost**: Depends on self-stopping (LOOP, EVALUATOR_OPTIMIZER)

---

## Implementation Notes

### All Strategies Share
- Same base RuntimeContext (model, instruction, tools)
- Same error handling framework
- Same callback system (before/after)
- Same state/output schema support
- Same code_executor availability

### Configuration Hierarchy
1. Base configuration (model, tools, instruction)
2. Pattern-specific (max_iterations, require_approval, specialists)
3. Strategy-specific (num_workers, num_steps)

### Best Practices
1. Start with DIRECT, upgrade to REACT if needed
2. Use SEQUENTIAL/PLANNER_EXECUTOR for workflow clarity
3. Use ROUTER for well-defined task types
4. Use PARALLEL/SUPERVISOR for diverse perspectives
5. Use HUMAN_IN_LOOP for compliance requirements
6. Use EVALUATOR_OPTIMIZER for quality critical tasks

---

This architecture ensures each pattern excels at its intended use case while maintaining a consistent, composable foundation.
