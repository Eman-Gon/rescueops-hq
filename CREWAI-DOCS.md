# CrewAI Documentation — Comprehensive Reference

> Scraped from https://docs.crewai.com on June 16, 2026.

---

## Table of Contents

1. [What is CrewAI?](#what-is-crewai)
2. [Architecture Overview](#architecture-overview)
3. [Agents](#agents)
4. [Crews](#crews)
5. [Flows](#flows)
6. [Tasks & Processes](#tasks--processes)
7. [Tools (40+ built-in)](#tools)
8. [MCP Integration](#mcp-integration)
9. [Memory System](#memory-system)
10. [Knowledge Sources](#knowledge-sources)
11. [Observability Integrations](#observability-integrations)
12. [Enterprise (CrewAI AMP)](#enterprise-crewai-amp)
13. [Full Documentation Index](#full-documentation-index)

---

## What is CrewAI?

CrewAI is the **leading open-source framework for orchestrating autonomous AI agents** and building complex workflows. It combines:

- **CrewAI Flows** — structured, event-driven workflows that manage state and control execution (the "backbone")
- **CrewAI Crews** — teams of autonomous agents that collaborate to solve specific tasks (the "intelligence")

Over **100,000 developers** have been certified through CrewAI community courses.

---

## Architecture Overview

```
Flow (manager/process definition)
  └── manages state & decides what to do next
  └── delegates complex tasks to Crew(s)
        └── Agents collaborate to complete the task
        └── Return result to the Flow
  └── continues execution based on result
```

### Key Feature Pillars

| Feature | Description |
|---|---|
| Production-Grade Flows | Reliable, stateful workflows for long-running processes |
| Autonomous Crews | Teams of agents that plan, execute, and collaborate |
| Flexible Tools | Connect to any API, database, or local tool |
| Enterprise Security | RBAC, SSO, PII redaction, secrets management |
| MCP Support | Native Model Context Protocol integration |
| Observability | Built-in tracing + 15+ external integrations |

### When to Use Crews vs. Flows

| Use Case | Architecture |
|---|---|
| Simple automation | Single Flow with Python tasks |
| Complex research | Flow → Crew performing research |
| Application backend | Flow handles API → Crew generates content → Flow saves to DB |

**Rule of thumb: always start with a Flow, use Crews within Flow steps for autonomous, complex subtasks.**

---

## Agents

An `Agent` is an autonomous unit that can: perform tasks, make decisions, use tools, collaborate with other agents, maintain memory, and delegate tasks.

### Agent Attributes (full list)

| Parameter | Type | Default | Description |
|---|---|---|---|
| `role` | `str` | required | Agent's function/expertise |
| `goal` | `str` | required | Individual objective guiding decisions |
| `backstory` | `str` | required | Context and personality |
| `llm` | `Union[str, LLM, Any]` | `"gpt-4"` | Language model powering the agent |
| `tools` | `List[BaseTool]` | `[]` | Capabilities/functions available |
| `function_calling_llm` | `Optional[Any]` | None | Separate LLM for tool calling |
| `max_iter` | `int` | 20 | Max iterations before forced answer |
| `max_rpm` | `Optional[int]` | None | Max requests per minute (rate limiting) |
| `max_execution_time` | `Optional[int]` | None | Max execution time in seconds |
| `verbose` | `bool` | False | Enable detailed execution logs |
| `allow_delegation` | `bool` | False | Allow delegating to other agents |
| `step_callback` | `Optional[Any]` | None | Called after each agent step |
| `cache` | `bool` | True | Enable tool result caching |
| `system_template` | `Optional[str]` | None | Custom system prompt template |
| `prompt_template` | `Optional[str]` | None | Custom prompt template |
| `response_template` | `Optional[str]` | None | Custom response template |
| `max_retry_limit` | `int` | 2 | Retries on error |
| `respect_context_window` | `bool` | True | Auto-summarize to fit context window |
| `code_execution_mode` | `Literal["safe","unsafe"]` | `"safe"` | Docker (safe) or direct (unsafe) |
| `multimodal` | `bool` | False | Enable text + visual processing |
| `inject_date` | `bool` | False | Auto-inject current date into tasks |
| `date_format` | `str` | `"%Y-%m-%d"` | Format for injected date |
| `reasoning` | `bool` | False | Agent reflects/plans before executing |
| `max_reasoning_attempts` | `Optional[int]` | None | Max planning iterations |
| `embedder` | `Optional[Dict[str, Any]]` | None | Custom embedder config |
| `knowledge_sources` | `Optional[List[BaseKnowledgeSource]]` | None | Domain knowledge bases |
| `use_system_prompt` | `Optional[bool]` | True | Set False for o1 model compatibility |

### Creating Agents — YAML (Recommended)

```yaml
# src/your_project/config/agents.yaml
researcher:
  role: "{topic} Senior Data Researcher"
  goal: "Uncover cutting-edge developments in {topic}"
  backstory: "You're a seasoned researcher with a knack for uncovering the latest developments in {topic}."

reporting_analyst:
  role: "{topic} Reporting Analyst"
  goal: "Create detailed reports based on {topic} data analysis"
  backstory: "You're a meticulous analyst with a keen eye for detail."
```

```python
from crewai import Agent, Crew, Process
from crewai.project import CrewBase, agent, crew
from crewai_tools import SerperDevTool

@CrewBase
class LatestAiDevelopmentCrew():
    agents_config = "config/agents.yaml"

    @agent
    def researcher(self) -> Agent:
        return Agent(
            config=self.agents_config['researcher'],
            verbose=True,
            tools=[SerperDevTool()]
        )
```

### Common Agent Patterns

**Research Agent**
```python
research_agent = Agent(
    role="Research Analyst",
    goal="Find and summarize information",
    backstory="Experienced researcher",
    tools=[SerperDevTool()],
    verbose=True
)
```

**Reasoning Agent (for complex planning)**
```python
reasoning_agent = Agent(
    role="Strategic Planner",
    goal="Analyze complex problems and create plans",
    backstory="Expert strategic planner",
    reasoning=True,
    max_reasoning_attempts=3,
    max_iter=30,
    verbose=True
)
```

**Multimodal Agent**
```python
multimodal_agent = Agent(
    role="Visual Content Analyst",
    goal="Analyze text and visual content",
    backstory="Specialized in multimodal analysis",
    multimodal=True,
    verbose=True
)
```

**Date-Aware Agent**
```python
strategic_agent = Agent(
    role="Market Analyst",
    goal="Track market movements with precise date references",
    backstory="Expert in time-sensitive financial analysis",
    inject_date=True,
    date_format="%B %d, %Y",
    reasoning=True,
    verbose=True
)
```

### Direct Agent Interaction (`kickoff()`)

Agents can be used without a full Crew via `.kickoff()`:

```python
result = researcher.kickoff("What are the latest developments in LLMs?")
print(result.raw)

# With structured output
from pydantic import BaseModel
from typing import List

class ResearchFindings(BaseModel):
    main_points: List[str]
    key_technologies: List[str]
    future_predictions: str

result = researcher.kickoff(
    "Summarize AI developments in 2025",
    response_format=ResearchFindings
)
print(result.pydantic.main_points)
```

`kickoff()` returns a `LiteAgentOutput` with: `.raw`, `.pydantic`, `.agent_role`, `.usage_metrics`.

Also supports `kickoff_async()` for async workflows.

### Context Window Management

- `respect_context_window=True` (default): auto-summarizes when token limit is hit — best for most use cases.
- `respect_context_window=False`: halts execution on overflow — use for legal, medical, or precision-critical tasks.

---

## Crews

A crew is a **collaborative group of agents** working together to achieve a set of tasks.

### Crew Attributes

| Parameter | Description |
|---|---|
| `tasks` | List of tasks assigned to the crew |
| `agents` | List of agents in the crew |
| `process` | `Process.sequential` (default) or `Process.hierarchical` |
| `verbose` | Logging verbosity |
| `manager_llm` | Required for hierarchical process |
| `manager_agent` | Custom manager agent for hierarchical process |
| `function_calling_llm` | LLM for tool calls across all agents |
| `memory` | Enable short-term, long-term, and entity memory |
| `cache` | Cache tool results (default: True) |
| `embedder` | Embedder config (default: `{"provider": "openai"}`) |
| `max_rpm` | Rate limit (overrides individual agent limits) |
| `step_callback` | Called after each agent step |
| `task_callback` | Called after each task completes |
| `output_log_file` | Save logs to file (`.txt` or `.json`) |
| `planning` | Enable pre-execution crew-level planning |
| `planning_llm` | LLM for the AgentPlanner |
| `knowledge_sources` | Crew-level knowledge accessible to all agents |
| `stream` | Enable real-time streaming output |
| `before_kickoff_callbacks` | Callables run before crew starts |
| `after_kickoff_callbacks` | Callables run after crew finishes |
| `tracing` | OpenTelemetry tracing control |
| `checkpoint` | Auto-checkpoint after tasks |

### Creating Crews — YAML + Decorators (Recommended)

```python
from crewai import Agent, Crew, Task, Process
from crewai.project import CrewBase, agent, task, crew, before_kickoff, after_kickoff

@CrewBase
class YourCrewName:
    agents_config = 'config/agents.yaml'
    tasks_config = 'config/tasks.yaml'

    @before_kickoff
    def prepare_inputs(self, inputs):
        inputs['additional_data'] = "Extra info"
        return inputs

    @after_kickoff
    def process_output(self, output):
        output.raw += "\nPost-processed."
        return output

    @agent
    def agent_one(self) -> Agent:
        return Agent(config=self.agents_config['agent_one'], verbose=True)

    @task
    def task_one(self) -> Task:
        return Task(config=self.tasks_config['task_one'])

    @crew
    def crew(self) -> Crew:
        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            process=Process.sequential,
            verbose=True,
        )
```

### Kickoff Methods

| Method | Type | Description |
|---|---|---|
| `kickoff()` | Sync | Standard execution |
| `kickoff_for_each()` | Sync | Sequential execution per input item |
| `akickoff()` | Native async | True async/await throughout |
| `akickoff_for_each()` | Native async | Async execution per input item |
| `kickoff_async()` | Thread-based | Wraps sync in `asyncio.to_thread` |
| `kickoff_for_each_async()` | Thread-based | Thread-based for each input |

```python
# Standard
result = my_crew.kickoff(inputs={"topic": "AI"})

# For each item in a list
results = my_crew.kickoff_for_each(inputs=[{"topic": "AI"}, {"topic": "ML"}])

# Native async
result = await my_crew.akickoff(inputs={"topic": "AI"})
```

### Crew Output (`CrewOutput`)

| Attribute | Type | Description |
|---|---|---|
| `raw` | `str` | Raw string output |
| `pydantic` | `Optional[BaseModel]` | Structured Pydantic model |
| `json_dict` | `Optional[Dict]` | JSON output as dictionary |
| `tasks_output` | `List[TaskOutput]` | Individual task outputs |
| `token_usage` | `Dict[str, Any]` | LLM performance metrics |

### Streaming

```python
crew = Crew(agents=[researcher], tasks=[task], stream=True)
streaming = crew.kickoff(inputs={"topic": "AI"})
for chunk in streaming:
    print(chunk.content, end="", flush=True)
result = streaming.result
```

### Checkpointing

```python
# Simple — save to .checkpoints/ after every task
crew = Crew(agents=[...], tasks=[...], checkpoint=True)
crew.kickoff(inputs={"topic": "AI trends"})

# Full control
from crewai.state.checkpoint_config import CheckpointConfig
crew = Crew(
    agents=[...], tasks=[...],
    checkpoint=CheckpointConfig(
        location="./.checkpoints",
        on_events=["task_completed"],
        max_checkpoints=5,
    )
)

# Resume from checkpoint
crew = Crew.from_checkpoint(".checkpoints/latest.json")
crew.kickoff()
```

### Replay a Specific Task

```bash
crewai log-tasks-outputs  # see task IDs
crewai replay -t <task_id>
```

---

## Flows

Flows provide structured, **event-driven workflows** that manage state and control execution.

### Core Decorators

| Decorator | Purpose |
|---|---|
| `@start()` | Marks entry points; multiple starts can run in parallel |
| `@listen(method)` | Triggers when the named method completes |
| `@router(method)` | Defines conditional branching based on method output |
| `@human_feedback(...)` | Pauses for human input (requires v1.8.0+) |

### Conditional Combinators

- `or_(method_a, method_b)` — triggers listener when **any** emits output
- `and_(method_a, method_b)` — triggers listener only when **all** emit output

### Basic Flow Example

```python
from crewai.flow.flow import Flow, listen, start
from litellm import completion

class ExampleFlow(Flow):
    model = "gpt-4o-mini"

    @start()
    def generate_city(self):
        response = completion(model=self.model, messages=[{"role": "user", "content": "Name a random city."}])
        random_city = response["choices"][0]["message"]["content"]
        self.state["city"] = random_city
        return random_city

    @listen(generate_city)
    def generate_fun_fact(self, random_city):
        response = completion(model=self.model, messages=[{"role": "user", "content": f"Fun fact about {random_city}"}])
        return response["choices"][0]["message"]["content"]

flow = ExampleFlow()
result = flow.kickoff()
```

### State Management

**Unstructured (flexible dict)**
```python
class MyFlow(Flow):
    @start()
    def first(self):
        self.state['counter'] = 0
        self.state['message'] = "Hello"
```

**Structured (Pydantic, recommended)**
```python
from pydantic import BaseModel

class MyState(BaseModel):
    counter: int = 0
    message: str = ""

class MyFlow(Flow[MyState]):
    @start()
    def first(self):
        self.state.message = "Hello"
        self.state.counter += 1
```

### Flow Persistence (`@persist`)

```python
from crewai.flow.persistence import persist

@persist  # class-level: all methods persisted
class MyFlow(Flow[MyState]):
    @start()
    def step(self):
        self.state.counter += 1
```

**Forking persisted state:**
```python
# Resume (same ID, extends history)
flow.kickoff(inputs={"id": existing_uuid})

# Fork (new ID, copies state, preserves original history)
flow.kickoff(restore_from_state_id=existing_uuid)
```

### Router Example

```python
from crewai.flow.flow import Flow, listen, router, start

class RouterFlow(Flow):
    @start()
    def initialize(self):
        self.state.success_flag = True

    @router(initialize)
    def route(self):
        return "success" if self.state.success_flag else "failed"

    @listen("success")
    def on_success(self):
        print("Taking success path")

    @listen("failed")
    def on_failure(self):
        print("Taking failure path")
```

### Human-in-the-Loop in Flows

```python
from crewai.flow.human_feedback import human_feedback, HumanFeedbackResult

class ReviewFlow(Flow):
    @start()
    @human_feedback(
        message="Do you approve this content?",
        emit=["approved", "rejected", "needs_revision"],
        llm="gpt-4o-mini",
        default_outcome="needs_revision",
    )
    def generate_content(self):
        return "Content to review..."

    @listen("approved")
    def on_approval(self, result: HumanFeedbackResult):
        print(f"Approved! Feedback: {result.feedback}")
```

### Memory in Flows

```python
class ResearchFlow(Flow):
    @start()
    def gather_data(self):
        findings = "PostgreSQL handles 10k concurrent connections..."
        memories = self.extract_memories(findings)
        for mem in memories:
            self.remember(mem, scope="/research/databases")

    @listen(gather_data)
    def analyze(self, raw_findings):
        past = self.recall("database performance", limit=10, depth="shallow")
        context = "\n".join([f"- {m.record.content}" for m in past])
        return {"context": context}
```

### Flow Usage Metrics

```python
flow.kickoff()
print(flow.usage_metrics)
# UsageMetrics(total_tokens=8579, prompt_tokens=6210, completion_tokens=2369, ...)
```

Note: `flow.usage_metrics` covers ALL LLM calls across the entire flow (all crews, bare LLM calls, etc.), unlike `flow.kickoff().token_usage` which only reflects the last crew.

### Flow Visualization

```python
flow.plot("my_flow_plot")  # generates my_flow_plot.html
```

```bash
crewai flow plot  # CLI option for project flows
```

### Running Flows

```bash
crewai run         # preferred (auto-detects flow vs crew from pyproject.toml)
crewai flow kickoff  # also works
```

---

## Tasks & Processes

### Processes

| Process | Description |
|---|---|
| `Process.sequential` | Tasks execute one after another (default) |
| `Process.hierarchical` | Manager agent delegates and validates tasks |

### Task Attributes (key ones)

- `description` — what the agent should do
- `expected_output` — what a successful result looks like
- `agent` — which agent handles this task
- `tools` — override agent's tools for this task
- `output_pydantic` — structured output schema
- `callback` — called when task completes
- `human_input` — pause for human review
- `condition` — conditional task execution
- `context` — list of tasks whose outputs feed into this task

---

## Tools

CrewAI provides **40+ built-in tools** across categories:

### AI/ML Tools
| Tool | Description |
|---|---|
| `AIMindTool` | Query data sources in natural language |
| `DallETool` | Generate images from text descriptions |
| `VisionTool` | Extract text from images (OCR via LLM) |
| `RagTool` | RAG-based knowledge base Q&A |
| `CodeInterpreterTool` | Execute Python in isolated environment |
| `LangChainTool` | Wrapper for LangChain tools |
| `LlamaIndexTool` | Wrapper for LlamaIndex query engines |

### Search & Research
| Tool | Description |
|---|---|
| `SerperDevTool` | Google search via Serper API |
| `TavilySearchTool` | Comprehensive web search via Tavily |
| `TavilyResearchTool` | Multi-step research with cited reports |
| `TavilyExtractorTool` | Extract structured content from URLs |
| `EXASearchTool` | Fast, accurate web search |
| `BraveSearchTool` | Web, news, image, video search |
| `ArxivPaperTool` | Search arXiv papers, download PDFs |
| `GithubSearchTool` | Search GitHub repositories |
| `WebsiteSearchTool` | RAG search within website content |
| `SerpApiGoogleSearchTool` | Google search via SerpApi |

### Web Scraping
| Tool | Description |
|---|---|
| `ScrapeWebsiteTool` | Extract content from a website |
| `FirecrawlScrapeWebsiteTool` | Scrape → clean markdown via Firecrawl |
| `FirecrawlCrawlWebsiteTool` | Crawl entire sites via Firecrawl |
| `SeleniumScrapingTool` | Browser-based scraping via Selenium |
| `BrowserbaseLoadTool` | Headless browser via Browserbase |
| `ScrapegraphScrapeTool` | AI-powered scraping via ScrapegraphAI |
| `SpiderTool` | Web content extraction via Spider |
| `BrightDataTools` | SERP search + Web Unlocker + Dataset API |

### File & Document
| Tool | Description |
|---|---|
| `FileReadTool` | Read files from local filesystem |
| `FileWriterTool` | Write content to files |
| `DirectoryReadTool` | List directory contents |
| `DirectorySearchTool` | RAG search within a directory |
| `PDFSearchTool` | RAG search within PDF files |
| `PDFTextWritingTool` | Write text to PDFs with custom fonts |
| `CSVSearchTool` | Semantic search within CSV files |
| `DOCXSearchTool` | RAG search within DOCX files |
| `JSONSearchTool` | Search JSON files |
| `XMLSearchTool` | RAG search within XML files |
| `TXTSearchTool` | RAG search within text files |
| `OCRTool` | OCR on local images or image URLs |

### Database & Data
| Tool | Description |
|---|---|
| `PGSearchTool` | PostgreSQL RAG search |
| `MySQLSearchTool` | MySQL RAG search |
| `NL2SQLTool` | Natural language to SQL |
| `SnowflakeSearchTool` | SQL + semantic search on Snowflake |
| `MongoDBVectorSearchTool` | Vector search on MongoDB Atlas |
| `QdrantVectorSearchTool` | Semantic search on Qdrant |
| `WeaviateVectorSearchTool` | Hybrid search on Weaviate |
| `SingleStoreSearchTool` | Safe SELECT/SHOW queries on SingleStore |

### Cloud Storage
| Tool | Description |
|---|---|
| `S3ReaderTool` | Read files from Amazon S3 |
| `S3WriterTool` | Write content to Amazon S3 |
| `BedrockKBRetriever` | Retrieve from Amazon Bedrock Knowledge Bases |

### Automation & Integration
| Tool | Description |
|---|---|
| `ComposioTool` | 250+ production-ready tools via Composio |
| `ApifyActorsTool` | Web scraping/crawling via Apify Actors |
| `ZapierActionsAdapter` | Zapier actions as CrewAI tools |
| `MultiOnTool` | Web navigation via natural language (MultiOn) |
| `MergeAgentHandlerTool` | Access Linear, GitHub, Slack via Merge |
| `BedrockInvokeAgentTool` | Invoke Amazon Bedrock Agents |
| `CrewAIRunAutomationTool` | Call other CrewAI Platform automations |

### Custom Tools

```python
from crewai.tools import BaseTool
from pydantic import BaseModel, Field
from typing import Type

class MyToolInput(BaseModel):
    argument: str = Field(..., description="Description of argument")

class MyCustomTool(BaseTool):
    name: str = "My Custom Tool"
    description: str = "Tool description for the agent"
    args_schema: Type[BaseModel] = MyToolInput

    def _run(self, argument: str) -> str:
        # Tool implementation
        return f"Result for {argument}"
```

---

## MCP Integration

CrewAI supports **Model Context Protocol (MCP)** servers natively.

### Transport Options
- **Stdio** — local MCP servers via stdin/stdout
- **SSE** — remote servers via Server-Sent Events
- **Streamable HTTP** — flexible remote transport

### DSL Syntax (simplest)

```python
from crewai import Agent

agent = Agent(
    role="Research Assistant",
    goal="Find information",
    backstory="...",
    mcps=["filesystem", "http://my-mcp-server.com/sse"]
)
```

### MCPServerAdapter (multiple servers)

```python
from crewai_tools import MCPServerAdapter

with MCPServerAdapter(["server1", "server2"]) as tools:
    agent = Agent(role="...", tools=tools)
```

### MCP Security Considerations
- Validate MCP server sources before connecting
- Use API key or OAuth 2.0 authentication for custom servers
- Prefer HTTPS/WSS transports for remote servers

---

## Memory System

CrewAI has a **unified memory system** with multiple memory types:

| Memory Type | Description |
|---|---|
| Short-term | Recent interaction context |
| Long-term | Persistent across sessions (LanceDB) |
| Entity memory | Tracks entities (people, places, concepts) |

### Enabling Memory in Crews

```python
crew = Crew(
    agents=[...],
    tasks=[...],
    memory=True,
    embedder={"provider": "openai"}  # or ollama, etc.
)
```

### Memory in Flows (built-in convenience methods)

```python
self.remember(content, scope="/research/databases")  # store
memories = self.recall("database performance", limit=10, depth="shallow")  # retrieve
facts = self.extract_memories(raw_text)  # parse text into discrete memories
```

---

## Knowledge Sources

Agents and crews can have access to domain-specific knowledge:

```python
from crewai.knowledge.source.pdf_knowledge_source import PDFKnowledgeSource
from crewai.knowledge.source.text_knowledge_source import TextKnowledgeSource

pdf_source = PDFKnowledgeSource(file_paths=["company_policy.pdf"])
text_source = TextKnowledgeSource(content="Domain-specific text content...")

agent = Agent(
    role="Policy Expert",
    goal="Answer policy questions",
    backstory="...",
    knowledge_sources=[pdf_source, text_source]
)
```

---

## Observability Integrations

CrewAI supports 15+ observability platforms:

| Platform | Type |
|---|---|
| CrewAI AMP Traces | Built-in (OpenTelemetry) |
| Arize Phoenix | OpenTelemetry + OpenInference |
| Braintrust | OpenTelemetry tracing + evaluation |
| Datadog | LLM Observability traces |
| Galileo | Tracing and evaluation |
| LangDB | AI Gateway with 350+ models |
| Langfuse | OpenTelemetry via OpenLit |
| Langtrace | Cost, latency, performance |
| Maxim | Agent monitoring + evaluation |
| MLflow | One-line monitoring |
| Neatlogs | Debug and share agent runs |
| OpenLIT | One-line OpenTelemetry |
| Opik (Comet) | Tracing, evaluation, dashboards |
| Patronus AI | LLM output evaluation |
| Portkey | LLM gateway + observability |
| TrueFoundry | Agent monitoring |
| Weave (W&B) | Tracking, evaluation, experiments |

### OpenTelemetry Export (AMP)

```bash
# Export traces to your own OTEL collector
# Configure via environment variables in AMP deployment
```

---

## Enterprise (CrewAI AMP)

CrewAI AMP is the **enterprise deployment and management platform**.

### Key Enterprise Features

| Feature | Description |
|---|---|
| **Crew Studio** | Visual no-code agent builder with real-time testing |
| **Automations** | Manage, deploy, and monitor live crews |
| **Triggers** | Gmail, Slack, Salesforce, HubSpot, Google Calendar, Teams, OneDrive, Outlook, Zapier, Webhook |
| **RBAC** | Role-Based Access Control for teams |
| **SSO** | SAML/OIDC enterprise authentication |
| **A2A (Agent-to-Agent)** | Production-grade distributed agent communication |
| **HITL Management** | Human-in-the-loop with email notifications and routing rules |
| **Hallucination Guardrail** | Prevent/detect AI hallucinations in tasks |
| **PII Redaction** | Auto-redact sensitive data from traces |
| **Secrets Manager** | AWS, Azure, GCP secrets integration |
| **Marketplace** | Reusable agent assets across teams |
| **Agent Repositories** | Share and reuse agents across projects |
| **Traces** | Full execution monitoring |
| **Webhook Streaming** | Stream events to your webhook |

### Supported Integrations (Enterprise)

Asana, Box, ClickUp, Databricks, GitHub, Gmail, Google Calendar, Google Contacts, Google Docs, Google Drive, Google Sheets, Google Slides, HubSpot, Jira, Linear, Microsoft Excel, Microsoft OneDrive, Microsoft Outlook, Microsoft SharePoint, Microsoft Teams, Microsoft Word, Notion, Salesforce, Shopify, Slack, Snowflake, Stripe, Zendesk

### Secrets Manager Backends
- AWS Secrets Manager (static keys or AssumeRole/OIDC)
- Azure Key Vault (static or Workload Identity Federation)
- Google Cloud Secret Manager (static or Workload Identity Federation)

### Deploy to AMP

```bash
crewai create crew my_crew     # scaffold project
# ... develop locally ...
crewai deploy                  # deploy to AMP
```

### REST API (CrewAI AMP)

| Endpoint | Method | Description |
|---|---|---|
| `/inputs` | GET | Get required inputs for a crew |
| `/kickoff` | POST | Start a crew execution |
| `/status/{kickoff_id}` | GET | Get execution status |
| `/resume` | POST | Resume with human feedback |

---

## Full Documentation Index

### Getting Started
- Introduction — https://docs.crewai.com/en/introduction.md
- Installation — https://docs.crewai.com/en/installation.md
- Quickstart — https://docs.crewai.com/en/quickstart.md
- Changelog — https://docs.crewai.com/en/changelog.md
- Telemetry — https://docs.crewai.com/en/telemetry.md

### Core Concepts
- Agents — https://docs.crewai.com/en/concepts/agents.md
- Crews — https://docs.crewai.com/en/concepts/crews.md
- Tasks — https://docs.crewai.com/en/concepts/tasks.md
- Flows — https://docs.crewai.com/en/concepts/flows.md
- Processes — https://docs.crewai.com/en/concepts/processes.md
- Tools — https://docs.crewai.com/en/concepts/tools.md
- Memory — https://docs.crewai.com/en/concepts/memory.md
- Knowledge — https://docs.crewai.com/en/concepts/knowledge.md
- LLMs — https://docs.crewai.com/en/concepts/llms.md
- Planning — https://docs.crewai.com/en/concepts/planning.md
- Reasoning — https://docs.crewai.com/en/concepts/reasoning.md
- Collaboration — https://docs.crewai.com/en/concepts/collaboration.md
- Checkpointing — https://docs.crewai.com/en/concepts/checkpointing.md
- Agent Capabilities — https://docs.crewai.com/en/concepts/agent-capabilities.md
- Skills — https://docs.crewai.com/en/concepts/skills.md
- Files (multimodal) — https://docs.crewai.com/en/concepts/files.md
- CLI — https://docs.crewai.com/en/concepts/cli.md
- Testing — https://docs.crewai.com/en/concepts/testing.md
- Training — https://docs.crewai.com/en/concepts/training.md
- Event Listeners — https://docs.crewai.com/en/concepts/event-listener.md
- Production Architecture — https://docs.crewai.com/en/concepts/production-architecture.md

### Guides
- Build Your First Crew — https://docs.crewai.com/en/guides/crews/first-crew.md
- Build Your First Flow — https://docs.crewai.com/en/guides/flows/first-flow.md
- Mastering Flow State — https://docs.crewai.com/en/guides/flows/mastering-flow-state.md
- Conversational Flows — https://docs.crewai.com/en/guides/flows/conversational-flows.md
- Crafting Effective Agents — https://docs.crewai.com/en/guides/agents/crafting-effective-agents.md
- Evaluating Use Cases — https://docs.crewai.com/en/guides/concepts/evaluating-use-cases.md
- Migrating from LangGraph — https://docs.crewai.com/en/guides/migration/migrating-from-langgraph.md
- Publish Custom Tools — https://docs.crewai.com/en/guides/tools/publish-custom-tools.md
- Customizing Prompts — https://docs.crewai.com/en/guides/advanced/customizing-prompts.md
- Fingerprinting — https://docs.crewai.com/en/guides/advanced/fingerprinting.md

### Learn (How-tos)
- Coding Agents — https://docs.crewai.com/en/learn/coding-agents.md
- Conditional Tasks — https://docs.crewai.com/en/learn/conditional-tasks.md
- Create Custom Tools — https://docs.crewai.com/en/learn/create-custom-tools.md
- Custom LLM Implementation — https://docs.crewai.com/en/learn/custom-llm.md
- Custom Manager Agent — https://docs.crewai.com/en/learn/custom-manager-agent.md
- Customize Agents — https://docs.crewai.com/en/learn/customizing-agents.md
- DALL-E Image Generation — https://docs.crewai.com/en/learn/dalle-image-generation.md
- Execution Hooks — https://docs.crewai.com/en/learn/execution-hooks.md
- Force Tool Output as Result — https://docs.crewai.com/en/learn/force-tool-output-as-result.md
- Hierarchical Process — https://docs.crewai.com/en/learn/hierarchical-process.md
- Human Feedback in Flows — https://docs.crewai.com/en/learn/human-feedback-in-flows.md
- Human-in-the-Loop Workflows — https://docs.crewai.com/en/learn/human-in-the-loop.md
- Human Input on Execution — https://docs.crewai.com/en/learn/human-input-on-execution.md
- Kickoff Async — https://docs.crewai.com/en/learn/kickoff-async.md
- Kickoff For Each — https://docs.crewai.com/en/learn/kickoff-for-each.md
- LLM Connections — https://docs.crewai.com/en/learn/llm-connections.md
- LLM Call Hooks — https://docs.crewai.com/en/learn/llm-hooks.md
- Strategic LLM Selection — https://docs.crewai.com/en/learn/llm-selection-guide.md
- Multimodal Agents — https://docs.crewai.com/en/learn/multimodal-agents.md
- Replay Tasks — https://docs.crewai.com/en/learn/replay-tasks-from-latest-crew-kickoff.md
- Sequential Processes — https://docs.crewai.com/en/learn/sequential-process.md
- Tool Call Hooks — https://docs.crewai.com/en/learn/tool-hooks.md
- Using Annotations — https://docs.crewai.com/en/learn/using-annotations.md
- Using CrewAI Without LiteLLM — https://docs.crewai.com/en/learn/litellm-removal-guide.md

### MCP
- Overview — https://docs.crewai.com/en/mcp/overview.md
- DSL Integration — https://docs.crewai.com/en/mcp/dsl-integration.md
- Multiple Servers — https://docs.crewai.com/en/mcp/multiple-servers.md
- SSE Transport — https://docs.crewai.com/en/mcp/sse.md
- Stdio Transport — https://docs.crewai.com/en/mcp/stdio.md
- Streamable HTTP — https://docs.crewai.com/en/mcp/streamable-http.md
- Security — https://docs.crewai.com/en/mcp/security.md

### Observability
- Overview — https://docs.crewai.com/en/observability/overview.md
- CrewAI Tracing — https://docs.crewai.com/en/observability/tracing.md
- Arize Phoenix — https://docs.crewai.com/en/observability/arize-phoenix.md
- Braintrust — https://docs.crewai.com/en/observability/braintrust.md
- Datadog — https://docs.crewai.com/en/observability/datadog.md
- Galileo — https://docs.crewai.com/en/observability/galileo.md
- LangDB — https://docs.crewai.com/en/observability/langdb.md
- Langfuse — https://docs.crewai.com/en/observability/langfuse.md
- Langtrace — https://docs.crewai.com/en/observability/langtrace.md
- MLflow — https://docs.crewai.com/en/observability/mlflow.md
- OpenLIT — https://docs.crewai.com/en/observability/openlit.md
- Opik (Comet) — https://docs.crewai.com/en/observability/opik.md
- Patronus AI — https://docs.crewai.com/en/observability/patronus-evaluation.md
- Portkey — https://docs.crewai.com/en/observability/portkey.md
- Weave (W&B) — https://docs.crewai.com/en/observability/weave.md

### Enterprise
- AMP Introduction — https://docs.crewai.com/en/enterprise/introduction.md
- Automations — https://docs.crewai.com/en/enterprise/features/automations.md
- Crew Studio — https://docs.crewai.com/en/enterprise/features/crew-studio.md
- RBAC — https://docs.crewai.com/en/enterprise/features/rbac.md
- SSO — https://docs.crewai.com/en/enterprise/features/sso.md
- Traces — https://docs.crewai.com/en/enterprise/features/traces.md
- Hallucination Guardrail — https://docs.crewai.com/en/enterprise/features/hallucination-guardrail.md
- PII Redaction — https://docs.crewai.com/en/enterprise/features/pii-trace-redactions.md
- A2A — https://docs.crewai.com/en/enterprise/features/a2a.md
- Marketplace — https://docs.crewai.com/en/enterprise/features/marketplace.md
- Deploy to AMP — https://docs.crewai.com/en/enterprise/guides/deploy-to-amp.md
- Triggers Overview — https://docs.crewai.com/en/enterprise/guides/automation-triggers.md
- Team Management — https://docs.crewai.com/en/enterprise/guides/team-management.md
- HITL Workflows — https://docs.crewai.com/en/enterprise/guides/human-in-the-loop.md
- Webhook Automation — https://docs.crewai.com/en/enterprise/guides/webhook-automation.md
- Custom MCP Servers — https://docs.crewai.com/en/enterprise/guides/custom-mcp-server.md
- OpenTelemetry Export — https://docs.crewai.com/en/enterprise/guides/capture_telemetry_logs.md
- FAQs — https://docs.crewai.com/en/enterprise/resources/frequently-asked-questions.md

### Tools (all categories)
- Tools Overview — https://docs.crewai.com/en/tools/overview.md
- AI/ML Tools — https://docs.crewai.com/en/tools/ai-ml/overview.md
- Search/Research Tools — https://docs.crewai.com/en/tools/search-research/overview.md
- Web Scraping Tools — https://docs.crewai.com/en/tools/web-scraping/overview.md
- File/Document Tools — https://docs.crewai.com/en/tools/file-document/overview.md
- Database/Data Tools — https://docs.crewai.com/en/tools/database-data/overview.md
- Cloud Storage Tools — https://docs.crewai.com/en/tools/cloud-storage/overview.md
- Automation Tools — https://docs.crewai.com/en/tools/automation/overview.md
- Integration Tools — https://docs.crewai.com/en/tools/integration/overview.md

### Examples
- Examples — https://docs.crewai.com/en/examples/example.md
- Cookbooks — https://docs.crewai.com/en/examples/cookbooks.md

### API Reference
- Introduction — https://docs.crewai.com/en/api-reference/introduction.md
- POST /kickoff — https://docs.crewai.com/en/api-reference/kickoff.md
- GET /status/{kickoff_id} — https://docs.crewai.com/en/api-reference/status.md
- GET /inputs — https://docs.crewai.com/en/api-reference/inputs.md
- POST /resume — https://docs.crewai.com/en/api-reference/resume.md

---

## Community & Resources

- Website: https://crewai.com
- GitHub: https://github.com/crewAIInc/crewAI
- Community Forum: https://community.crewai.com
- Blog: https://blog.crewai.com
- CrewGPT Assistant: https://chatgpt.com/g/g-qqTuUWsBY-crewai-assistant
- Skills Registry: https://skills.sh
