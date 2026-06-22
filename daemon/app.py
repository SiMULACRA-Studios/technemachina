import asyncio
import json
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel, Field
import uvicorn

import memory
import thread_context
import thread_registry
import thread_to_memory
import ai
from brain_status import get_brain_status
import tools
import monitor
from risk import RiskLevel, classify_text
import project_context
import memory_taxonomy
import memory_retrieval
import memory_consolidation_worker
import memory_review_queue
import knowledge_ingest
import synapse_map
import synapse_analysis

app = FastAPI(title="Technemachina Daemon", version="0.2.1")

# Technemachina local browser frontend policy.
# Origin matching is exact; do not add trailing slashes.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["127.0.0.1", "localhost"]
)


memory.init_db()

COMPANION_ASSOCIATION_CONTEXT_LIMIT = 8
COMPANION_SUGGESTIONS_LIMIT = 3
COMPANION_DESCRIPTION_MAX_CHARS = 2000


class CompanionRequest(BaseModel):
    user_message: str
    selected_node_id: str
    view: str = "companion"


class ChatRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=20000)
    model: str = "auto"
    thread_id: str = ""

class ToolRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=50000)
    model: str = "auto"

class NoteRequest(BaseModel):
    topic: str = Field(..., min_length=1, max_length=300)
    notes: str = Field(..., min_length=1, max_length=20000)

class RiskRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=50000)

class ThreadRenameRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=120)

class MemoryRecordRequest(BaseModel):
    record_type: str = Field(..., min_length=1, max_length=80)
    layer: str = Field(..., min_length=1, max_length=40)
    scope: str = Field(..., min_length=1, max_length=80)
    title: str = Field(..., min_length=1, max_length=200)
    summary: str = Field(..., min_length=1, max_length=1000)
    body: str = Field(..., min_length=1, max_length=20000)
    tags: list[str] = []
    source_type: str = "manual"
    source_ref: str = ""
    source_title: str = ""
    created_by: str = "Oracle"
    provenance: str = ""
    confidence: str = "medium"
    status: str = "active"
    review_state: str = "oracle_approved"
    expires_at: str | None = None
    risk_level: str = "low"
    supersedes: list[str] = []
    attach_to_context: bool = False
    retrieval_priority: int = 50
    recency_weight: float = 0.5
    importance_weight: float = 0.5

class MemoryRevokeRequest(BaseModel):
    reason: str = ""

class MemorySearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    record_type: str | None = None
    layer: str | None = None
    scope: str | None = None
    include_revoked: bool = False
    limit: int = 10
    min_score: float = 0.01

class MemoryConsolidationRequest(BaseModel):
    dry_run: bool = True
    limit: int = 50


class KnowledgeIngestTextRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=300)
    body: str = Field(..., min_length=1, max_length=100000)
    source_type: str = "text"
    source_path: str = ""
    origin: str = "manual"
    tags: list[str] = []
    created_by: str = "Oracle"
    provenance: str = ""


class KnowledgeCandidateCreateRequest(BaseModel):
    knowledge_record_id: str = Field(..., min_length=1, max_length=200)
    reason: str = ""
    created_by: str = "Oracle"
    force: bool = False

class KnowledgeCandidateEnqueueRequest(BaseModel):
    reviewed_by: str = "Oracle"
    notes: str = ""

class MemoryReviewCreateRequest(BaseModel):
    candidate_record: dict
    suggested_action: str = "approve"
    reason: str = ""
    source_refs: list[str] = []
    conflicting_record_ids: list[str] = []
    related_record_ids: list[str] = []
    original_record: dict = {}
    created_by: str = "Oracle"

class MemoryReviewDecisionRequest(BaseModel):
    reviewed_by: str = "Oracle"
    notes: str = ""

class MemoryReviewEditRequest(BaseModel):
    patch: dict
    reviewed_by: str = "Oracle"
    notes: str = ""

@app.get("/")
async def root():
    context = project_context.load_context()
    return {
        "status": "online",
        "system": context.get("project", "Technemachina Daemon"),
        "version": context.get("current_version", "unknown"),
        "project_status": context.get("status", "unknown"),
        "active_provider": context.get("active_provider", "unknown"),
    }







