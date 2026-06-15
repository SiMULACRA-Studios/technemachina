# v0.2.9 — Obsidian / Synapse Map Foundation

## Status

Planned foundation module.

The Synapse Map is a read-only relationship layer for Technemachina Daemon. It does not activate H.I.V.E., collaboration, syncing, sharing, or public discovery.

## Default Renderer Skin

Default renderer skin: Constellation Skin.

See:

- docs/synapse_constellation_skin_v0.2.9.md

## Role Split

Control Center is the operational governance console.

Synapse Map is the conceptual relationship surface.

H.I.V.E. remains a future collaboration layer and is not operational.

## Core Doctrine

Knowledge is ingested, indexed, and searched.

Memory is extracted, reviewed, and approved.

Candidates are proposals.

Reviews are gates.

Decisions are governance events.

The Synapse Map visualizes relationships between these objects without mutating them.

## Entity Types

- memory_record
- knowledge_record
- knowledge_source
- thread_candidate
- knowledge_candidate
- review_item
- review_decision
- thread
- doctrine
- project_context

## Relation Types

- source_of
- candidate_from
- queued_as
- reviewed_by
- approved_into
- rejected_as
- deferred_as
- linked_to_thread
- belongs_to_layer
- governed_by
- references_source
- derived_from
- supersedes

## Read-Only Endpoints

- GET /synapse/status
- GET /synapse/entities
- GET /synapse/relations
- GET /synapse/map

## First Implementation Goal

Assemble a local graph from existing ledgers:

- logs/memory/memory_records.jsonl
- logs/memory/review_queue.jsonl
- logs/memory/review_decisions.jsonl
- logs/memory/candidates.jsonl
- logs/knowledge/knowledge_records.jsonl
- logs/knowledge/knowledge_sources.json
- logs/knowledge/knowledge_candidates.jsonl
- logs/threads/thread_registry.json
- daemon/project_context.json

## Non-Goals

v0.2.9 must not:

- write memory,
- write knowledge,
- approve candidates,
- edit graph nodes,
- sync across devices,
- expose public discovery,
- activate H.I.V.E.,
- or create collaboration proposals.

## Future UI

The Synapse Map may later live as its own app mode beside:

- Chat
- Control Center
- Brain Mode

Potential future label:

Synapse Map

## One-Line Definition

The Synapse Map is the daemon’s read-only graph of how knowledge, memory, candidates, reviews, decisions, sources, and threads connect.
