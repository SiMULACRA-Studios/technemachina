# v0.2.9c — Synapse Map Frontend / Constellation Renderer

## Status

Planned frontend renderer.

This milestone visualizes the read-only Synapse Map backend as a constellation-style graph. It must not mutate memory, knowledge, candidates, reviews, decisions, threads, or H.I.V.E.

## Renderer Doctrine

The Synapse Map renderer is a layered visualization system, not a single flat graph component.

The renderer has three layers:

1. Star Layer
2. Thread Layer
3. Read Layer

## Layer 1 — Star Layer

Purpose:

Render nodes as mini-stars.

Responsibilities:

- draw node cores,
- draw soft glow halos,
- encode node type with visual class,
- encode importance with salience / brightness,
- support selected and dimmed states.

Node classes:

- memory_record
- memory_layer
- knowledge_record
- knowledge_source
- thread_candidate
- knowledge_candidate
- review_item
- review_decision
- thread
- project_context
- doctrine

Rules:

- no large glowing blobs,
- no excessive pulse animation,
- no always-on labels at far zoom,
- brightness and size should carry meaning before color.

## Layer 2 — Thread Layer

Purpose:

Render relationships as luminous constellation links.

Responsibilities:

- draw edges between nodes,
- encode relation type,
- brighten selected paths,
- dim unrelated links,
- support hover emphasis.

Relation classes:

- belongs_to_layer
- references_source
- candidate_from
- queued_as
- linked_to_thread
- governed_by
- reviewed_by
- approved_into
- rejected_as
- deferred_as

Rules:

- links must be thin,
- links must remain subtle at default zoom,
- selected links may brighten,
- dense relation fields must not become visual noise.

## Layer 3 — Read Layer

Purpose:

Render labels, metadata, tooltips, filters, and inspector.

Responsibilities:

- selected node inspector,
- selected edge inspector,
- filter controls,
- zoom-aware labels,
- node count / edge count summary,
- read-only doctrine badge.

Rules:

- labels appear progressively,
- inspector updates on selection,
- no write buttons,
- no approval buttons,
- no graph editing controls.

## Zoom States

### Far Zoom

Constellation field.

- node labels hidden,
- only star points and faint edges visible,
- clusters read as a glowing field,
- doctrine / project context may appear slightly brighter.

### Mid Zoom

Relationship discovery.

- important labels appear,
- selected paths brighten,
- clusters become readable,
- hover tooltips become available.

### Near Zoom

Technical inspection.

- labels visible,
- node metadata available,
- edge relation types visible,
- inspector becomes primary reading surface.

## Node States

### Default

- mini-star core,
- soft halo,
- semantic node class,
- moderate opacity.

### Hovered

- brighter halo,
- tooltip appears,
- immediate edges brighten slightly.

### Selected

- brightest halo,
- connected path highlighted,
- inspector opens,
- unrelated nodes dim.

### Dimmed

- reduced opacity,
- low halo,
- used outside active filter or selected path.

## Edge States

### Default

- thin luminous line,
- low opacity,
- relation class stored in data attribute.

### Hovered

- brighter line,
- relation tooltip appears.

### Selected

- bright line,
- source and target nodes brighten,
- inspector shows relation details.

### Dimmed

- low opacity,
- background context only.

## Visual Tokens

Suggested semantic classes:

- memory_record: silver-white
- memory_layer: soft white ring
- knowledge_record: pale blue
- knowledge_source: blue-white
- thread_candidate: violet
- knowledge_candidate: cyan-violet
- review_item: amber
- review_decision approved: gold-white
- review_decision deferred: muted amber-gray
- review_decision rejected: muted red
- thread: dim blue-gray
- project_context: pale gold-white
- doctrine: bright white with faint violet halo

Exact color values may be implemented in CSS later.

## Data Contract

The renderer consumes:

- GET /synapse/status
- GET /synapse/map

Expected map payload:

- nodes
- edges
- meta
- styleHints
- doctrine

The renderer must respect:

- meta.read_only
- styleHints.mutationAllowed
- styleHints.defaultRenderer
- node.skin.renderer
- edge.skin.renderer

## UI Placement

The renderer should become its own mode beside:

- Chat
- Control Center
- Brain Mode

Proposed mode label:

Synapse Map

## Non-Goals

v0.2.9c must not:

- edit graph nodes,
- create memory,
- create knowledge,
- enqueue candidates,
- approve reviews,
- reject reviews,
- defer reviews,
- activate H.I.V.E.,
- sync externally,
- or expose public discovery.

## One-Line Definition

The Constellation Renderer turns the Synapse Map into a living star field: mini-star nodes, luminous relationship lines, zoom-aware labels, and read-only inspection.


## v0.2.9c-1 Addendum — Object-Backed Stars + Milestone Layer

### Core Rule

Synapse Map stars must represent real daemon objects and real milestone history.

The Constellation Skin is only the visual language. The underlying nodes are authoritative data objects, approved memory, indexed knowledge, governance records, thread records, project context, doctrine, and release milestones.

### No Decorative Stars

The renderer must not create fake stars for visual density.

Allowed stars:

- memory records,
- memory layers,
- knowledge records,
- knowledge sources,
- thread candidates,
- knowledge candidates,
- review items,
- review decisions,
- threads,
- project context,
- doctrine,
- release milestones.

### Milestone Stars

Milestone nodes are created from `project_context.locked_milestones`.

Milestone stars represent the actual evolution of the daemon.

Examples:

- Brain Online
- Audit Log Online
- Multi-Brain Router Online
- Memory Review Queue Online
- Knowledge Ingest Foundation Online
- Synapse Map Read-Only Backend Online
- Synapse Map Constellation Renderer Spec Documented

### Semantic Zoom Doctrine

Far zoom:

- release history and major architecture constellations.

Mid zoom:

- Memory, Knowledge, Governance, Threads, Synapse, Provider clusters.

Near zoom:

- concrete records, candidates, reviews, decisions, sources, and metadata.

### One-Line Rule

The Synapse Map is a living sky of real daemon history: no decorative stars, only object-backed and milestone-backed nodes.


## v0.2.9d Addendum — Galaxy Layout Engine

The Synapse Map must read as a daemon galaxy, not a compressed wheel.

### Doctrine

- Black space is part of the interface.
- No decorative stars.
- Every star must represent a real daemon object or milestone.
- Clusters should be separated into semantic galaxies.
- Cross-galaxy edges should be sparse at far zoom.
- Motion should imply depth without overwhelming readability.

### Galaxy Anchors

- Center: project context, doctrine, daemon identity.
- Upper left: knowledge records and knowledge sources.
- Upper right: memory records and memory layers.
- Lower left: candidates.
- Lower right: reviews and decisions.
- Outer belt: threads.
- Deep field: milestones and milestone clusters.

### Guide Stars

Guide stars are major navigation landmarks and remain visible earlier than ordinary labels.

Guide stars include:

- project context,
- doctrine,
- Brain milestones,
- Memory milestones,
- Knowledge milestones,
- Synapse milestones,
- H.I.V.E. documented milestones.

### Semantic Zoom

Far zoom:
- show clusters, guide stars, and sparse links.

Mid zoom:
- show major labels, high-salience nodes, and selected paths.

Near zoom:
- show object labels, fuller relation density, and inspector-ready detail.