# --- Technemachina Knowledge Ingest Foundation v0.2.8 ---


# --- Technemachina Synapse Map Read-Only Backend v0.2.9 ---

@app.get("/synapse/status")
async def synapse_status():
    return synapse_map.synapse_status()


@app.get("/synapse/entities")
async def synapse_entities(entity_type: str = ""):
    return synapse_map.get_entities(entity_type=entity_type)


@app.get("/synapse/relations")
async def synapse_relations(relation_type: str = ""):
    return synapse_map.get_relations(relation_type=relation_type)




@app.get("/synapse/analysis")
async def synapse_analysis_payload():
    return synapse_analysis.get_analysis()

@app.get("/synapse/map")
async def synapse_map_payload(
    entity_type: str = "",
    relation_type: str = "",
    view: str = "",
):
    payload = synapse_map.get_map(
        entity_type=entity_type,
        relation_type=relation_type,
    )

    if not view:
        return payload

    try:
        return synapse_map.project_map_by_scope(payload, view)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc


# --- End Technemachina Synapse Map Read-Only Backend ---


@app.get("/knowledge/status")
async def knowledge_status():
    return knowledge_ingest.knowledge_status()


@app.get("/knowledge/sources")
async def knowledge_sources():
    return knowledge_ingest.load_sources()


@app.get("/knowledge/records")
async def knowledge_records(limit: int = 100, include_inactive: bool = False):
    return {
        "records": knowledge_ingest.load_records(limit=limit, include_inactive=include_inactive),
        "status": knowledge_ingest.knowledge_status(),
    }


@app.post("/knowledge/ingest-text")
async def knowledge_ingest_text(req: KnowledgeIngestTextRequest):
    try:
        return knowledge_ingest.ingest_text(
            title=req.title,
            body=req.body,
            source_type=req.source_type,
            source_path=req.source_path,
            origin=req.origin,
            tags=req.tags,
            created_by=req.created_by,
            provenance=req.provenance,
        )
    except ValueError as exc:
        return {"status": "error", "detail": str(exc)}


@app.get("/knowledge/search")
async def knowledge_search(
    query: str,
    limit: int = 10,
    include_duplicates: bool = False,
    source_status: str = "",
    provenance_label: str = "",
):
    return knowledge_ingest.search_knowledge(
        query=query,
        limit=limit,
        include_duplicates=include_duplicates,
        source_status=source_status,
        provenance_label=provenance_label,
    )


# --- End Technemachina Knowledge Ingest Foundation ---

# --- Technemachina Knowledge-to-Candidate Bridge v0.2.8c ---

@app.get("/knowledge/candidates/status")
async def knowledge_candidates_status():
    return knowledge_ingest.knowledge_candidate_status()


@app.get("/knowledge/candidates")
async def knowledge_candidates(
    limit: int = 100,
    include_closed: bool = True,
    current_only: bool = True,
):
    return {
        "candidates": knowledge_ingest.load_knowledge_candidates(
            limit=limit,
            include_closed=include_closed,
            current_only=current_only,
        ),
        "status": knowledge_ingest.knowledge_candidate_status(),
    }


@app.get("/knowledge/candidates/bridge-status")
async def knowledge_candidates_bridge_status():
    return knowledge_ingest.knowledge_bridge_status()


@app.post("/knowledge/candidates/from-record")
async def knowledge_candidate_from_record(req: KnowledgeCandidateCreateRequest):
    try:
        return knowledge_ingest.build_candidate_from_knowledge(
            knowledge_record_id=req.knowledge_record_id,
            created_by=req.created_by,
            reason=req.reason,
            force=req.force,
        )
    except ValueError as exc:
        return {"status": "error", "detail": str(exc)}


@app.post("/knowledge/candidates/{candidate_id}/enqueue")
async def knowledge_candidate_enqueue(candidate_id: str, req: KnowledgeCandidateEnqueueRequest):
    try:
        return knowledge_ingest.enqueue_knowledge_candidate(
            candidate_id=candidate_id,
            reviewed_by=req.reviewed_by,
            notes=req.notes,
        )
    except ValueError as exc:
        return {"status": "error", "detail": str(exc)}


