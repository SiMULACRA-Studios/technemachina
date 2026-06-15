
---

# v0.2.6a — Code Readability UI

State: ONLINE  
Status: LOCKED AFTER VISUAL CONFIRMATION  

Confirmed:

- Chat messages now render as separated user/daemon blocks.
- Markdown code blocks render as readable code cards.
- Code cards include a Copy button.
- Python syntax highlighting works.
- Keywords, functions, strings, comments, and numbers are visually separated.
- The Daemon can now provide code in a usable assistant-style format.

Deferred:

- Run button.
- Sandbox-backed execution.
- More polished cockpit styling.
- Model dropdown accuracy.
- Dynamic version display.

Notes:

This milestone improves usability without touching provider routing, failover policy, safety policy, decision ledger, or backend execution. It is a frontend readability milestone.


---

# v0.2.6b — Thread Context Window

State: ONLINE  
Status: LOCKED AFTER LIVE TEST  

Confirmed:

- `thread_context.py` exists and compiles.
- `/chat` route uses the Thread Context Window.
- User messages are saved locally.
- Daemon responses are saved locally.
- Thread records are stored in `logs/threads/default.jsonl`.
- `/chat` returns `thread_id: default`.
- `/chat` returns `context: thread_context_window_active`.
- Follow-up questions can use recent thread context.
- Test marker `silver-orchid` was remembered correctly.
- Provider/API error messages are filtered out of injected thread memory.

Notes:

This milestone fixes the Daemon's immediate follow-up awareness problem. The Daemon now has a local current-thread memory layer. External providers remain replaceable brains; the Daemon owns the thread record locally.

Deferred:

- Sidebar thread list.
- Multiple named threads.
- Thread title generation.
- Thread search.
- Continuum Memory Taxonomy.
- Long-term semantic memory.
