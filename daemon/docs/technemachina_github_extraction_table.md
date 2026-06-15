# Technemachina GitHub Extraction Table

## Purpose

This document ranks open-source references by what Technemachina should borrow conceptually.

The rule remains: borrow patterns, not uncontrolled code.

---

## Ranked extraction table

| Rank | Repo / project | What to extract | Technemachina fit | Difficulty | Risk |
|---|---|---|---|---|---|
| 1 | LocalAI | Local model gateway, OpenAI-compatible API layer, modular backend loading, local-first runtime patterns. | Core runtime / body layer. | Medium | Low |
| 2 | Letta Context Repositories | Git-based context, versioned memory files, inspectable memory state, context management. | Long-term memory / project memory. | Medium | Medium |
| 3 | Letta Memory Blocks | Memory segmentation into functional units, structured context management. | Memory architecture / thread state. | Medium | Low |
| 4 | agentmemory | Session capture, memory compression, reinjection of relevant context across sessions. | Memory persistence for coding and threads. | Medium | Medium |
| 5 | RepoAudit | Repo-wide analysis, hybrid static + LLM audit flow, structured security/report output. | Repo analysis / future code audit mode. | High | Medium |
| 6 | Awesome Agent Memory lists | Paper map, taxonomy, benchmark discovery, memory-system references. | Research discovery / memory roadmap. | Low | Low |
| 7 | Awesome-Memory-for-Agents | Curated memory mechanisms, taxonomy, benchmark and implementation leads. | Research discovery / memory roadmap. | Low | Low |
| 8 | LocalAI docs / ecosystem patterns | Deployment structure, runtime composition, API compatibility strategy. | Implementation reference for local stack. | Medium | Low |
| 9 | Open source agent frameworks | State graphs, tool routing, planning loops, memory hooks. | Planner / router / orchestration. | Medium | Medium |
| 10 | OpenBrain-style personal memory systems | MCP-connected persistent memory, externalized context store. | Personal/project memory layer. | Medium | Medium |

---

## Best borrowing strategy

The safest and most useful extraction path:

1. Use LocalAI for runtime structure.
2. Use Letta for memory organization.
3. Use agentmemory for capture, compression, and reinjection.
4. Use RepoAudit later for repository inspection and safety checks.

---

## Priority order

1. Memory blocks and context repositories.
2. Local runtime compatibility layer.
3. Session capture and reinjection.
4. Repo analysis and audit mode.
5. Research taxonomies after the core architecture is stable.

---

## Suggested implementation order

1. Define memory schemas.
2. Implement capture and retrieval.
3. Add a local model adapter.
4. Wire planner/router memory hooks.
5. Add repo-analysis capabilities.
6. Expand into code synthesis and safe modification.

---

## Memory-specific implications

The next memory module should not be a vague database dump.

It should define typed memory records first:

- thread memory
- project fact
- decision
- procedure
- research note
- external reference
- risk note
- doctrine note

Then retrieval should explain why a memory was selected.

This directly supports:

- v0.2.7 Continuum Memory Taxonomy
- v0.2.7a Typed Memory + Explainable Retrieval
- v0.2.7b Memory Consolidation Worker

---

## Doctrine

Memory comes first.

The brain architecture comes second.

Bigger agent features come after memory, retrieval, safety, and auditability are stable.