# --- End Technemachina Knowledge-to-Candidate Bridge ---




# --- Technemachina Frontend Static Mount Repair ---

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

if FRONTEND_DIR.exists():
    app.mount("/frontend", StaticFiles(directory=str(FRONTEND_DIR)), name="frontend")


@app.get("/app")
async def frontend_app():
    return FileResponse(FRONTEND_DIR / "index.html")


# --- End Technemachina Frontend Static Mount Repair ---


@app.get("/memory/review/status")
async def memory_review_status():
    return memory_review_queue.review_status()


@app.get("/memory/review/queue")
async def memory_review_queue_endpoint(include_closed: bool = False):
    return {
        "queue": memory_review_queue.load_queue(include_closed=include_closed),
        "status": memory_review_queue.review_status(),
    }


@app.get("/memory/review/decisions")
async def memory_review_decisions(limit: int = 100):
    return {
        "decisions": memory_review_queue.load_decisions(limit=limit)
    }


@app.post("/memory/review/enqueue")
async def memory_review_enqueue(req: MemoryReviewCreateRequest):
    try:
        item = memory_review_queue.create_review_item(
            candidate_record=req.candidate_record,
            suggested_action=req.suggested_action,
            reason=req.reason,
            source_refs=req.source_refs,
            conflicting_record_ids=req.conflicting_record_ids,
            related_record_ids=req.related_record_ids,
            original_record=req.original_record,
            created_by=req.created_by,
        )
        return {"status": "success", "review": item}
    except Exception as exc:
        return {"status": "error", "detail": str(exc)}


@app.get("/memory/review/{review_id}")
async def memory_review_get(review_id: str):
    item = memory_review_queue.get_review_item(review_id)
    if not item:
        return {"status": "error", "detail": "review_not_found"}
    return {"status": "success", "review": item}


@app.post("/memory/review/{review_id}/approve")
async def memory_review_approve(review_id: str, req: MemoryReviewDecisionRequest):
    try:
        result = memory_review_queue.approve_review(
            review_id=review_id,
            reviewed_by=req.reviewed_by,
            notes=req.notes,
        )
        if not result:
            return {"status": "error", "detail": "review_not_found"}
        return {"status": "success", **result}
    except Exception as exc:
        return {"status": "error", "detail": str(exc)}


@app.post("/memory/review/{review_id}/reject")
async def memory_review_reject(review_id: str, req: MemoryReviewDecisionRequest):
    try:
        result = memory_review_queue.reject_review(
            review_id=review_id,
            reviewed_by=req.reviewed_by,
            notes=req.notes,
        )
        if not result:
            return {"status": "error", "detail": "review_not_found"}
        return {"status": "success", **result}
    except Exception as exc:
        return {"status": "error", "detail": str(exc)}


@app.post("/memory/review/{review_id}/defer")
async def memory_review_defer(review_id: str, req: MemoryReviewDecisionRequest):
    try:
        result = memory_review_queue.defer_review(
            review_id=review_id,
            reviewed_by=req.reviewed_by,
            notes=req.notes,
        )
        if not result:
            return {"status": "error", "detail": "review_not_found"}
        return {"status": "success", **result}
    except Exception as exc:
        return {"status": "error", "detail": str(exc)}


@app.post("/memory/review/{review_id}/edit")
async def memory_review_edit(review_id: str, req: MemoryReviewEditRequest):
    try:
        result = memory_review_queue.edit_review(
            review_id=review_id,
            patch=req.patch,
            reviewed_by=req.reviewed_by,
            notes=req.notes,
        )
        if not result:
            return {"status": "error", "detail": "review_not_found"}
        return {"status": "success", **result}
    except Exception as exc:
        return {"status": "error", "detail": str(exc)}


@app.post("/memory/consolidate")
async def memory_consolidate(req: MemoryConsolidationRequest):
    return memory_consolidation_worker.consolidate_memory(
        dry_run=req.dry_run,
        limit=req.limit,
    )


@app.get("/memory/consolidation/status")
async def memory_consolidation_status():
    return memory_consolidation_worker.consolidation_status()


@app.get("/memory/consolidation/journal")
async def memory_consolidation_journal(limit: int = 50):
    return {
        "journal": memory_consolidation_worker.load_journal(limit=limit)
    }


