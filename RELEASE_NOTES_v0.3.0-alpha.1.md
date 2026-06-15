# Technemachina v0.3.0-alpha.1

This prerelease marks the first public ownership-boundary architecture for Synapse.

## Included

- Explicit `owner_scope` classification for Synapse nodes
- Source provenance preserved across record loading
- Unified provenance-aware knowledge loading
- Strict server-side Synapse scope projections
- Read-only API views through `/synapse/map?view=...`
- Dedicated `developer_history` projection for the main constellation
- Bounded `companion` projection that excludes developer-history nodes
- Edge pruning with no dangling projected relationships
- HTTP 400 rejection for unknown scope views
- Permanent standard-library regression coverage
- Public README documentation for ownership views

## Verified views

- `personal`
- `personal_governance`
- `imported_knowledge`
- `imported_governance`
- `developer_history`
- `system`
- `system_doctrine`
- `companion`
- `all`

## Validation

- 10 Synapse ownership regression tests passing
- Working tree clean before release
- Local `main` synchronized with `origin/main`
- Secret-pattern scan clean
- No tracked files larger than 5 MB

## Status

Alpha research software. Interfaces and data models may still change.
