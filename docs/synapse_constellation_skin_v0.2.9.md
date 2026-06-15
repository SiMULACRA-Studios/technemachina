# Synapse Map Constellation Skin
## Visual Mini-Spec for v0.2.9

## Status

Design doctrine for the Synapse Map renderer.

This is a visual skin specification only. It does not change memory, knowledge, candidates, reviews, decisions, or H.I.V.E. behavior.

## Core Doctrine

Synapse Map foundation and Synapse Map skin must remain separate.

The foundation defines:

- entities,
- relations,
- filters,
- graph assembly,
- inspectors,
- and read-only map data.

The skin defines:

- node appearance,
- link appearance,
- glow behavior,
- zoom behavior,
- color tokens,
- and selection emphasis.

## Skin Direction

Synapse Map skin direction: Constellation Renderer.

Nodes appear as mini stars.

Relations appear as luminous constellation links.

The zoomed-out view should read as a glowing star map.

The map should feel celestial, intelligent, quiet, and alive without becoming visual noise.

## Node States

### Default Node

- tiny star core,
- soft glow halo,
- low visual weight,
- readable only when zoomed near enough.

### Important Node

- slightly larger core,
- stronger halo,
- subtle pulse,
- higher brightness.

### Selected Node

- bright core,
- expanded halo,
- connected edges brighten,
- inspector opens or updates.

### Dimmed Node

- reduced opacity,
- minimal halo,
- used for filtered or unrelated nodes.

## Semantic Node Colors

- Memory records: white / silver stars.
- Knowledge records: pale blue stars.
- Knowledge sources: blue-white faint stars.
- Thread candidates: violet stars.
- Knowledge candidates: cyan-violet stars.
- Review items: amber stars.
- Approved decisions: gold-white stars.
- Deferred decisions: muted amber-gray stars.
- Rejected decisions: muted red-shifted stars.
- Doctrine nodes: bright white with faint violet halo.
- Project context nodes: pale gold-white.

## Link States

### Default Link

- thin translucent constellation line,
- low brightness,
- visible only enough to imply structure.

### Hovered Link

- slightly brighter,
- relation type becomes readable.

### Selected Link

- luminous line,
- connected nodes brighten,
- inspector shows relation details.

### Dimmed Link

- low opacity,
- used when unrelated to selected node or active filter.

## Zoom Behavior

### Zoomed Out

The map reads as a constellation field.

- labels hidden,
- small stars visible,
- major clusters glow softly,
- links faint.

### Mid Zoom

The map reveals structure.

- clusters become legible,
- selected paths brighten,
- important node labels appear.

### Zoomed In

The map becomes technical.

- labels readable,
- relation types visible,
- inspector details meaningful,
- node metadata accessible.

## Salience / Heat

Node heat should represent importance or signal strength.

Higher-salience nodes may glow more strongly based on:

- review approval,
- high confidence,
- high importance,
- doctrine relevance,
- repeated linkage,
- candidate score,
- or active project relevance.

Heat must remain subtle.

Avoid excessive pulsing, large blobs, or chaotic animation.

## Renderer Rules

- The skin must not mutate graph data.
- The skin must not create memory.
- The skin must not create candidates.
- The skin must not approve reviews.
- The skin must remain swappable.
- The map must still work if the skin changes later.

## Future Skins

Possible future skins:

- Constellation
- Neural
- Circuit
- Obsidian
- H.I.V.E.
- Infrared
- Ultraviolet
- Vireon

## One-Line Definition

The Constellation Skin makes the Synapse Map look like a living star field: mini-star nodes, luminous relation lines, semantic glow, and zoom-dependent clarity.