@app.get("/memory/search")
async def memory_search_get(
    query: str,
    record_type: str | None = None,
    layer: str | None = None,
    scope: str | None = None,
    include_revoked: bool = False,
    limit: int = 10,
    min_score: float = 0.01,
):
    return memory_retrieval.search_memory(
        query=query,
        record_type=record_type,
        layer=layer,
        scope=scope,
        include_revoked=include_revoked,
        limit=limit,
        min_score=min_score,
    )


@app.post("/memory/search")
async def memory_search_post(req: MemorySearchRequest):
    return memory_retrieval.search_memory(
        query=req.query,
        record_type=req.record_type,
        layer=req.layer,
        scope=req.scope,
        include_revoked=req.include_revoked,
        limit=req.limit,
        min_score=req.min_score,
    )


@app.get("/memory/taxonomy")
async def memory_taxonomy_endpoint():
    return memory_taxonomy.taxonomy_summary()


@app.get("/memory/records")
async def memory_records(include_revoked: bool = False):
    return {
        "records": memory_taxonomy.load_records(include_revoked=include_revoked),
        "summary": memory_taxonomy.taxonomy_summary(),
    }


@app.post("/memory/record")
async def create_memory_record_endpoint(req: MemoryRecordRequest):
    try:
        record = memory_taxonomy.create_memory_record(
            record_type=req.record_type,
            layer=req.layer,
            scope=req.scope,
            title=req.title,
            summary=req.summary,
            body=req.body,
            tags=req.tags,
            source_type=req.source_type,
            source_ref=req.source_ref,
            source_title=req.source_title,
            created_by=req.created_by,
            provenance=req.provenance,
            confidence=req.confidence,
            status=req.status,
            review_state=req.review_state,
            expires_at=req.expires_at,
            risk_level=req.risk_level,
            supersedes=req.supersedes,
            attach_to_context=req.attach_to_context,
            retrieval_priority=req.retrieval_priority,
            recency_weight=req.recency_weight,
            importance_weight=req.importance_weight,
        )
        return {"status": "success", "record": record}
    except Exception as exc:
        return {"status": "error", "detail": str(exc)}


@app.post("/memory/{record_id}/revoke")
async def revoke_memory_endpoint(record_id: str, req: MemoryRevokeRequest):
    record = memory_taxonomy.revoke_memory(record_id, reason=req.reason)
    if not record:
        return {"status": "error", "detail": "memory_not_found"}
    return {"status": "success", "record": record}




def _companion_node_id(node: dict) -> str:
    return str(node.get("id") or "")


def _companion_edge_endpoint(edge: dict, side: str) -> str:
    aliases = {
        "source": ("source", "from", "source_id"),
        "target": ("target", "to", "target_id"),
    }

    for key in aliases[side]:
        value = edge.get(key)

        if isinstance(value, dict):
            value = value.get("id")

        if value:
            return str(value)

    return ""


def _companion_associations(
    selected_node_id: str,
    nodes: list[dict],
    edges: list[dict],
) -> list[dict]:
    nodes_by_id = {
        _companion_node_id(node): node
        for node in nodes
        if _companion_node_id(node)
    }

    associated_ids: list[str] = []

    for edge in edges:
        source_id = _companion_edge_endpoint(edge, "source")
        target_id = _companion_edge_endpoint(edge, "target")

        if source_id == selected_node_id and target_id:
            associated_ids.append(target_id)
        elif target_id == selected_node_id and source_id:
            associated_ids.append(source_id)

    associations: list[dict] = []

    for node_id in dict.fromkeys(associated_ids):
        node = nodes_by_id.get(node_id)

        if not node:
            continue

        associations.append({
            "id": node_id,
            "title": (
                node.get("title")
                or node.get("label")
                or node.get("name")
                or node_id
            ),
            "owner_scope": node.get("owner_scope"),
        })

    return associations


