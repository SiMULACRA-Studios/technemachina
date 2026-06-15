# Technemachina GitHub Research List

## Purpose

This document is the canonical open-source research list for Technemachina Daemon.

The rule is not to blindly copy code. The rule is to extract architecture patterns, safety patterns, UX patterns, and roadmap ideas that can be rebuilt locally under Oracle approval.

---

## 1. Local-first AI engines

Anchor references:

- mudler/localai
- coleam00/local-ai-packaged
- janhq/awesome-local-ai
- Open WebUI
- Ollama
- LM Studio
- RAGFlow
- Dify
- n8n
- Langflow

What to borrow:

- OpenAI-compatible local API patterns
- Modular provider loading
- Local-first privacy defaults
- Model lifecycle management
- Embeddings and retrieval support
- Tool/function calling patterns
- Simple onboarding UX

What not to copy:

- Heavy deployment complexity too early
- Provider lock-in
- Uncontrolled plugin execution
- Anything that weakens local-first governance

Technemachina phase:

- Local runtime adapter
- Provider abstraction layer
- Future desktop/local packaging

---

## 2. Memory-first assistants

Anchor references:

- letta-ai/letta-code
- Letta Context Repositories
- davegoldblatt/total-recall
- CaviraOSS/OpenMemory
- rohitg00/agentmemory
- agiresearch/A-mem
- WujiangXu/A-mem
- SuperLocalMemory

What to borrow:

- Memory blocks
- Tiered memory
- Git-backed context repositories
- Memory write gates
- Correction propagation
- Shared memory blocks across agents
- Compression and context injection
- Inspectable and revocable memory

What not to copy:

- Flat prompt stuffing
- Silent permanent memory writes
- Memory without provenance
- Memory without Oracle control

Technemachina phase:

- Continuum Memory Taxonomy
- Typed Memory
- Explainable Retrieval
- Memory Consolidation Worker
- Obsidian Synapse / project knowledge layer

---

## 3. Code audit and repository analysis

Anchor references:

- RepoAudit
- PR-Agent / code review assistants
- SonarQube Community Build
- Review Board
- Gerrit
- Gitea
- Forgejo
- GitLab CE
- OneDev
- SCM-Manager
- RhodeCode

What to borrow:

- Repository-wide code inspection
- Hybrid static + LLM analysis
- Diff review patterns
- Risk scoring
- Explainable reports
- Pull request style patch workflow
- Security summaries before code modification

What not to copy:

- Auto-editing without review
- Repo write access without sandboxing
- Security scans with vague findings
- Self-modification without rollback

Technemachina phase:

- Repo Audit Mode
- Code Synthesis Module
- Sandbox Foundation
- Oracle-approved self-modification

---

## 4. Agent frameworks and orchestration

Anchor references:

- LangGraph
- LangChain
- LlamaIndex
- Haystack
- Semantic Kernel
- Pydantic AI
- DSPy
- crewAI
- Mastra
- Google ADK
- Anthropic SDK patterns

What to borrow:

- Stateful graph routing
- Retrieval-backed workflows
- Typed agent schemas
- Tool planning patterns
- Observability
- Agent state machines
- Failure handling

What not to copy:

- Overcomplicated agent graphs too early
- Hidden tool execution
- Non-local memory assumptions
- Framework lock-in

Technemachina phase:

- Multi-brain router
- Decision Ledger
- Tool/skill loader
- Memory-aware orchestration
- Research brain integration

---

## 5. Public APIs and free-tier catalogs

Anchor references:

- public-apis/public-apis
- public-api-lists/public-api-lists
- free-for-dev
- awesome-developer-first
- freestuff.dev

What to borrow:

- API discovery structure
- Free-tier tracking
- Integration catalog organization
- Developer tooling categories

What not to copy:

- Stale API assumptions
- Unsafe scraping patterns
- Credential-heavy services without secret handling
- Integrations before governance

Technemachina phase:

- Public API layer
- Research integrations
- Grant/product utility modules

---

## 6. Foundational model literacy

Anchor references:

- LLM from scratch repositories
- ML from scratch repositories
- Build GPT-like model repositories

What to borrow:

- Conceptual grounding
- Tokenization understanding
- Training and inference vocabulary
- Model architecture literacy

What not to copy:

- Attempting full model training too early
- Expensive compute paths
- Distracting from the daemon roadmap

Technemachina phase:

- Long-term education
- Technical credibility
- Grant and research literacy

---

## 7. Anchor repo conclusions

### LocalAI

Best reference for local runtime, OpenAI-compatible APIs, modular backend loading, local-first privacy, embeddings, tool use, and future distributed routing ideas.

### Letta

Best reference for memory blocks, context repositories, programmatic context management, git-backed memory files, and shared memory across agents.

### RepoAudit

Best reference for repository-level inspection, static + LLM hybrid analysis, security summaries, and explainable code audit reports.

---

## 8. Ranked study order

1. Memory and context systems
2. Local-first AI engines
3. Orchestration frameworks
4. Code audit and repository analysis
5. Public APIs and free-tier catalogs
6. Foundational model literacy

---

## 9. Extraction template

For every repo studied, record:

- Repo
- Category
- Core pattern
- What to borrow
- What not to borrow
- Technemachina integration phase
- Complexity
- Security risk
- Notes

---

## 10. Current recommended feature candidates

- Memory blocks
- Git-backed context layer
- Local runtime adapter
- Repo audit mode
- Tool/skill loader
- Retriever-backed project knowledge
- Graph-based routing
- Safe code synthesis pipeline

---

## Doctrine

Technemachina studies other systems, but does not become them.

External repos are references. The Daemon remains local-first, inspectable, governed by the Oracle, and protected by audit logs, decision ledgers, sandboxing, and explicit approval gates.

---

## Companion extraction table

See also:

- `docs/technemachina_github_extraction_table.md`

This companion document ranks the highest-value open-source references by what Technemachina should borrow conceptually, where each pattern fits, and how risky or difficult it is to adapt.