@app.post("/companion/respond")
async def companion_respond(req: CompanionRequest):
    if req.view != "companion":
        raise HTTPException(
            status_code=400,
            detail="Companion responses require view=companion",
        )

    user_message = req.user_message.strip()
    selected_node_id = req.selected_node_id.strip()

    if not user_message:
        raise HTTPException(
            status_code=400,
            detail="user_message is required",
        )

    if not selected_node_id:
        raise HTTPException(
            status_code=400,
            detail="selected_node_id is required",
        )

    companion_graph = await synapse_map_payload(view="companion")
    nodes = list(companion_graph.get("nodes", []))
    edges = list(
        companion_graph.get("edges")
        or companion_graph.get("relations")
        or []
    )

    selected_node = next(
        (
            node
            for node in nodes
            if _companion_node_id(node) == selected_node_id
        ),
        None,
    )

    if selected_node is None:
        raise HTTPException(
            status_code=400,
            detail="Selected node is not available in the Companion view",
        )

    associations = _companion_associations(
        selected_node_id=selected_node_id,
        nodes=nodes,
        edges=edges,
    )

    selected_title = (
        selected_node.get("title")
        or selected_node.get("label")
        or selected_node.get("name")
        or selected_node_id
    )

    selected_description_raw = str(
        selected_node.get("description")
        or selected_node.get("summary")
        or selected_node.get("body")
        or ""
    )

    description_truncated = (
        len(selected_description_raw)
        > COMPANION_DESCRIPTION_MAX_CHARS
    )

    if description_truncated:
        selected_description = (
            selected_description_raw[
                :COMPANION_DESCRIPTION_MAX_CHARS
            ]
            + "\n[...truncated]"
        )
    else:
        selected_description = selected_description_raw

    association_context = "\n".join(
        f'- {item["title"]} [{item["id"]}]'
        for item in associations[
            :COMPANION_ASSOCIATION_CONTEXT_LIMIT
        ]
    ) or "- No permitted neighboring nodes were found."

    grounded_prompt = f"""
You are the Technemachina Companion operating through the Synapse Map.

Surface: Map-local
View: companion
Permission boundary: Read-only. Memory mutation is Oracle-gated.
Grounding rule: Use only the selected node and permitted associations supplied below.
Do not claim that memory was changed, saved, approved, or executed.

Selected node:
ID: {selected_node_id}
Title: {selected_title}
Owner scope: {selected_node.get("owner_scope", "unknown")}
Description:
{selected_description}

Permitted associations:
{association_context}

Oracle's question:
{user_message}

Answer warmly and directly. Explain what is grounded in Synapse and clearly
acknowledge when the supplied context is insufficient.
""".strip()

    answer = await asyncio.to_thread(
        ai.query_model,
        grounded_prompt,
        "auto",
    )

    suggestions = [
        {
            "action": "inspect_association",
            "node_id": item["id"],
            "label": f'Explore {item["title"]}',
        }
        for item in associations[:COMPANION_SUGGESTIONS_LIMIT]
    ]

    if not suggestions:
        suggestions = [{
            "action": "ask_follow_up",
            "node_id": selected_node_id,
            "label": f"Ask a follow-up about {selected_title}",
        }]

    return {
        "answer": answer,
        "selected_node": {
            "id": selected_node_id,
            "title": selected_title,
            "owner_scope": selected_node.get("owner_scope"),
        },
        "grounding": {
            "primary": "synapse",
            "selected_node_id": selected_node_id,
            "association_count": len(associations),
            "live_web": False,
            "description_truncated": description_truncated,
        },
        "associations": associations,
        "suggestions": suggestions,
        "permissions": {
            "memory_mutation": "oracle_gated",
            "read_only": True,
            "surface": "map_local",
        },
        "view": "companion",
    }


@app.get("/companion/surface-context")
async def companion_surface_context():
    runtime_path = Path(__file__).resolve().parent / "runtime_context" / "synapse_frontend_status.json"

    if not runtime_path.exists():
        return {
            "status": "missing",
            "detail": "runtime_context/synapse_frontend_status.json not found"
        }

    try:
        data = json.loads(runtime_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {
            "status": "error",
            "detail": str(exc)
        }

    return {
        "status": "success",
        "surface_context": data,
        "permission_boundary": {
            "visual_perception": "not_direct_browser_vision",
            "project_awareness": "runtime_context_available",
            "memory_mutation": "oracle_gated"
        }
    }


@app.get("/system-info")
async def system_info():
    context = project_context.load_context()
    return {
        "system": context.get("project", "Technemachina Daemon"),
        "version": context.get("current_version", "unknown"),
        "status": context.get("status", "unknown"),
        "active_provider": context.get("active_provider", "unknown"),
        "current_objective": context.get("current_objective", "unknown"),
        "primary_user": context.get("primary_user", "Crybaby404 / Oracle"),
        "assistant_role": context.get("assistant_role", "Master"),
        "daemon_role": context.get("daemon_role", "Apprentice"),
        "locked_milestones": context.get("locked_milestones", []),
    }

@app.get("/brain-health")
async def brain_health():
    return monitor.check_brain_health("gemini")

@app.get("/brain-status")
async def brain_status():
    return get_brain_status()



# --- Technemachina Daemon Awareness Bridge v0.3.7 ---

def load_daemon_runtime_awareness() -> str:
    """Load bounded runtime project awareness for chat prompt injection."""
    runtime_path = Path(__file__).resolve().parent / "runtime_context" / "synapse_frontend_status.json"

    if not runtime_path.exists():
        return ""

    try:
        data = json.loads(runtime_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return f"""
DAEMON RUNTIME AWARENESS:
- runtime_context_status: unreadable
- detail: {exc}
"""

    features = data.get("confirmed_features", [])
    feature_lines = "\n".join(f"- {item}" for item in features)

    return f"""
DAEMON RUNTIME AWARENESS:
Surface: {data.get("surface", "unknown")}
Status: {data.get("status", "unknown")}
Date: {data.get("date", "unknown")}

Summary:
{data.get("summary", "")}

Confirmed frontend/project features:
{feature_lines}

Boundary:
{data.get("important_boundary", "")}

Correct bounded response:
{data.get("correct_daemon_response", "")}

Instruction:
If asked whether Synapse Map renderer work exists, do not say no upgrades have been registered.
Say you cannot visually perceive the browser canvas directly, but runtime project context confirms the Synapse Map frontend prototype and renderer work exist.
Do not mention Perplexity, Claude, ChatGPT, web search, APIs, or external tools unless the user explicitly asks for tool suggestions.
Keep the answer bounded, concise, and project-aware.
"""

# --- End Technemachina Daemon Awareness Bridge ---

@app.post("/chat")
async def handle_chat(req: ChatRequest):
    requested_thread_id = getattr(req, "thread_id", "") or thread_registry.get_active_thread_id()
    thread_id = thread_registry.safe_thread_id(requested_thread_id)

    # Ensure this thread exists in the local registry.
    thread_registry.ensure_thread(thread_id=thread_id)

    # Save the user's latest message locally first.
    thread_context.append_message(
        role="user",
        content=req.prompt,
        thread_id=thread_id,
    )
    thread_registry.touch_thread(
        thread_id=thread_id,
        role="user",
        content=req.prompt,
    )

    # Build a context-aware prompt from recent local thread history.
    context_prompt = thread_context.build_context_prompt(
        latest_user_message=req.prompt,
        thread_id=thread_id,
        history_limit=16,
    )

    # Inject bounded runtime awareness before sending to the active brain/provider.
    runtime_awareness = load_daemon_runtime_awareness()
    if runtime_awareness:
        context_prompt = f"{context_prompt}\n\n{runtime_awareness}"

    # Send recent thread context to the active brain/provider.
    reply = ai.query_model(context_prompt, req.model)

    # Save the Daemon's reply locally.
    thread_context.append_message(
        role="daemon",
        content=reply,
        thread_id=thread_id,
    )
    thread_registry.touch_thread(
        thread_id=thread_id,
        role="daemon",
        content=reply,
    )

    return {
        "response": reply,
        "thread_id": thread_id,
        "context": "thread_context_window_active"
    }



# --- Technemachina Thread-to-Memory Candidate Flow v0.2.7e ---

@app.get("/memory/candidates/status")
async def memory_candidates_status():
    return thread_to_memory.candidate_status()


@app.get("/memory/candidates")
async def list_memory_candidates(include_enqueued: bool = True):
    return {
        "candidates": thread_to_memory.load_candidates(include_enqueued=include_enqueued),
        "status": thread_to_memory.candidate_status(),
    }


@app.post("/memory/candidates/from-thread")
async def create_memory_candidates_from_thread(thread_id: str = "", limit: int = 40):
    return thread_to_memory.generate_candidates_from_thread(
        thread_id=thread_id,
        limit=limit,
        persist=True,
    )


@app.post("/memory/candidates/{candidate_id}/enqueue")
async def enqueue_memory_candidate(candidate_id: str, reviewed_by: str = "Oracle", notes: str = ""):
    try:
        return thread_to_memory.enqueue_candidate(
            candidate_id=candidate_id,
            reviewed_by=reviewed_by,
            notes=notes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# --- End Technemachina Thread-to-Memory Candidate Flow ---


@app.get("/threads")
async def list_threads():
    return {
        "active_thread_id": thread_registry.get_active_thread_id(),
        "threads": thread_registry.list_threads(),
    }

@app.post("/threads/new")
async def create_thread():
    thread = thread_registry.create_thread()
    return {
        "status": "success",
        "thread": thread,
    }

@app.get("/threads/location")
async def thread_location():
    return {
        "thread_messages_path": "logs/threads/<thread_id>.jsonl",
        "default_thread_path": "logs/threads/default.jsonl",
        "thread_registry_path": "logs/threads/thread_registry.json",
        "audit_log_path": "logs/audit_log.jsonl",
        "decision_ledger_path": "logs/decision_ledger.jsonl",
        "doctrine": "Threads are stored in logs/threads/<thread_id>.jsonl with metadata in logs/threads/thread_registry.json. Audit logs and decision ledgers are separate records, not thread storage."
    }


@app.post("/threads/{thread_id}/rename")
async def rename_thread_endpoint(thread_id: str, req: ThreadRenameRequest):
    thread = thread_registry.rename_thread(thread_id, req.title)
    if not thread:
        return {"status": "error", "detail": "thread_not_found"}
    return {"status": "success", "thread": thread}


@app.post("/threads/{thread_id}/archive")
async def archive_thread_endpoint(thread_id: str):
    thread = thread_registry.archive_thread(thread_id)
    if not thread:
        return {"status": "error", "detail": "thread_not_found"}
    return {
        "status": "success",
        "thread": thread,
        "active_thread_id": thread_registry.get_active_thread_id(),
        "threads": thread_registry.list_threads()
    }


@app.post("/threads/{thread_id}/restore")
async def restore_thread_endpoint(thread_id: str):
    thread = thread_registry.restore_thread(thread_id)
    if not thread:
        return {"status": "error", "detail": "thread_not_found"}
    return {
        "status": "success",
        "thread": thread,
        "active_thread_id": thread_registry.get_active_thread_id(),
        "threads": thread_registry.list_threads()
    }


@app.get("/threads/{thread_id}")
async def get_thread(thread_id: str):
    thread = thread_registry.get_thread(thread_id)

    if not thread:
        thread = thread_registry.ensure_thread(thread_id=thread_id)

    messages = thread_context.load_messages(thread_id=thread_id, limit=40)

    return {
        "thread": thread,
        "messages": messages,
    }


@app.post("/explain")
async def handle_explain(req: ToolRequest):
    prompt = tools.format_explain_prompt(req.code)
    reply = ai.query_model(prompt, req.model)
    return {"response": reply}

@app.post("/debug")
async def handle_debug(req: ToolRequest):
    risk_report = classify_text(req.code)

    if risk_report.level == RiskLevel.BLOCKED:
        return JSONResponse(
            status_code=403,
            content={
                "risk": risk_report.model_dump(mode="json"),
                "error": "blocked_risk",
                "message": "Debug request blocked by risk policy.",
            },
        )

    prompt = tools.format_debug_prompt(req.code)
    reply = ai.query_model(prompt, req.model)

    return {
        "risk": risk_report.model_dump(),
        "response": reply
    }

@app.post("/risk")
async def handle_risk(req: RiskRequest):
    return classify_text(req.text).model_dump()

@app.post("/notebook")
async def handle_note(req: NoteRequest):
    memory.save_note(req.topic, req.notes)
    return {"status": "success"}

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
