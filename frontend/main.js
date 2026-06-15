const BACKEND_URL = "http://127.0.0.1:8000";

// --- Technemachina Dynamic System Info v0.2.6d ---
let technemachinaSystemInfo = null;

async function refreshSystemInfo() {
    try {
        const response = await fetch(`${BACKEND_URL}/system-info`);
        if (!response.ok) throw new Error(await response.text());

        const data = await response.json();
        technemachinaSystemInfo = data;

        const versionLabel = document.getElementById("system-version-label");
        const statusLabel = document.getElementById("system-status-label");
        const terminal = document.getElementById("terminal-out");

        if (versionLabel) {
            versionLabel.textContent = `${data.version || "unknown"} · ${data.active_provider || "provider unknown"}`;
            versionLabel.title = data.current_objective || "";
        }

        if (statusLabel) {
            statusLabel.textContent = data.status || "status unknown";
            statusLabel.title = data.current_objective || "";
        }

        if (terminal && terminal.textContent.includes("loading system context")) {
            terminal.textContent = `[Technemachina Daemon ${data.version || "unknown"} online]`;
        }
    } catch (error) {
        console.error("Failed to refresh system info:", error);

        const versionLabel = document.getElementById("system-version-label");
        if (versionLabel) {
            versionLabel.textContent = "system info unavailable";
        }
    }
}
// --- End Technemachina Dynamic System Info ---


// --- Technemachina Thread Sidebar UI v0.2.6c-2 ---
let activeThreadId = localStorage.getItem("technemachinaActiveThreadId") || null;

function setActiveThreadId(threadId) {
    if (!threadId) return;
    activeThreadId = threadId;
    localStorage.setItem("technemachinaActiveThreadId", activeThreadId);

    const label = document.getElementById("active-thread-label");
    if (label) {
        label.textContent = `Active: ${activeThreadId}`;
        label.title = activeThreadId;
    }

    document.querySelectorAll(".thread-item").forEach(item => {
        item.classList.toggle("active", item.dataset.threadId === activeThreadId);
    });
}

function clearOutput(message = "[Technemachina Daemon v0.1 online]") {
    const display = document.getElementById("terminal-out");
    display.innerHTML = "";
    display.textContent = message;
}

function renderThreadMessages(messages) {
    const display = document.getElementById("terminal-out");
    display.innerHTML = "";

    if (!messages || messages.length === 0) {
        display.textContent = "[New thread ready]";
        return;
    }

    messages.forEach(message => {
        const role = String(message.role || "daemon").toLowerCase();
        const label = role === "user" ? "USER" : "DAEMON";
        appendOutput(label, message.content || "");
    });
}

function renderThreadList(threads) {
    const list = document.getElementById("thread-list");
    if (!list) return;

    list.innerHTML = "";

    if (!threads || threads.length === 0) {
        const empty = document.createElement("div");
        empty.className = "thread-empty";
        empty.textContent = "No threads yet.";
        list.appendChild(empty);
        return;
    }

    threads.forEach(thread => {
        const item = document.createElement("div");
        item.className = "thread-item";
        item.dataset.threadId = thread.thread_id;
        item.tabIndex = 0;

        const top = document.createElement("div");
        top.className = "thread-topline";

        const title = document.createElement("div");
        title.className = "thread-title";
        title.textContent = thread.title || thread.thread_id;

        const controls = document.createElement("div");
        controls.className = "thread-controls";

        const renameButton = document.createElement("button");
        renameButton.type = "button";
        renameButton.className = "thread-control-btn rename";
        renameButton.title = "Rename thread";
        renameButton.textContent = "EDIT";
        renameButton.addEventListener("click", (event) => {
            event.stopPropagation();
            renameThread(thread.thread_id);
        });

        const archiveButton = document.createElement("button");
        archiveButton.type = "button";
        archiveButton.className = "thread-control-btn archive";
        archiveButton.title = "Archive thread";
        archiveButton.textContent = "X";
        archiveButton.addEventListener("click", (event) => {
            event.stopPropagation();
            archiveThread(thread.thread_id);
        });

        controls.appendChild(renameButton);
        controls.appendChild(archiveButton);

        top.appendChild(title);
        top.appendChild(controls);

        const preview = document.createElement("div");
        preview.className = "thread-preview";
        preview.textContent = thread.preview || "No preview yet.";

        const meta = document.createElement("div");
        meta.className = "thread-meta";
        meta.textContent = `${thread.message_count || 0} messages`;

        item.appendChild(top);
        item.appendChild(preview);
        item.appendChild(meta);

        item.addEventListener("click", () => selectThread(thread.thread_id));
        item.addEventListener("keydown", (event) => {
            if (event.key === "Enter") selectThread(thread.thread_id);
        });

        list.appendChild(item);
    });

    setActiveThreadId(activeThreadId || threads[0].thread_id);
}


async function renameThread(threadId) {
    if (!threadId) return;

    const currentItem = document.querySelector(`.thread-item[data-thread-id="${CSS.escape(threadId)}"]`);
    const currentTitle = currentItem?.querySelector(".thread-title")?.textContent || "";

    const newTitle = prompt("Rename thread:", currentTitle);
    if (!newTitle || !newTitle.trim()) return;

    try {
        const response = await fetch(`${BACKEND_URL}/threads/${encodeURIComponent(threadId)}/rename`, {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({title: newTitle.trim()})
        });

        if (!response.ok) throw new Error(await response.text());

        await refreshThreads();
    } catch (error) {
        console.error("Failed to rename thread:", error);
        appendOutput("ERROR", "Could not rename thread.");
    }
}

async function archiveThread(threadId) {
    if (!threadId) return;

    const confirmed = confirm("Archive this thread? It will be hidden from the sidebar but kept on disk.");
    if (!confirmed) return;

    try {
        const response = await fetch(`${BACKEND_URL}/threads/${encodeURIComponent(threadId)}/archive`, {
            method: "POST",
            headers: {"Content-Type": "application/json"}
        });

        if (!response.ok) throw new Error(await response.text());

        const data = await response.json();

        if (data.active_thread_id) {
            setActiveThreadId(data.active_thread_id);
        }

        await refreshThreads();

        if (activeThreadId) {
            await selectThread(activeThreadId);
        }
    } catch (error) {
        console.error("Failed to archive thread:", error);
        appendOutput("ERROR", "Could not archive thread.");
    }
}


async function refreshThreads() {
    try {
        const response = await fetch(`${BACKEND_URL}/threads`);
        if (!response.ok) throw new Error(await response.text());

        const data = await response.json();
        const threads = data.threads || [];

        const serverActive = data.active_thread_id || null;
        const localStillExists = threads.some(t => t.thread_id === activeThreadId);

        if (!activeThreadId || !localStillExists) {
            activeThreadId = serverActive || (threads[0] ? threads[0].thread_id : "default");
        }

        renderThreadList(threads);
        setActiveThreadId(activeThreadId);
    } catch (error) {
        console.error("Failed to refresh threads:", error);
        const label = document.getElementById("active-thread-label");
        if (label) label.textContent = "Active: thread backend unavailable";
    }
}

async function selectThread(threadId) {
    if (!threadId) return;

    setActiveThreadId(threadId);

    try {
        const response = await fetch(`${BACKEND_URL}/threads/${encodeURIComponent(threadId)}`);
        if (!response.ok) throw new Error(await response.text());

        const data = await response.json();
        renderThreadMessages(data.messages || []);
        await refreshThreads();
    } catch (error) {
        console.error("Failed to load thread:", error);
        appendOutput("ERROR", `Could not load thread ${threadId}`);
    }
}

async function createNewThread() {
    try {
        const response = await fetch(`${BACKEND_URL}/threads/new`, {
            method: "POST",
            headers: {"Content-Type": "application/json"}
        });

        if (!response.ok) throw new Error(await response.text());

        const data = await response.json();
        const thread = data.thread || data;
        const threadId = thread.thread_id;

        setActiveThreadId(threadId);
        await refreshThreads();
        await selectThread(threadId);
    } catch (error) {
        console.error("Failed to create thread:", error);
        appendOutput("ERROR", "Could not create a new thread.");
    }
}

async function initThreadSidebar() {
    const newThreadButton = document.getElementById("new-thread-btn");
    if (newThreadButton && newThreadButton.dataset.bound !== "true") {
        newThreadButton.dataset.bound = "true";
        newThreadButton.addEventListener("click", createNewThread);
    }

    const refreshButton = document.getElementById("refresh-threads-btn");
    if (refreshButton && refreshButton.dataset.bound !== "true") {
        refreshButton.dataset.bound = "true";
        refreshButton.addEventListener("click", refreshThreads);
    }

    await refreshThreads();

    if (activeThreadId) {
        await selectThread(activeThreadId);
    }
}
// --- End Technemachina Thread Sidebar UI ---


function appendOutput(label, text) {
    const display = document.getElementById("terminal-out");

    const message = document.createElement("div");
    message.className = `chat-row ${String(label).toLowerCase()}`;

    const header = document.createElement("div");
    header.className = "chat-label";
    header.textContent = `[${label}]`;

    const body = document.createElement("div");
    body.className = "chat-body";

    if (typeof renderCodeBlocks === "function") {
        body.innerHTML = renderCodeBlocks(text);
    } else {
        body.textContent = text;
    }

    message.appendChild(header);
    message.appendChild(body);
    display.appendChild(message);

    if (typeof enhanceLatestMessage === "function") {
        enhanceLatestMessage();
    }

    display.scrollTop = display.scrollHeight;
}


function getInput() {
    return document.getElementById("cmd-in").value.trim();
}

function clearInput() {
    document.getElementById("cmd-in").value = "";
}

function getModel() {
    return document.getElementById("engine-select").value;
}

async function postJSON(path, payload) {
    const res = await fetch(`${BACKEND_URL}${path}`, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(payload)
    });

    if (!res.ok) {
        const err = await res.text();
        throw new Error(err);
    }

    return await res.json();
}

async function dispatchChat() {
    const text = getInput();
    if (!text) return;

    appendOutput("USER", text);
    clearInput();

    try {
        const data = await postJSON("/chat", {
            prompt: text,
            model: getModel(),
            thread_id: activeThreadId || "default"
        });

        if (data.thread_id) {
            setActiveThreadId(data.thread_id);
        }

        appendOutput("DAEMON", data.response);
        await refreshThreads();
    } catch (e) {
        appendOutput("ERROR", "Backend disconnected or model unavailable.");
    }
}

async function runTool(actionType) {
    const code = getInput();
    if (!code) {
        alert("Paste code or technical content first.");
        return;
    }

    appendOutput("TOOL", `Running ${actionType}...`);

    try {
        const data = await postJSON(`/${actionType}`, {
            code: code,
            model: getModel()
        });

        if (data.risk) {
            appendOutput("RISK", JSON.stringify(data.risk, null, 2));
        }

        appendOutput(actionType.toUpperCase(), data.response);
    } catch (e) {
        appendOutput("ERROR", `${actionType} failed.`);
    }
}

async function runRiskCheck() {
    const text = getInput();
    if (!text) return;

    try {
        const data = await postJSON("/risk", { text });
        appendOutput("RISK CHECK", JSON.stringify(data, null, 2));
    } catch (e) {
        appendOutput("ERROR", "Risk check failed.");
    }
}

async function commitLog() {
    const topic = document.getElementById("log-topic").value.trim();
    const notes = document.getElementById("log-body").value.trim();

    if (!topic || !notes) return;

    try {
        await postJSON("/notebook", { topic, notes });
        document.getElementById("log-topic").value = "";
        document.getElementById("log-body").value = "";
        appendOutput("NOTE", "Learning log entry saved.");
    } catch (e) {
        appendOutput("ERROR", "Failed to save note.");
    }
}

// v0.2.3 Provider Brain Lights
async function refreshBrainStatus() {
    try {
        const response = await fetch("http://127.0.0.1:8000/brain-status");
        const data = await response.json();

        if (!data.providers) return;

        data.providers.forEach(provider => {
            const light = document.getElementById(`light-${provider.provider}`);
            if (!light) return;

            light.classList.remove("green", "red");
            light.classList.add(provider.light === "green" ? "green" : "red");
            light.title = provider.detail || provider.provider;
        });
    } catch (e) {
        console.error("Failed to refresh brain status:", e);
    }
}



// --- Technemachina Read-Only Memory UI Panel v0.2.7d ---

function memoryBadge(text, className = "") {
    const span = document.createElement("span");
    span.className = `memory-badge ${className}`.trim();
    span.textContent = text;
    return span;
}

function renderMemoryLayerSummary(summary) {
    const container = document.getElementById("memory-layer-summary");
    if (!container) return;

    container.innerHTML = "";

    const index = summary?.index || {};
    const layers = index.layers || {};
    const records = index.record_count ?? 0;
    const revoked = index.revoked_count ?? 0;

    const header = document.createElement("div");
    header.className = "memory-summary-line";
    header.textContent = `${records} active records · ${revoked} revoked`;
    container.appendChild(header);

    ["gamma", "beta", "alpha", "theta", "delta"].forEach(layer => {
        const row = document.createElement("div");
        row.className = "memory-layer-row";

        const label = document.createElement("span");
        label.textContent = layer.toUpperCase();

        const count = document.createElement("span");
        count.textContent = layers[layer] || 0;

        row.appendChild(label);
        row.appendChild(count);
        container.appendChild(row);
    });
}

function renderMemoryRecords(records) {
    const list = document.getElementById("memory-record-list");
    if (!list) return;

    list.innerHTML = "";

    if (!records || records.length === 0) {
        list.textContent = "No memory records.";
        return;
    }

    records.slice(0, 12).forEach(record => {
        const item = document.createElement("div");
        item.className = "memory-record-item";

        const title = document.createElement("div");
        title.className = "memory-record-title";
        title.textContent = record.title || record.record_id || "Untitled memory";

        const meta = document.createElement("div");
        meta.className = "memory-record-meta";
        meta.appendChild(memoryBadge(record.layer || "layer"));
        meta.appendChild(memoryBadge(record.record_type || "type"));
        meta.appendChild(memoryBadge(record.confidence || "confidence"));
        meta.appendChild(memoryBadge(record.status || "status"));

        const summary = document.createElement("div");
        summary.className = "memory-record-summary";
        summary.textContent = record.summary || record.body || "";

        const source = document.createElement("div");
        source.className = "memory-record-source";
        source.textContent = `Source: ${record.source_ref || "unknown"}`;

        item.appendChild(title);
        item.appendChild(meta);
        item.appendChild(summary);
        item.appendChild(source);

        list.appendChild(item);
    });
}

function renderMemoryReviewQueue(queue) {
    const list = document.getElementById("memory-review-list");
    if (!list) return;

    list.innerHTML = "";

    if (!queue || queue.length === 0) {
        list.textContent = "No pending review items.";
        return;
    }

    queue.slice(0, 8).forEach(item => {
        const row = document.createElement("div");
        row.className = "memory-review-item";

        const title = document.createElement("div");
        title.className = "memory-record-title";
        title.textContent = item.title || item.review_id || "Untitled review";

        const meta = document.createElement("div");
        meta.className = "memory-record-meta";
        meta.appendChild(memoryBadge(item.review_status || "pending"));
        meta.appendChild(memoryBadge(item.suggested_action || "action"));
        meta.appendChild(memoryBadge(item.layer || "layer"));

        const reason = document.createElement("div");
        reason.className = "memory-record-summary";
        reason.textContent = item.reason_for_review || "No reason provided.";

        row.appendChild(title);
        row.appendChild(meta);
        row.appendChild(reason);

        list.appendChild(row);
    });
}

function renderMemorySearchResults(data) {
    const box = document.getElementById("memory-search-results");
    if (!box) return;

    box.innerHTML = "";

    if (!data || !data.selected_record) {
        box.textContent = data?.explanation || "No memory matched.";
        return;
    }

    const selected = data.selected_record;

    const title = document.createElement("div");
    title.className = "memory-record-title";
    title.textContent = selected.title || selected.record_id;

    const why = document.createElement("div");
    why.className = "memory-record-summary";
    why.textContent = selected.why_selected || data.explanation || "";

    const meta = document.createElement("div");
    meta.className = "memory-record-meta";
    meta.appendChild(memoryBadge(`score ${selected.rank_score}`));
    meta.appendChild(memoryBadge(selected.layer || "layer"));
    meta.appendChild(memoryBadge(selected.confidence || "confidence"));
    meta.appendChild(memoryBadge(selected.attach_recommendation || "attach?"));

    const tags = document.createElement("div");
    tags.className = "memory-record-source";
    tags.textContent = `Matched tags: ${(selected.matched_tags || []).join(", ") || "none"}`;

    box.appendChild(title);
    box.appendChild(meta);
    box.appendChild(why);
    box.appendChild(tags);
}

async function refreshMemoryPanel() {
    try {
        const recordsResponse = await fetch(`${BACKEND_URL}/memory/records`);
        const recordsData = await recordsResponse.json();

        renderMemoryLayerSummary(recordsData.summary || {});
        renderMemoryRecords(recordsData.records || []);

        const reviewResponse = await fetch(`${BACKEND_URL}/memory/review/queue`);
        const reviewData = await reviewResponse.json();

        renderMemoryReviewQueue(reviewData.queue || []);
    } catch (error) {
        console.error("Failed to refresh memory panel:", error);

        const layerBox = document.getElementById("memory-layer-summary");
        if (layerBox) layerBox.textContent = "Memory backend unavailable.";

        const recordList = document.getElementById("memory-record-list");
        if (recordList) recordList.textContent = "Could not load memory records.";

        const reviewList = document.getElementById("memory-review-list");
        if (reviewList) reviewList.textContent = "Could not load review queue.";
    }
}

async function runMemorySearch() {
    const input = document.getElementById("memory-search-input");
    const query = input ? input.value.trim() : "";

    if (!query) {
        renderMemorySearchResults({ explanation: "Enter a memory search query." });
        return;
    }

    try {
        const response = await fetch(`${BACKEND_URL}/memory/search?query=${encodeURIComponent(query)}`);
        const data = await response.json();
        renderMemorySearchResults(data);
    } catch (error) {
        console.error("Memory search failed:", error);
        renderMemorySearchResults({ explanation: "Memory search failed." });
    }
}

function initMemoryPanel() {
    const refreshButton = document.getElementById("refresh-memory-btn");
    if (refreshButton) {
        refreshButton.addEventListener("click", refreshMemoryPanel);
    }

    const searchButton = document.getElementById("memory-search-btn");
    if (searchButton) {
        searchButton.addEventListener("click", runMemorySearch);
    }

    const searchInput = document.getElementById("memory-search-input");
    if (searchInput) {
        searchInput.addEventListener("keydown", event => {
            if (event.key === "Enter") runMemorySearch();
        });
    }

    refreshMemoryPanel();
}

// --- End Technemachina Read-Only Memory UI Panel ---




// --- Technemachina Control Center Shell v0.2.7d ---

function setAppMode(mode) {
    const modes = ["chat", "control", "brain"];

    modes.forEach(name => {
        const page = document.getElementById(`${name === "control" ? "control-center" : name}-page`);
        const button = document.getElementById(`mode-${name === "control" ? "control" : name}-btn`);

        if (page) page.classList.toggle("active", name === mode);
        if (button) button.classList.toggle("active", name === mode);
    });

    localStorage.setItem("technemachinaAppMode", mode);

    if (mode === "control" && typeof refreshMemoryPanel === "function") {
        refreshMemoryPanel();
    }
}

function initModeShell() {
    const chatButton = document.getElementById("mode-chat-btn");
    const controlButton = document.getElementById("mode-control-btn");
    const brainButton = document.getElementById("mode-brain-btn");

    if (chatButton) chatButton.addEventListener("click", () => setAppMode("chat"));
    if (controlButton) controlButton.addEventListener("click", () => setAppMode("control"));
    if (brainButton) brainButton.addEventListener("click", () => setAppMode("brain"));

    const saved = localStorage.getItem("technemachinaAppMode") || "chat";
    setAppMode(saved);
}

// --- End Technemachina Control Center Shell ---


window.addEventListener("DOMContentLoaded", async () => {
    await refreshSystemInfo();
    refreshBrainStatus();
    await initThreadSidebar();
    if (typeof initMemoryPanel === "function") initMemoryPanel();
    initModeShell();
    if (typeof initReviewControls === "function") initReviewControls();
});


// --- Technemachina Code Block Renderer v0.2.6a ---
function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function renderCodeBlocks(text) {
  const parts = String(text).split(/```/g);

  if (parts.length === 1) {
    return escapeHtml(text).replace(/\n/g, "<br>");
  }

  let html = "";

  for (let i = 0; i < parts.length; i++) {
    const part = parts[i];

    if (i % 2 === 0) {
      html += `<div class="message-text">${escapeHtml(part).replace(/\n/g, "<br>")}</div>`;
    } else {
      const firstNewline = part.indexOf("\n");
      let lang = "code";
      let code = part;

      if (firstNewline !== -1) {
        const possibleLang = part.slice(0, firstNewline).trim();
        if (possibleLang.length > 0 && possibleLang.length < 30) {
          lang = possibleLang;
          code = part.slice(firstNewline + 1);
        }
      }

      html += `
        <div class="code-card">
          <div class="code-card-header">
            <span class="code-lang">${escapeHtml(lang)}</span>
            <button class="copy-code-btn" type="button">Copy</button>
          </div>
          <pre><code class="code-content">${syntaxHighlight(code.trim(), lang)}</code></pre>
        </div>
      `;
    }
  }

  return html;
}

function enhanceCodeCopyButtons(container = document) {
  container.querySelectorAll(".copy-code-btn").forEach((button) => {
    if (button.dataset.bound === "true") return;

    button.dataset.bound = "true";

    button.addEventListener("click", async () => {
      const card = button.closest(".code-card");
      const code = card ? card.querySelector("code")?.innerText || "" : "";

      try {
        await navigator.clipboard.writeText(code);
        const oldText = button.innerText;
        button.innerText = "Copied";
        setTimeout(() => {
          button.innerText = oldText;
        }, 1200);
      } catch (error) {
        button.innerText = "Copy failed";
        setTimeout(() => {
          button.innerText = "Copy";
        }, 1200);
      }
    });
  });
}

function enhanceLatestMessage() {
  enhanceCodeCopyButtons(document);
}
// --- End Technemachina Code Block Renderer ---


// --- Technemachina Syntax Highlighting v0.2.6b ---
function syntaxHighlight(code, lang = "code") {
  const language = String(lang).toLowerCase();
  let escaped = escapeHtml(code);
  const stash = [];

  function stashToken(html) {
    const key = `@@TOK${stash.length}@@`;
    stash.push([key, html]);
    return key;
  }

  function restoreTokens(value) {
    for (const [key, html] of stash) {
      value = value.replaceAll(key, html);
    }
    return value;
  }

  if (language.includes("python") || language === "py") {
    escaped = escaped
      .replace(/(#.*$)/gm, function(match) {
        return stashToken(`<span class="tok-comment">${match}</span>`);
      })
      .replace(/(&quot;[^&]*?&quot;|&#039;[^&]*?&#039;)/g, function(match) {
        return stashToken(`<span class="tok-string">${match}</span>`);
      })
      .replace(/\b([0-9]+)\b/g, function(match) {
        return stashToken(`<span class="tok-number">${match}</span>`);
      })
      .replace(/\b(def|if|elif|else|for|while|return|import|from|as|try|except|with|pass|break|continue|in|is|not|and|or|lambda|True|False|None)\b/g, function(match) {
        return stashToken(`<span class="tok-keyword">${match}</span>`);
      })
      .replace(/\b([a-zA-Z_][a-zA-Z0-9_]*)\s*(?=\()/g, function(match) {
        return stashToken(`<span class="tok-function">${match}</span>`);
      });
  }

  if (language.includes("bash") || language.includes("shell") || language === "sh") {
    escaped = escaped
      .replace(/(#.*$)/gm, function(match) {
        return stashToken(`<span class="tok-comment">${match}</span>`);
      })
      .replace(/(&quot;[^&]*?&quot;|&#039;[^&]*?&#039;)/g, function(match) {
        return stashToken(`<span class="tok-string">${match}</span>`);
      })
      .replace(/\b(cd|python|python3|pip|source|echo|cat|cp|mv|mkdir|ls|grep|find|tail|head|nano|open|chmod|curl)\b/g, function(match) {
        return stashToken(`<span class="tok-keyword">${match}</span>`);
      });
  }

  if (language.includes("javascript") || language === "js") {
    escaped = escaped
      .replace(/(\/\/.*$)/gm, function(match) {
        return stashToken(`<span class="tok-comment">${match}</span>`);
      })
      .replace(/(&quot;[^&]*?&quot;|&#039;[^&]*?&#039;|`[^`]*?`)/g, function(match) {
        return stashToken(`<span class="tok-string">${match}</span>`);
      })
      .replace(/\b(function|const|let|var|if|else|return|async|await|try|catch|class|new|true|false|null|document|window)\b/g, function(match) {
        return stashToken(`<span class="tok-keyword">${match}</span>`);
      })
      .replace(/\b([0-9]+)\b/g, function(match) {
        return stashToken(`<span class="tok-number">${match}</span>`);
      });
  }

  return restoreTokens(escaped);
}
// --- End Technemachina Syntax Highlighting ---


// --- Technemachina Control Center Read-Only Memory Polish v0.2.7d-1 ---

function renderMemoryHealth(records = [], summary = {}, queue = []) {
    const strip = document.getElementById("memory-health-strip");
    if (!strip) return;

    const index = summary?.index || {};
    const pending = queue.filter(item => item.review_status === "pending").length;
    const approved = queue.filter(item => item.review_status === "approved").length;

    strip.innerHTML = "";

    [
        ["Active Records", index.record_count ?? records.length ?? 0],
        ["Revoked", index.revoked_count ?? 0],
        ["Pending Reviews", pending],
        ["Approved Reviews", approved],
    ].forEach(([label, value]) => {
        const card = document.createElement("div");
        card.className = "memory-health-card";

        const valueNode = document.createElement("div");
        valueNode.className = "memory-health-value";
        valueNode.textContent = value;

        const labelNode = document.createElement("div");
        labelNode.className = "memory-health-label";
        labelNode.textContent = label;

        card.appendChild(valueNode);
        card.appendChild(labelNode);
        strip.appendChild(card);
    });
}

function inspectMemoryRecord(record, explanation = null) {
    const inspector = document.getElementById("memory-inspector");
    if (!inspector) return;

    if (!record) {
        inspector.textContent = "Select or search a memory record to inspect provenance, confidence, and attach recommendation.";
        return;
    }

    inspector.innerHTML = "";

    const title = document.createElement("div");
    title.className = "memory-inspector-title";
    title.textContent = record.title || record.record_id || "Untitled memory";

    const meta = document.createElement("div");
    meta.className = "memory-record-meta";
    meta.appendChild(memoryBadge(record.layer || "layer"));
    meta.appendChild(memoryBadge(record.record_type || "type"));
    meta.appendChild(memoryBadge(record.confidence || "confidence"));
    meta.appendChild(memoryBadge(record.status || "status"));

    const summary = document.createElement("div");
    summary.className = "memory-record-summary";
    summary.textContent = record.summary || record.body || "No summary.";

    const source = document.createElement("div");
    source.className = "memory-inspector-line";
    source.textContent = `Source: ${record.source_ref || "unknown"}`;

    const provenance = document.createElement("div");
    provenance.className = "memory-inspector-line";
    provenance.textContent = `Provenance: ${record.provenance || "not provided"}`;

    const tags = document.createElement("div");
    tags.className = "memory-inspector-line";
    tags.textContent = `Tags: ${(record.tags || []).join(", ") || "none"}`;

    inspector.appendChild(title);
    inspector.appendChild(meta);
    inspector.appendChild(summary);
    inspector.appendChild(source);
    inspector.appendChild(provenance);
    inspector.appendChild(tags);

    if (explanation) {
        const explain = document.createElement("div");
        explain.className = "memory-explain-box";
        explain.textContent = explanation;
        inspector.appendChild(explain);
    }
}

function renderMemoryRecords(records) {
    const list = document.getElementById("memory-record-list");
    if (!list) return;

    list.innerHTML = "";

    if (!records || records.length === 0) {
        list.textContent = "No memory records.";
        inspectMemoryRecord(null);
        return;
    }

    records.slice(0, 18).forEach(record => {
        const item = document.createElement("button");
        item.type = "button";
        item.className = "memory-record-item memory-clickable";

        const title = document.createElement("div");
        title.className = "memory-record-title";
        title.textContent = record.title || record.record_id || "Untitled memory";

        const meta = document.createElement("div");
        meta.className = "memory-record-meta";
        meta.appendChild(memoryBadge(record.layer || "layer"));
        meta.appendChild(memoryBadge(record.record_type || "type"));
        meta.appendChild(memoryBadge(record.confidence || "confidence"));
        meta.appendChild(memoryBadge(record.status || "status"));

        const summary = document.createElement("div");
        summary.className = "memory-record-summary";
        summary.textContent = record.summary || record.body || "";

        const source = document.createElement("div");
        source.className = "memory-record-source";
        source.textContent = `Source: ${record.source_ref || "unknown"}`;

        item.appendChild(title);
        item.appendChild(meta);
        item.appendChild(summary);
        item.appendChild(source);

        item.addEventListener("click", () => inspectMemoryRecord(record));
        list.appendChild(item);
    });

    inspectMemoryRecord(records[0]);
}

function renderMemorySearchResults(data) {
    const box = document.getElementById("memory-search-results");
    if (!box) return;

    box.innerHTML = "";

    if (!data || !data.selected_record) {
        box.textContent = data?.explanation || "No memory matched.";
        return;
    }

    const selected = data.selected_record;

    const title = document.createElement("div");
    title.className = "memory-record-title";
    title.textContent = selected.title || selected.record_id;

    const why = document.createElement("div");
    why.className = "memory-record-summary";
    why.textContent = selected.why_selected || data.explanation || "";

    const meta = document.createElement("div");
    meta.className = "memory-record-meta";
    meta.appendChild(memoryBadge(`score ${selected.rank_score}`));
    meta.appendChild(memoryBadge(selected.layer || "layer"));
    meta.appendChild(memoryBadge(selected.confidence || "confidence"));
    meta.appendChild(memoryBadge(selected.attach_recommendation || "attach?"));

    const tags = document.createElement("div");
    tags.className = "memory-record-source";
    tags.textContent = `Matched tags: ${(selected.matched_tags || []).join(", ") || "none"}`;

    box.appendChild(title);
    box.appendChild(meta);
    box.appendChild(why);
    box.appendChild(tags);

    inspectMemoryRecord(selected.record || selected, data.explanation || selected.why_selected);
}

async function refreshMemoryPanel() {
    try {
        const recordsResponse = await fetch(`${BACKEND_URL}/memory/records`);
        const recordsData = await recordsResponse.json();

        const reviewResponse = await fetch(`${BACKEND_URL}/memory/review/queue?include_closed=true`);
        const reviewData = await reviewResponse.json();

        renderMemoryHealth(recordsData.records || [], recordsData.summary || {}, reviewData.queue || []);
        renderMemoryLayerSummary(recordsData.summary || {});
        renderMemoryRecords(recordsData.records || []);
        renderMemoryReviewQueue(reviewData.queue || []);
    } catch (error) {
        console.error("Failed to refresh memory panel:", error);
        const layerBox = document.getElementById("memory-layer-summary");
        if (layerBox) layerBox.textContent = "Memory backend unavailable.";
    }
}

// --- End Technemachina Control Center Read-Only Memory Polish ---


// --- Technemachina Review Queue Controls v0.2.7d-2 ---

let selectedReviewItem = null;
let lastReviewDecisions = [];

function reviewStatusBadge(status) {
    return memoryBadge(status || "unknown");
}

function inspectReviewItem(item) {
    selectedReviewItem = item || null;

    const inspector = document.getElementById("review-inspector");
    const approveBtn = document.getElementById("review-approve-btn");
    const rejectBtn = document.getElementById("review-reject-btn");
    const deferBtn = document.getElementById("review-defer-btn");

    const isPending = item && item.review_status === "pending";

    [approveBtn, rejectBtn, deferBtn].forEach(btn => {
        if (btn) btn.disabled = !isPending;
    });

    if (!inspector) return;

    if (!item) {
        inspector.textContent = "Select a review item to inspect the candidate, provenance, and ruling options.";
        return;
    }

    const candidate = item.candidate_record || {};

    inspector.innerHTML = "";

    const title = document.createElement("div");
    title.className = "memory-inspector-title";
    title.textContent = item.title || item.review_id || "Untitled review item";

    const meta = document.createElement("div");
    meta.className = "memory-record-meta";
    meta.appendChild(reviewStatusBadge(item.review_status));
    meta.appendChild(memoryBadge(item.suggested_action || "action"));
    meta.appendChild(memoryBadge(item.layer || candidate.layer || "layer"));
    meta.appendChild(memoryBadge(item.confidence || candidate.confidence || "confidence"));
    meta.appendChild(memoryBadge(item.risk_level || candidate.risk_level || "risk"));

    const reason = document.createElement("div");
    reason.className = "memory-record-summary";
    reason.textContent = item.reason_for_review || "No review reason provided.";

    const source = document.createElement("div");
    source.className = "memory-inspector-line";
    source.textContent = `Source refs: ${(item.source_refs || [candidate.source_ref]).filter(Boolean).join(", ") || "unknown"}`;

    const provenance = document.createElement("div");
    provenance.className = "memory-inspector-line";
    provenance.textContent = `Provenance: ${item.provenance || candidate.provenance || "not provided"}`;

    const candidateBody = document.createElement("div");
    candidateBody.className = "memory-explain-box";
    candidateBody.textContent = candidate.body || item.summary || "No candidate body.";

    const ruling = document.createElement("div");
    ruling.className = "memory-inspector-line";
    ruling.textContent = isPending
        ? "Ruling available: approve, reject, or defer."
        : `Closed item: ${item.review_status}.`;

    inspector.appendChild(title);
    inspector.appendChild(meta);
    inspector.appendChild(reason);
    inspector.appendChild(source);
    inspector.appendChild(provenance);
    inspector.appendChild(candidateBody);
    inspector.appendChild(ruling);
}

function renderMemoryReviewQueue(queue) {
    const list = document.getElementById("memory-review-list");
    if (!list) return;

    list.innerHTML = "";

    if (!queue || queue.length === 0) {
        list.textContent = "No review items.";
        inspectReviewItem(null);
        return;
    }

    const sorted = [...queue].sort((a, b) => {
        if (a.review_status === "pending" && b.review_status !== "pending") return -1;
        if (a.review_status !== "pending" && b.review_status === "pending") return 1;
        return String(b.created_at || "").localeCompare(String(a.created_at || ""));
    });

    sorted.slice(0, 12).forEach(item => {
        const row = document.createElement("button");
        row.type = "button";
        row.className = "memory-review-item memory-clickable";

        const title = document.createElement("div");
        title.className = "memory-record-title";
        title.textContent = item.title || item.review_id || "Untitled review";

        const meta = document.createElement("div");
        meta.className = "memory-record-meta";
        meta.appendChild(reviewStatusBadge(item.review_status || "pending"));
        meta.appendChild(memoryBadge(item.suggested_action || "action"));
        meta.appendChild(memoryBadge(item.layer || "layer"));
        meta.appendChild(memoryBadge(item.confidence || "confidence"));

        const reason = document.createElement("div");
        reason.className = "memory-record-summary";
        reason.textContent = item.reason_for_review || "No reason provided.";

        const source = document.createElement("div");
        source.className = "memory-record-source";
        source.textContent = `Review ID: ${item.review_id}`;

        row.appendChild(title);
        row.appendChild(meta);
        row.appendChild(reason);
        row.appendChild(source);

        row.addEventListener("click", () => inspectReviewItem(item));

        list.appendChild(row);
    });

    const firstPending = sorted.find(item => item.review_status === "pending");
    inspectReviewItem(firstPending || sorted[0]);
}

function renderReviewDecisionLog(decisions) {
    const log = document.getElementById("review-decision-log");
    if (!log) return;

    log.innerHTML = "";

    if (!decisions || decisions.length === 0) {
        log.textContent = "No review decisions yet.";
        return;
    }

    decisions.slice(-8).reverse().forEach(decision => {
        const row = document.createElement("div");
        row.className = "review-decision-item";

        const title = document.createElement("div");
        title.className = "memory-record-title";
        title.textContent = `${decision.decision || "decision"} · ${decision.review_id || "unknown review"}`;

        const meta = document.createElement("div");
        meta.className = "memory-record-meta";
        meta.appendChild(memoryBadge(decision.reviewed_by || "reviewer"));
        meta.appendChild(memoryBadge(decision.record_id || "no record"));

        const notes = document.createElement("div");
        notes.className = "memory-record-summary";
        notes.textContent = decision.notes || "No notes.";

        const time = document.createElement("div");
        time.className = "memory-record-source";
        time.textContent = decision.reviewed_at || "";

        row.appendChild(title);
        row.appendChild(meta);
        row.appendChild(notes);
        row.appendChild(time);
        log.appendChild(row);
    });
}

async function loadReviewDecisionLog() {
    try {
        const response = await fetch(`${BACKEND_URL}/memory/review/decisions`);
        const data = await response.json();
        lastReviewDecisions = data.decisions || [];
        renderReviewDecisionLog(lastReviewDecisions);
    } catch (error) {
        console.error("Failed to load review decisions:", error);
        const log = document.getElementById("review-decision-log");
        if (log) log.textContent = "Could not load decision log.";
    }
}

async function submitReviewDecision(decision) {
    if (!selectedReviewItem || !selectedReviewItem.review_id) {
        alert("No review item selected.");
        return;
    }

    if (selectedReviewItem.review_status !== "pending") {
        alert("This review item is already closed.");
        return;
    }

    const label = decision.charAt(0).toUpperCase() + decision.slice(1);
    const notes = prompt(`${label} notes for this review item:`, `${label} by Oracle from Control Center.`);
    if (notes === null) return;

    try {
        const response = await fetch(`${BACKEND_URL}/memory/review/${selectedReviewItem.review_id}/${decision}`, {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({
                reviewed_by: "Oracle",
                notes: notes
            })
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.detail || JSON.stringify(data));
        }

        await refreshMemoryPanel();
        await loadReviewDecisionLog();
    } catch (error) {
        console.error(`Review ${decision} failed:`, error);
        alert(`Review ${decision} failed: ${error.message}`);
    }
}

function initReviewControls() {
    const approveBtn = document.getElementById("review-approve-btn");
    const rejectBtn = document.getElementById("review-reject-btn");
    const deferBtn = document.getElementById("review-defer-btn");

    if (approveBtn) approveBtn.addEventListener("click", () => submitReviewDecision("approve"));
    if (rejectBtn) rejectBtn.addEventListener("click", () => submitReviewDecision("reject"));
    if (deferBtn) deferBtn.addEventListener("click", () => submitReviewDecision("defer"));

    loadReviewDecisionLog();
}

// Patch refreshMemoryPanel so decision log stays current.
const previousRefreshMemoryPanelForReviewControls = refreshMemoryPanel;
refreshMemoryPanel = async function() {
    await previousRefreshMemoryPanelForReviewControls();
    await loadReviewDecisionLog();
};

// --- End Technemachina Review Queue Controls ---



// --- Technemachina Review Button Wiring Repair v0.2.7d-2a ---

function bindReviewControlButtonsRepair() {
    const buttons = [
        ["review-approve-btn", "approve"],
        ["review-reject-btn", "reject"],
        ["review-defer-btn", "defer"],
    ];

    buttons.forEach(([buttonId, decision]) => {
        const button = document.getElementById(buttonId);
        if (!button || button.dataset.reviewRepairBound === "true") return;

        button.dataset.reviewRepairBound = "true";

        button.addEventListener("click", async event => {
            event.preventDefault();
            event.stopPropagation();

            if (button.disabled) {
                alert("Select a pending review item first.");
                return;
            }

            if (typeof submitReviewDecision !== "function") {
                alert("Review decision function is not available.");
                return;
            }

            await submitReviewDecision(decision);
        });
    });
}

window.addEventListener("DOMContentLoaded", () => {
    bindReviewControlButtonsRepair();
});

setTimeout(bindReviewControlButtonsRepair, 500);
setTimeout(bindReviewControlButtonsRepair, 1500);

// --- End Technemachina Review Button Wiring Repair ---



// --- Technemachina Review Queue Real Buttons v0.2.7d-2b ---

function renderMemoryReviewQueue(queue) {
    const list = document.getElementById("memory-review-list");
    if (!list) return;

    list.innerHTML = "";

    if (!queue || queue.length === 0) {
        list.textContent = "No review items.";
        inspectReviewItem(null);
        return;
    }

    const sorted = [...queue].sort((a, b) => {
        if (a.review_status === "pending" && b.review_status !== "pending") return -1;
        if (a.review_status !== "pending" && b.review_status === "pending") return 1;
        return String(b.created_at || "").localeCompare(String(a.created_at || ""));
    });

    sorted.slice(0, 12).forEach(item => {
        const row = document.createElement("div");
        row.className = "memory-review-item review-case-card";
        row.dataset.reviewId = item.review_id || "";

        const title = document.createElement("div");
        title.className = "memory-record-title";
        title.textContent = item.title || item.review_id || "Untitled review";

        const meta = document.createElement("div");
        meta.className = "memory-record-meta";
        meta.appendChild(reviewStatusBadge(item.review_status || "pending"));
        meta.appendChild(memoryBadge(item.suggested_action || "action"));
        meta.appendChild(memoryBadge(item.layer || "layer"));
        meta.appendChild(memoryBadge(item.confidence || "confidence"));

        const reason = document.createElement("div");
        reason.className = "memory-record-summary";
        reason.textContent = item.reason_for_review || "No reason provided.";

        const source = document.createElement("div");
        source.className = "memory-record-source";
        source.textContent = `Review ID: ${item.review_id}`;

        const buttonRow = document.createElement("div");
        buttonRow.className = "review-case-button-row";

        const selectButton = document.createElement("button");
        selectButton.type = "button";
        selectButton.className = "review-real-button review-select-button";
        selectButton.textContent = "Select Case";
        selectButton.addEventListener("click", event => {
            event.preventDefault();
            event.stopPropagation();
            inspectReviewItem(item);
            document.querySelectorAll(".review-case-card").forEach(card => card.classList.remove("selected"));
            row.classList.add("selected");
        });

        buttonRow.appendChild(selectButton);

        if (item.review_status === "pending") {
            ["approve", "reject", "defer"].forEach(decision => {
                const actionButton = document.createElement("button");
                actionButton.type = "button";
                actionButton.className = `review-real-button review-${decision}-button`;
                actionButton.textContent = decision.toUpperCase();

                actionButton.addEventListener("click", async event => {
                    event.preventDefault();
                    event.stopPropagation();

                    selectedReviewItem = item;
                    inspectReviewItem(item);

                    await submitReviewDecision(decision);
                });

                buttonRow.appendChild(actionButton);
            });
        } else {
            const closed = document.createElement("span");
            closed.className = "review-closed-label";
            closed.textContent = `Closed: ${item.review_status}`;
            buttonRow.appendChild(closed);
        }

        row.addEventListener("click", () => {
            inspectReviewItem(item);
            document.querySelectorAll(".review-case-card").forEach(card => card.classList.remove("selected"));
            row.classList.add("selected");
        });

        row.appendChild(title);
        row.appendChild(meta);
        row.appendChild(reason);
        row.appendChild(source);
        row.appendChild(buttonRow);

        list.appendChild(row);
    });

    const firstPending = sorted.find(item => item.review_status === "pending");
    inspectReviewItem(firstPending || sorted[0]);
}

// --- End Technemachina Review Queue Real Buttons ---



// --- Technemachina Candidate Triage Desk v0.2.7e-1 ---

let selectedMemoryCandidate = null;

function ensureCandidatePanel() {
    if (document.getElementById("candidate-panel")) return;

    const controlPage = document.getElementById("control-center-page");
    const memoryPanel = document.getElementById("memory-panel");
    if (!controlPage || !memoryPanel) return;

    const panel = document.createElement("section");
    panel.id = "candidate-panel";
    panel.className = "candidate-panel";

    panel.innerHTML = `
        <div class="candidate-panel-header">
            <div>
                <h3>Candidate Triage Desk</h3>
                <p>Thread moments become candidates here. Candidates can be enqueued for review, but never written directly to durable memory.</p>
            </div>
            <div class="candidate-action-cluster">
                <button id="refresh-candidates-btn" type="button">Refresh Candidates</button>
                <button id="generate-candidates-btn" type="button">Generate From Active Thread</button>
            </div>
        </div>

        <div id="candidate-health-strip" class="candidate-health-strip">Candidate status loading...</div>

        <div class="candidate-grid">
            <div class="candidate-card">
                <h4>Candidate List</h4>
                <div id="candidate-list" class="candidate-list">Candidates loading...</div>
            </div>

            <div class="candidate-card">
                <h4>Evidence Inspector</h4>
                <div id="candidate-inspector" class="candidate-inspector">Select a candidate to inspect evidence, provenance, and extraction rationale.</div>
            </div>

            <div class="candidate-card">
                <h4>Queue Action Panel</h4>
                <div id="candidate-action-panel" class="candidate-inspector">Select a candidate that is not already enqueued.</div>
                <button id="enqueue-candidate-btn" type="button" disabled>Enqueue to Review Queue</button>
            </div>
        </div>
    `;

    memoryPanel.insertAdjacentElement("afterend", panel);
}

function renderCandidateHealth(status) {
    const strip = document.getElementById("candidate-health-strip");
    if (!strip) return;

    const counts = status?.counts || {};
    const total = status?.total_candidates ?? 0;

    strip.innerHTML = "";

    [
        ["Total Candidates", total],
        ["Candidate", counts.candidate || 0],
        ["Enqueued", counts.enqueued || 0],
        ["Deferred", counts.deferred || 0],
    ].forEach(([label, value]) => {
        const card = document.createElement("div");
        card.className = "candidate-health-card";

        const valueNode = document.createElement("div");
        valueNode.className = "candidate-health-value";
        valueNode.textContent = value;

        const labelNode = document.createElement("div");
        labelNode.className = "candidate-health-label";
        labelNode.textContent = label;

        card.appendChild(valueNode);
        card.appendChild(labelNode);
        strip.appendChild(card);
    });
}

function inspectMemoryCandidate(candidate) {
    selectedMemoryCandidate = candidate || null;

    const inspector = document.getElementById("candidate-inspector");
    const actionPanel = document.getElementById("candidate-action-panel");
    const enqueueBtn = document.getElementById("enqueue-candidate-btn");

    const canEnqueue = candidate && ["candidate", "deferred"].includes(candidate.review_status || "candidate");

    if (enqueueBtn) enqueueBtn.disabled = !canEnqueue;

    if (!candidate) {
        if (inspector) inspector.textContent = "Select a candidate to inspect evidence, provenance, and extraction rationale.";
        if (actionPanel) actionPanel.textContent = "Select a candidate that is not already enqueued.";
        return;
    }

    if (inspector) {
        inspector.innerHTML = "";

        const title = document.createElement("div");
        title.className = "candidate-title";
        title.textContent = candidate.title || candidate.candidate_id || "Untitled candidate";

        const meta = document.createElement("div");
        meta.className = "memory-record-meta";
        meta.appendChild(memoryBadge(candidate.review_status || "candidate"));
        meta.appendChild(memoryBadge(candidate.record_type || "type"));
        meta.appendChild(memoryBadge(candidate.layer_suggested || candidate.layer || "layer"));
        meta.appendChild(memoryBadge(candidate.confidence || "confidence"));

        const why = document.createElement("div");
        why.className = "candidate-explain-box";
        why.textContent = candidate.why_candidate || "No extraction rationale provided.";

        const excerpt = document.createElement("div");
        excerpt.className = "candidate-excerpt";
        excerpt.textContent = candidate.source_excerpt || candidate.summary || candidate.body || "";

        const source = document.createElement("div");
        source.className = "candidate-line";
        source.textContent = `Thread: ${candidate.source_thread_id || "unknown"}`;

        const messages = document.createElement("div");
        messages.className = "candidate-line";
        messages.textContent = `Message IDs: ${(candidate.source_message_ids || []).join(", ") || "none"}`;

        const provenance = document.createElement("div");
        provenance.className = "candidate-line";
        provenance.textContent = `Provenance: ${candidate.provenance || "not provided"}`;

        const tags = document.createElement("div");
        tags.className = "candidate-line";
        tags.textContent = `Tags: ${(candidate.matched_tags || candidate.tags || []).join(", ") || "none"}`;

        inspector.appendChild(title);
        inspector.appendChild(meta);
        inspector.appendChild(why);
        inspector.appendChild(excerpt);
        inspector.appendChild(source);
        inspector.appendChild(messages);
        inspector.appendChild(provenance);
        inspector.appendChild(tags);
    }

    if (actionPanel) {
        actionPanel.innerHTML = "";

        const summary = document.createElement("div");
        summary.className = "candidate-line";
        summary.textContent = canEnqueue
            ? "This candidate can be enqueued for Oracle review. It will not become durable memory unless approved in the Review Queue."
            : `This candidate is already ${candidate.review_status}.`;

        const id = document.createElement("div");
        id.className = "candidate-id-line";
        id.textContent = candidate.candidate_id || "unknown candidate";

        actionPanel.appendChild(summary);
        actionPanel.appendChild(id);
    }
}

function renderCandidateList(candidates) {
    const list = document.getElementById("candidate-list");
    if (!list) return;

    list.innerHTML = "";

    if (!candidates || candidates.length === 0) {
        list.textContent = "No memory candidates.";
        inspectMemoryCandidate(null);
        return;
    }

    candidates.slice().reverse().slice(0, 16).forEach(candidate => {
        const card = document.createElement("div");
        card.className = "candidate-list-item";
        card.dataset.candidateId = candidate.candidate_id || "";

        const title = document.createElement("div");
        title.className = "memory-record-title";
        title.textContent = candidate.title || candidate.candidate_id || "Untitled candidate";

        const meta = document.createElement("div");
        meta.className = "memory-record-meta";
        meta.appendChild(memoryBadge(candidate.review_status || "candidate"));
        meta.appendChild(memoryBadge(candidate.record_type || "type"));
        meta.appendChild(memoryBadge(candidate.layer_suggested || candidate.layer || "layer"));
        meta.appendChild(memoryBadge(candidate.confidence || "confidence"));

        const summary = document.createElement("div");
        summary.className = "memory-record-summary";
        summary.textContent = candidate.summary || candidate.source_excerpt || "";

        const source = document.createElement("div");
        source.className = "memory-record-source";
        source.textContent = candidate.candidate_id || "";

        card.appendChild(title);
        card.appendChild(meta);
        card.appendChild(summary);
        card.appendChild(source);

        card.addEventListener("click", () => {
            document.querySelectorAll(".candidate-list-item").forEach(item => item.classList.remove("selected"));
            card.classList.add("selected");
            inspectMemoryCandidate(candidate);
        });

        list.appendChild(card);
    });

    inspectMemoryCandidate(candidates[candidates.length - 1]);
}

async function refreshCandidatePanel() {
    ensureCandidatePanel();

    try {
        const response = await fetch(`${BACKEND_URL}/memory/candidates`);
        const data = await response.json();

        renderCandidateHealth(data.status || {});
        renderCandidateList(data.candidates || []);
    } catch (error) {
        console.error("Failed to refresh candidate panel:", error);

        const list = document.getElementById("candidate-list");
        if (list) list.textContent = "Could not load candidates.";

        const strip = document.getElementById("candidate-health-strip");
        if (strip) strip.textContent = "Candidate backend unavailable.";
    }
}

async function generateCandidatesFromActiveThread() {
    try {
        const response = await fetch(`${BACKEND_URL}/memory/candidates/from-thread?limit=40`, {
            method: "POST"
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.detail || JSON.stringify(data));
        }

        await refreshCandidatePanel();

        alert(`Candidate extraction complete. New candidates: ${data.candidate_count ?? 0}`);
    } catch (error) {
        console.error("Candidate generation failed:", error);
        alert(`Candidate generation failed: ${error.message}`);
    }
}

async function enqueueSelectedCandidate() {
    if (!selectedMemoryCandidate || !selectedMemoryCandidate.candidate_id) {
        alert("No candidate selected.");
        return;
    }

    if (!["candidate", "deferred"].includes(selectedMemoryCandidate.review_status || "candidate")) {
        alert(`Candidate is already ${selectedMemoryCandidate.review_status}.`);
        return;
    }

    const notes = prompt(
        "Enqueue notes:",
        "Enqueue candidate to Review Queue from Control Center."
    );

    if (notes === null) return;

    try {
        const response = await fetch(
            `${BACKEND_URL}/memory/candidates/${selectedMemoryCandidate.candidate_id}/enqueue?reviewed_by=Oracle&notes=${encodeURIComponent(notes)}`,
            { method: "POST" }
        );

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.detail || JSON.stringify(data));
        }

        await refreshCandidatePanel();

        if (typeof refreshMemoryPanel === "function") {
            await refreshMemoryPanel();
        }

        alert("Candidate enqueued to Review Queue.");
    } catch (error) {
        console.error("Candidate enqueue failed:", error);
        alert(`Candidate enqueue failed: ${error.message}`);
    }
}

function initCandidatePanel() {
    ensureCandidatePanel();

    const refreshBtn = document.getElementById("refresh-candidates-btn");
    const generateBtn = document.getElementById("generate-candidates-btn");
    const enqueueBtn = document.getElementById("enqueue-candidate-btn");

    if (refreshBtn && refreshBtn.dataset.bound !== "true") {
        refreshBtn.dataset.bound = "true";
        refreshBtn.addEventListener("click", refreshCandidatePanel);
    }

    if (generateBtn && generateBtn.dataset.bound !== "true") {
        generateBtn.dataset.bound = "true";
        generateBtn.addEventListener("click", generateCandidatesFromActiveThread);
    }

    if (enqueueBtn && enqueueBtn.dataset.bound !== "true") {
        enqueueBtn.dataset.bound = "true";
        enqueueBtn.addEventListener("click", enqueueSelectedCandidate);
    }

    refreshCandidatePanel();
}

window.addEventListener("DOMContentLoaded", () => {
    initCandidatePanel();
});

setTimeout(initCandidatePanel, 600);

// Patch mode switching so candidates refresh when Control Center opens.
if (typeof setAppMode === "function" && !window.__candidateModePatchApplied) {
    window.__candidateModePatchApplied = true;
    const previousSetAppModeForCandidates = setAppMode;
    setAppMode = function(mode) {
        previousSetAppModeForCandidates(mode);
        if (mode === "control") {
            refreshCandidatePanel();
        }
    };
}

// --- End Technemachina Candidate Triage Desk ---



// --- Technemachina Candidate UI Refinement v0.2.7e-1b ---

function candidateCanEnqueue(candidate) {
    if (!candidate) return false;
    return ["candidate", "deferred"].includes(candidate.review_status || "candidate");
}

function candidateStatusText(candidate) {
    if (!candidate) return "No candidate selected.";

    const status = candidate.review_status || "candidate";

    if (status === "candidate") {
        return "Ready for triage. This candidate can be enqueued to the Review Queue.";
    }

    if (status === "enqueued") {
        return "Already enqueued. This candidate is now governed by the Review Queue.";
    }

    if (status === "approved") {
        return "Approved. Durable memory may already exist through the Review Queue.";
    }

    if (status === "deferred") {
        return "Deferred. This candidate can be reconsidered later.";
    }

    return `Current status: ${status}.`;
}

// Override inspector with clearer enqueue state.
const previousInspectMemoryCandidateRefinement = inspectMemoryCandidate;

inspectMemoryCandidate = function(candidate) {
    previousInspectMemoryCandidateRefinement(candidate);

    const enqueueBtn = document.getElementById("enqueue-candidate-btn");
    const actionPanel = document.getElementById("candidate-action-panel");

    const canEnqueue = candidateCanEnqueue(candidate);

    if (enqueueBtn) {
        enqueueBtn.disabled = !canEnqueue;
        enqueueBtn.classList.toggle("candidate-disabled-action", !canEnqueue);
        enqueueBtn.textContent = canEnqueue ? "Enqueue to Review Queue" : "Already Governed";
    }

    if (actionPanel && candidate) {
        const statusBox = document.createElement("div");
        statusBox.className = canEnqueue ? "candidate-ready-box" : "candidate-governed-box";
        statusBox.textContent = candidateStatusText(candidate);
        actionPanel.appendChild(statusBox);
    }
};

// Patch enqueue function with stricter guard.
const previousEnqueueSelectedCandidateRefinement = enqueueSelectedCandidate;

enqueueSelectedCandidate = async function() {
    if (!candidateCanEnqueue(selectedMemoryCandidate)) {
        alert(candidateStatusText(selectedMemoryCandidate));
        return;
    }

    return previousEnqueueSelectedCandidateRefinement();
};

// --- End Technemachina Candidate UI Refinement ---



// --- Technemachina Control Center Mini-Tabs Layout v0.2.8c-2 ---

let controlCenterTabsInitialized = false;

const CONTROL_CENTER_TABS = [
    ["overview", "Overview"],
    ["memory", "Memory"],
    ["reviews", "Reviews"],
    ["thread-candidates", "Thread Candidates"],
    ["knowledge-candidates", "Knowledge Candidates"],
    ["decisions", "Decisions"],
    ["system", "System"],
];

function ccSafeText(value, fallback = "—") {
    if (value === undefined || value === null || value === "") return fallback;
    return String(value);
}

function ccCreateMetric(label, value, hint = "") {
    const card = document.createElement("div");
    card.className = "cc-metric-card";

    const valueNode = document.createElement("div");
    valueNode.className = "cc-metric-value";
    valueNode.textContent = ccSafeText(value);

    const labelNode = document.createElement("div");
    labelNode.className = "cc-metric-label";
    labelNode.textContent = label;

    card.appendChild(valueNode);
    card.appendChild(labelNode);

    if (hint) {
        const hintNode = document.createElement("div");
        hintNode.className = "cc-metric-hint";
        hintNode.textContent = hint;
        card.appendChild(hintNode);
    }

    return card;
}

function ccPanel(tabName) {
    return document.getElementById(`cc-tab-${tabName}`);
}

function setControlCenterTab(tabName) {
    const valid = CONTROL_CENTER_TABS.some(([key]) => key === tabName);
    const nextTab = valid ? tabName : "overview";

    document.querySelectorAll(".cc-tab-btn").forEach(button => {
        button.classList.toggle("active", button.dataset.ccTab === nextTab);
    });

    document.querySelectorAll(".cc-tab-panel").forEach(panel => {
        panel.classList.toggle("active", panel.dataset.ccPanel === nextTab);
    });

    localStorage.setItem("technemachina_control_center_tab", nextTab);

    if (nextTab === "overview") refreshControlCenterOverview();
    if (nextTab === "knowledge-candidates") refreshKnowledgeCandidateTab();
    if (nextTab === "system") refreshControlCenterSystemTab();
}

function ccMoveCardContaining(elementId, targetPanel) {
    const element = document.getElementById(elementId);
    if (!element || !targetPanel) return;

    const card =
        element.closest(".memory-card") ||
        element.closest(".candidate-card") ||
        element.closest(".memory-section") ||
        element;

    targetPanel.appendChild(card);
}

function ensureControlCenterMiniTabs() {
    if (controlCenterTabsInitialized) return;

    const controlPage = document.getElementById("control-center-page");
    const memoryPanel = document.getElementById("memory-panel");

    if (!controlPage || !memoryPanel) return;

    // Candidate panel must be created before moving memoryPanel, because the older
    // creator inserts relative to memoryPanel.
    if (!document.getElementById("candidate-panel") && typeof ensureCandidatePanel === "function") {
        try {
            ensureCandidatePanel();
        } catch (error) {
            console.warn("Candidate panel pre-create failed:", error);
        }
    }

    const header = controlPage.querySelector(".control-center-header") || controlPage.firstElementChild;

    const shell = document.createElement("div");
    shell.id = "cc-mini-tabs-shell";
    shell.className = "cc-mini-tabs-shell";

    const tabRow = document.createElement("div");
    tabRow.id = "cc-tab-row";
    tabRow.className = "cc-tab-row";
    tabRow.setAttribute("role", "tablist");

    const panelWrap = document.createElement("div");
    panelWrap.id = "cc-tab-panels";
    panelWrap.className = "cc-tab-panels";

    CONTROL_CENTER_TABS.forEach(([key, label]) => {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "cc-tab-btn";
        button.dataset.ccTab = key;
        button.textContent = label;
        button.addEventListener("click", () => setControlCenterTab(key));
        tabRow.appendChild(button);

        const panel = document.createElement("section");
        panel.id = `cc-tab-${key}`;
        panel.className = "cc-tab-panel";
        panel.dataset.ccPanel = key;
        panel.setAttribute("aria-label", label);
        panelWrap.appendChild(panel);
    });

    shell.appendChild(tabRow);
    shell.appendChild(panelWrap);

    if (header && header.parentNode === controlPage) {
        header.insertAdjacentElement("afterend", shell);
    } else {
        controlPage.insertBefore(shell, controlPage.firstChild);
    }

    buildControlCenterOverviewTab();
    buildKnowledgeCandidateTab();
    buildControlCenterSystemTab();

    const memoryTab = ccPanel("memory");
    const reviewsTab = ccPanel("reviews");
    const threadCandidateTab = ccPanel("thread-candidates");
    const decisionsTab = ccPanel("decisions");

    if (memoryTab) {
        memoryPanel.classList.add("cc-contained-panel");
        memoryTab.appendChild(memoryPanel);
    }

    if (reviewsTab) {
        const reviewsHeader = document.createElement("div");
        reviewsHeader.className = "cc-panel-heading";
        reviewsHeader.innerHTML = `
            <h3>Reviews</h3>
            <p>Review Queue and Review Inspector live here. Approval is still required before durable memory.</p>
        `;
        reviewsTab.appendChild(reviewsHeader);

        const reviewGrid = document.createElement("div");
        reviewGrid.className = "cc-split-grid";
        reviewsTab.appendChild(reviewGrid);

        ccMoveCardContaining("memory-review-list", reviewGrid);
        ccMoveCardContaining("review-inspector", reviewGrid);
    }

    if (decisionsTab) {
        const decisionsHeader = document.createElement("div");
        decisionsHeader.className = "cc-panel-heading";
        decisionsHeader.innerHTML = `
            <h3>Decisions</h3>
            <p>Decision Log for approvals, rejections, deferrals, and governance rulings.</p>
        `;
        decisionsTab.appendChild(decisionsHeader);

        const decisionGrid = document.createElement("div");
        decisionGrid.className = "cc-single-grid";
        decisionsTab.appendChild(decisionGrid);

        ccMoveCardContaining("review-decision-log", decisionGrid);
    }

    const candidatePanel = document.getElementById("candidate-panel");
    if (threadCandidateTab) {
        const threadHeader = document.createElement("div");
        threadHeader.className = "cc-panel-heading";
        threadHeader.innerHTML = `
            <h3>Thread Candidates</h3>
            <p>Candidate Triage Desk gets its own workspace. Thread moments can become candidates, but never durable memory directly.</p>
        `;
        threadCandidateTab.appendChild(threadHeader);

        if (candidatePanel) {
            candidatePanel.classList.add("cc-contained-panel");
            threadCandidateTab.appendChild(candidatePanel);
        }
    }

    controlCenterTabsInitialized = true;

    const savedTab = localStorage.getItem("technemachina_control_center_tab") || "overview";
    setControlCenterTab(savedTab);
}

function buildControlCenterOverviewTab() {
    const overview = ccPanel("overview");
    if (!overview || document.getElementById("cc-overview-content")) return;

    overview.innerHTML = `
        <div id="cc-overview-content">
            <div class="cc-panel-heading">
                <h3>Overview</h3>
                <p>Compact governance summary for the local daemon.</p>
            </div>

            <div id="cc-overview-metrics" class="cc-metric-strip">
                <div class="cc-loading-card">Overview loading...</div>
            </div>

            <div class="cc-overview-grid">
                <div class="cc-dashboard-card">
                    <h4>Governance Map</h4>
                    <p>Memory is durable. Reviews gate memory. Candidates are proposals. Knowledge is source-backed and searchable.</p>
                    <div class="cc-jump-row">
                        <button type="button" data-jump-tab="memory">Memory</button>
                        <button type="button" data-jump-tab="reviews">Reviews</button>
                        <button type="button" data-jump-tab="thread-candidates">Thread Candidates</button>
                        <button type="button" data-jump-tab="knowledge-candidates">Knowledge Candidates</button>
                    </div>
                </div>

                <div class="cc-dashboard-card">
                    <h4>Current Rule</h4>
                    <p>Knowledge and thread moments may create candidates. Durable memory still requires Oracle review.</p>
                </div>
            </div>
        </div>
    `;

    overview.querySelectorAll("[data-jump-tab]").forEach(button => {
        button.addEventListener("click", () => setControlCenterTab(button.dataset.jumpTab));
    });
}

async function refreshControlCenterOverview() {
    const strip = document.getElementById("cc-overview-metrics");
    if (!strip) return;

    strip.textContent = "";

    let memoryRecords = {};
    let reviewStatus = {};
    let threadCandidates = {};
    let knowledgeCandidates = {};
    let systemInfo = {};

    try {
        const [memoryRes, reviewRes, threadRes, knowledgeRes, systemRes] = await Promise.allSettled([
            fetch(`${BACKEND_URL}/memory/records`),
            fetch(`${BACKEND_URL}/memory/review/status`),
            fetch(`${BACKEND_URL}/memory/candidates/status`),
            fetch(`${BACKEND_URL}/knowledge/candidates/status`),
            fetch(`${BACKEND_URL}/system-info`),
        ]);

        if (memoryRes.status === "fulfilled") memoryRecords = await memoryRes.value.json();
        if (reviewRes.status === "fulfilled") reviewStatus = await reviewRes.value.json();
        if (threadRes.status === "fulfilled") threadCandidates = await threadRes.value.json();
        if (knowledgeRes.status === "fulfilled") knowledgeCandidates = await knowledgeRes.value.json();
        if (systemRes.status === "fulfilled") systemInfo = await systemRes.value.json();
    } catch (error) {
        console.warn("Overview refresh failed:", error);
    }

    const activeRecords = (memoryRecords.records || []).filter(item => item.status !== "revoked").length;
    const pendingReviews = reviewStatus.pending_count ?? reviewStatus.counts?.pending ?? "—";
    const threadCandidateCount = threadCandidates.total_candidates ?? threadCandidates.candidate_count ?? "—";
    const knowledgeCandidateCount = knowledgeCandidates.candidate_count ?? "—";
    const version = systemInfo.current_version || systemInfo.version || "—";

    strip.appendChild(ccCreateMetric("Active Records", activeRecords));
    strip.appendChild(ccCreateMetric("Pending Reviews", pendingReviews));
    strip.appendChild(ccCreateMetric("Thread Candidates", threadCandidateCount));
    strip.appendChild(ccCreateMetric("Knowledge Candidates", knowledgeCandidateCount));
    strip.appendChild(ccCreateMetric("Version", version));
}

function buildKnowledgeCandidateTab() {
    const panel = ccPanel("knowledge-candidates");
    if (!panel || document.getElementById("cc-knowledge-candidates-content")) return;

    panel.innerHTML = `
        <div id="cc-knowledge-candidates-content">
            <div class="cc-panel-heading">
                <h3>Knowledge Candidates</h3>
                <p>Current-state view for knowledge-to-candidate bridge. Read-only in this layout pass.</p>
                <button id="cc-refresh-knowledge-candidates" type="button">Refresh Knowledge Candidates</button>
            </div>

            <div id="cc-knowledge-candidate-metrics" class="cc-metric-strip">
                <div class="cc-loading-card">Knowledge candidate status loading...</div>
            </div>

            <div class="cc-dashboard-card">
                <h4>Bridge States</h4>
                <div id="cc-knowledge-bridge-list" class="cc-mini-table">No bridge status loaded.</div>
            </div>
        </div>
    `;

    const refresh = document.getElementById("cc-refresh-knowledge-candidates");
    if (refresh) refresh.addEventListener("click", refreshKnowledgeCandidateTab);
}

async function refreshKnowledgeCandidateTab() {
    const metrics = document.getElementById("cc-knowledge-candidate-metrics");
    const list = document.getElementById("cc-knowledge-bridge-list");
    if (!metrics || !list) return;

    metrics.textContent = "";
    list.textContent = "Loading bridge status...";

    try {
        const [candidateRes, bridgeRes] = await Promise.all([
            fetch(`${BACKEND_URL}/knowledge/candidates/status`),
            fetch(`${BACKEND_URL}/knowledge/candidates/bridge-status`),
        ]);

        const candidateStatus = await candidateRes.json();
        const bridgeStatus = await bridgeRes.json();

        metrics.appendChild(ccCreateMetric("Current Candidates", candidateStatus.candidate_count ?? "—"));
        metrics.appendChild(ccCreateMetric("Raw Events", candidateStatus.raw_candidate_event_count ?? "—"));
        metrics.appendChild(ccCreateMetric("Queued", candidateStatus.counts?.candidate_queued ?? 0));
        metrics.appendChild(ccCreateMetric("Knowledge Only", bridgeStatus.counts?.knowledge_only ?? 0));
        metrics.appendChild(ccCreateMetric("Duplicates", bridgeStatus.counts?.duplicate_records ?? 0));

        list.textContent = "";
        (bridgeStatus.record_states || []).forEach(item => {
            const row = document.createElement("div");
            row.className = "cc-mini-row";
            row.innerHTML = `
                <strong>${ccSafeText(item.title, "Untitled")}</strong>
                <span>${ccSafeText(item.bridge_state)}</span>
                <small>${ccSafeText(item.knowledge_record_id)}</small>
            `;
            list.appendChild(row);
        });

        if (!(bridgeStatus.record_states || []).length) {
            list.textContent = "No knowledge bridge states yet.";
        }
    } catch (error) {
        console.error("Knowledge candidate tab refresh failed:", error);
        list.textContent = "Could not load knowledge candidate status.";
    }
}

function buildControlCenterSystemTab() {
    const panel = ccPanel("system");
    if (!panel || document.getElementById("cc-system-content")) return;

    panel.innerHTML = `
        <div id="cc-system-content">
            <div class="cc-panel-heading">
                <h3>System</h3>
                <p>Read-only runtime, provider, and project context summary.</p>
                <button id="cc-refresh-system" type="button">Refresh System</button>
            </div>

            <div id="cc-system-metrics" class="cc-metric-strip">
                <div class="cc-loading-card">System status loading...</div>
            </div>

            <div class="cc-dashboard-card">
                <h4>Objective</h4>
                <p id="cc-system-objective">No system objective loaded.</p>
            </div>
        </div>
    `;

    const refresh = document.getElementById("cc-refresh-system");
    if (refresh) refresh.addEventListener("click", refreshControlCenterSystemTab);
}

async function refreshControlCenterSystemTab() {
    const metrics = document.getElementById("cc-system-metrics");
    const objective = document.getElementById("cc-system-objective");
    if (!metrics || !objective) return;

    metrics.textContent = "";

    try {
        const response = await fetch(`${BACKEND_URL}/system-info`);
        const data = await response.json();

        metrics.appendChild(ccCreateMetric("Version", data.current_version || data.version || "—"));
        metrics.appendChild(ccCreateMetric("Provider", data.active_provider || "—"));
        metrics.appendChild(ccCreateMetric("Status", data.status || data.project_status || "—"));

        objective.textContent = data.current_objective || "No objective available.";
    } catch (error) {
        console.error("System tab refresh failed:", error);
        objective.textContent = "Could not load system status.";
    }
}

function initControlCenterMiniTabsWhenReady() {
    setTimeout(ensureControlCenterMiniTabs, 100);
    setTimeout(ensureControlCenterMiniTabs, 600);
    setTimeout(ensureControlCenterMiniTabs, 1400);
}

document.addEventListener("DOMContentLoaded", initControlCenterMiniTabsWhenReady);

document.querySelectorAll(".mode-btn").forEach(button => {
    button.addEventListener("click", () => {
        setTimeout(ensureControlCenterMiniTabs, 150);
    });
});

if (typeof setAppMode === "function") {
    const previousSetAppModeForControlCenterTabs = setAppMode;
    setAppMode = function(mode) {
        previousSetAppModeForControlCenterTabs(mode);
        if (mode === "control") {
            setTimeout(ensureControlCenterMiniTabs, 150);
        }
    };
}

// --- End Technemachina Control Center Mini-Tabs Layout ---


// --- Technemachina Synapse Map Frontend / Constellation Renderer v0.2.9c ---

window.__synapseMapState = {
    map: null,
    selected: null,
    hover: null,
    positions: new Map(),
    animationFrame: null,
};

function ensureSynapseModeInstalled() {
    const synapseButton = document.getElementById("mode-synapse-btn");
    const synapsePage = document.getElementById("synapse-map-page");

    if (!synapseButton || !synapsePage) return;

    synapseButton.addEventListener("click", () => {
        if (typeof setAppMode === "function") {
            setAppMode("synapse");
        } else {
            activateSynapseModeFallback();
        }
        loadSynapseMap();
    });

    const refreshButton = document.getElementById("synapse-refresh-btn");
    if (refreshButton) {
        refreshButton.addEventListener("click", loadSynapseMap);
    }

    if (typeof setAppMode === "function" && !window.__synapseModePatchApplied) {
        window.__synapseModePatchApplied = true;
        const previousSetAppModeForSynapse = setAppMode;

        setAppMode = function(mode) {
            if (mode === "synapse") {
                document.querySelectorAll(".mode-btn").forEach(btn => btn.classList.remove("active"));
                document.querySelectorAll(".mode-page").forEach(page => page.classList.remove("active"));

                const btn = document.getElementById("mode-synapse-btn");
                const page = document.getElementById("synapse-map-page");

                if (btn) btn.classList.add("active");
                if (page) page.classList.add("active");

                localStorage.setItem("technemachina_mode", "synapse");
                requestAnimationFrame(resizeSynapseCanvas);
                return;
            }

            previousSetAppModeForSynapse(mode);

            const page = document.getElementById("synapse-map-page");
            const btn = document.getElementById("mode-synapse-btn");
            if (page) page.classList.remove("active");
            if (btn) btn.classList.remove("active");
        };
    }
}

function activateSynapseModeFallback() {
    document.querySelectorAll(".mode-btn").forEach(btn => btn.classList.remove("active"));
    document.querySelectorAll(".mode-page").forEach(page => page.classList.remove("active"));

    const btn = document.getElementById("mode-synapse-btn");
    const page = document.getElementById("synapse-map-page");

    if (btn) btn.classList.add("active");
    if (page) page.classList.add("active");
}

async function loadSynapseMap() {
    const title = document.getElementById("synapse-inspector-title");
    const subtitle = document.getElementById("synapse-inspector-subtitle");

    try {
        if (title) title.textContent = "Loading constellation…";
        if (subtitle) subtitle.textContent = "Reading Synapse Map without mutation.";

        const response = await fetch("http://127.0.0.1:8000/synapse/map");
        const map = await response.json();

        window.__synapseMapState.map = map;
        window.__synapseMapState.selected = null;
        prepareSynapseLayout(map);
        updateSynapseStatus(map);
        updateSynapseInspector(null);
        resizeSynapseCanvas();
        drawSynapseMap();

    } catch (error) {
        if (title) title.textContent = "Synapse Map unavailable";
        if (subtitle) subtitle.textContent = String(error);
    }
}

function updateSynapseStatus(map) {
    const version = document.getElementById("synapse-version-pill");
    const nodes = document.getElementById("synapse-node-count-pill");
    const edges = document.getElementById("synapse-edge-count-pill");
    const readonly = document.getElementById("synapse-readonly-pill");

    if (version) version.textContent = `Version: ${map?.meta?.synapse_version || "—"}`;
    if (nodes) nodes.textContent = `Nodes: ${map?.meta?.node_count ?? map?.nodes?.length ?? "—"}`;
    if (edges) edges.textContent = `Edges: ${map?.meta?.edge_count ?? map?.edges?.length ?? "—"}`;
    if (readonly) readonly.textContent = `Read-only: ${map?.meta?.read_only === true ? "true" : "unknown"}`;
}

function synapseNodeColor(type, status) {
    if (type === "memory_record") return "rgba(235, 240, 255, 0.95)";
    if (type === "memory_layer") return "rgba(255, 255, 255, 0.75)";
    if (type === "knowledge_record") return "rgba(155, 205, 255, 0.95)";
    if (type === "knowledge_source") return "rgba(190, 225, 255, 0.9)";
    if (type === "thread_candidate") return "rgba(190, 130, 255, 0.95)";
    if (type === "knowledge_candidate") return "rgba(120, 220, 255, 0.95)";
    if (type === "review_item") return status === "pending" ? "rgba(255, 190, 80, 0.98)" : "rgba(210, 165, 90, 0.82)";
    if (type === "review_decision") return status === "approved" ? "rgba(255, 230, 150, 0.98)" : "rgba(180, 155, 125, 0.78)";
    if (type === "thread") return "rgba(120, 145, 180, 0.75)";
    if (type === "project_context") return "rgba(255, 235, 180, 0.98)";
    if (type === "doctrine") return "rgba(255, 255, 255, 1)";
    return "rgba(220, 225, 255, 0.85)";
}

function prepareSynapseLayout(map) {
    const canvas = document.getElementById("synapse-canvas");
    if (!canvas || !map || !Array.isArray(map.nodes)) return;

    const rect = canvas.getBoundingClientRect();
    const width = rect.width || 900;
    const height = rect.height || 560;
    const centerX = width / 2;
    const centerY = height / 2;

    const positions = new Map();
    const nodes = map.nodes;
    const count = Math.max(nodes.length, 1);

    nodes.forEach((node, index) => {
        const ring = 90 + (index % 4) * 70;
        const angle = (Math.PI * 2 * index) / count;
        const jitter = ((index * 37) % 31) - 15;

        let x = centerX + Math.cos(angle) * (ring + jitter);
        let y = centerY + Math.sin(angle) * (ring + jitter);

        if (node.type === "project_context" || node.type === "doctrine") {
            x = centerX + (node.type === "doctrine" ? 42 : -42);
            y = centerY;
        }

        positions.set(node.id, {
            x,
            y,
            radius: 3.5 + Math.max(0.5, Number(node.weight || 0.5)) * 5,
        });
    });

    window.__synapseMapState.positions = positions;
}

function resizeSynapseCanvas() {
    const canvas = document.getElementById("synapse-canvas");
    if (!canvas) return;

    const rect = canvas.getBoundingClientRect();
    const scale = window.devicePixelRatio || 1;

    canvas.width = Math.max(1, Math.floor(rect.width * scale));
    canvas.height = Math.max(1, Math.floor(rect.height * scale));

    const ctx = canvas.getContext("2d");
    if (ctx) ctx.setTransform(scale, 0, 0, scale, 0, 0);

    const map = window.__synapseMapState.map;
    if (map) {
        prepareSynapseLayout(map);
        drawSynapseMap();
    }
}

function drawSynapseMap() {
    const canvas = document.getElementById("synapse-canvas");
    const map = window.__synapseMapState.map;
    if (!canvas || !map) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const rect = canvas.getBoundingClientRect();
    const width = rect.width;
    const height = rect.height;
    const positions = window.__synapseMapState.positions;
    const selected = window.__synapseMapState.selected;

    ctx.clearRect(0, 0, width, height);

    const gradient = ctx.createRadialGradient(width / 2, height / 2, 30, width / 2, height / 2, Math.max(width, height));
    gradient.addColorStop(0, "rgba(22, 26, 44, 1)");
    gradient.addColorStop(1, "rgba(2, 4, 12, 1)");
    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, width, height);

    const selectedId = selected?.kind === "node" ? selected.item.id : null;
    const connectedIds = new Set();

    if (selectedId) {
        (map.edges || []).forEach(edge => {
            if (edge.source === selectedId || edge.target === selectedId) {
                connectedIds.add(edge.source);
                connectedIds.add(edge.target);
            }
        });
    }

    (map.edges || []).forEach(edge => {
        const a = positions.get(edge.source);
        const b = positions.get(edge.target);
        if (!a || !b) return;

        const isSelectedPath = selectedId && (edge.source === selectedId || edge.target === selectedId);
        const alpha = selectedId ? (isSelectedPath ? 0.82 : 0.12) : 0.28;
        const widthLine = isSelectedPath ? 1.8 : 0.85;

        ctx.beginPath();
        ctx.moveTo(a.x, a.y);
        ctx.lineTo(b.x, b.y);
        ctx.lineWidth = widthLine;
        ctx.strokeStyle = `rgba(185, 210, 255, ${alpha})`;
        ctx.shadowColor = `rgba(150, 190, 255, ${alpha})`;
        ctx.shadowBlur = isSelectedPath ? 12 : 4;
        ctx.stroke();
        ctx.shadowBlur = 0;
    });

    (map.nodes || []).forEach(node => {
        const p = positions.get(node.id);
        if (!p) return;

        const isSelected = selectedId === node.id;
        const isConnected = connectedIds.has(node.id);
        const dimmed = selectedId && !isSelected && !isConnected;
        const salience = Number(node?.skin?.salience || node.weight || 0.5);
        const radius = p.radius * (isSelected ? 1.55 : 1);
        const color = synapseNodeColor(node.type, node.status);

        ctx.globalAlpha = dimmed ? 0.22 : 1;

        ctx.beginPath();
        ctx.arc(p.x, p.y, radius + 9 + salience * 8, 0, Math.PI * 2);
        ctx.fillStyle = color.replace(/[\d.]+\)$/g, dimmed ? "0.08)" : isSelected ? "0.28)" : "0.14)");
        ctx.shadowColor = color;
        ctx.shadowBlur = isSelected ? 26 : 13;
        ctx.fill();

        ctx.beginPath();
        ctx.arc(p.x, p.y, radius, 0, Math.PI * 2);
        ctx.fillStyle = color;
        ctx.shadowBlur = isSelected ? 18 : 8;
        ctx.fill();

        if (isSelected || (!selectedId && (node.type === "project_context" || node.type === "doctrine"))) {
            ctx.font = "12px system-ui, -apple-system, BlinkMacSystemFont, sans-serif";
            ctx.fillStyle = "rgba(245, 247, 255, 0.9)";
            ctx.shadowBlur = 0;
            ctx.fillText(String(node.label || node.id).slice(0, 42), p.x + 12, p.y - 10);
        }

        ctx.globalAlpha = 1;
        ctx.shadowBlur = 0;
    });
}

function updateSynapseInspector(selection) {
    const title = document.getElementById("synapse-inspector-title");
    const subtitle = document.getElementById("synapse-inspector-subtitle");
    const jsonBlock = document.getElementById("synapse-inspector-json");

    if (!selection) {
        if (title) title.textContent = "Select a star";
        if (subtitle) subtitle.textContent = "Click a node or relation to inspect it. This surface is read-only.";
        if (jsonBlock) jsonBlock.textContent = "{}";
        return;
    }

    if (title) title.textContent = selection.item.label || selection.item.id || "Selected item";
    if (subtitle) subtitle.textContent = `${selection.kind} • ${selection.item.type || selection.item.status || "synapse"}`;
    if (jsonBlock) jsonBlock.textContent = JSON.stringify(selection.item, null, 2);
}

function handleSynapseCanvasClick(event) {
    const canvas = document.getElementById("synapse-canvas");
    const map = window.__synapseMapState.map;
    if (!canvas || !map) return;

    const rect = canvas.getBoundingClientRect();
    const x = event.clientX - rect.left;
    const y = event.clientY - rect.top;
    const positions = window.__synapseMapState.positions;

    let hit = null;

    for (const node of map.nodes || []) {
        const p = positions.get(node.id);
        if (!p) continue;

        const dx = x - p.x;
        const dy = y - p.y;
        const distance = Math.sqrt(dx * dx + dy * dy);

        if (distance <= p.radius + 10) {
            hit = node;
            break;
        }
    }

    if (hit) {
        window.__synapseMapState.selected = { kind: "node", item: hit };
        updateSynapseInspector(window.__synapseMapState.selected);
        drawSynapseMap();
    }
}

function installSynapseCanvasEvents() {
    const canvas = document.getElementById("synapse-canvas");
    if (!canvas || window.__synapseCanvasEventsInstalled) return;

    window.__synapseCanvasEventsInstalled = true;
    canvas.addEventListener("click", handleSynapseCanvasClick);
    window.addEventListener("resize", resizeSynapseCanvas);
}

document.addEventListener("DOMContentLoaded", () => {
    ensureSynapseModeInstalled();
    installSynapseCanvasEvents();

    const saved = localStorage.getItem("technemachina_mode");
    if (saved === "synapse") {
        setTimeout(() => {
            if (typeof setAppMode === "function") setAppMode("synapse");
            loadSynapseMap();
        }, 120);
    }
});

// --- End Technemachina Synapse Map Frontend / Constellation Renderer ---


// --- Technemachina Synapse Map Fetch Hardpatch v0.2.9c-1 ---

async function loadSynapseMap() {
    const title = document.getElementById("synapse-inspector-title");
    const subtitle = document.getElementById("synapse-inspector-subtitle");

    const endpoint = window.location.protocol === "file:"
        ? "http://127.0.0.1:8000/synapse/map"
        : "http://127.0.0.1:8000/synapse/map";

    try {
        if (title) title.textContent = "Loading constellation…";
        if (subtitle) subtitle.textContent = `Reading ${endpoint} without mutation.`;

        const response = await fetch(endpoint, {
            method: "GET",
            cache: "no-store",
            headers: {
                "Accept": "application/json",
            },
        });

        if (!response.ok) {
            throw new Error(`Synapse endpoint returned HTTP ${response.status}`);
        }

        const map = await response.json();

        window.__synapseMapState.map = map;
        window.__synapseMapState.selected = null;

        prepareSynapseLayout(map);
        updateSynapseStatus(map);
        updateSynapseInspector(null);
        resizeSynapseCanvas();
        drawSynapseMap();

    } catch (error) {
        if (title) title.textContent = "Synapse Map unavailable";
        if (subtitle) subtitle.textContent = String(error);
        console.error("Synapse Map load failed:", error);
    }
}

// --- End Technemachina Synapse Map Fetch Hardpatch ---


// --- Technemachina Synapse Map Zoom + Black Starfield Patch v0.2.9c-2 ---

if (!window.__synapseMapState) {
    window.__synapseMapState = {};
}

window.__synapseMapState.zoom = window.__synapseMapState.zoom || 1;

function clampSynapseZoom(value) {
    return Math.max(0.2, Math.min(4.5, value));
}

function setSynapseZoom(nextZoom) {
    window.__synapseMapState.zoom = clampSynapseZoom(nextZoom);
    updateSynapseZoomLabel();
    drawSynapseMap();
}

function updateSynapseZoomLabel() {
    const reset = document.getElementById("synapse-zoom-reset-btn");
    if (reset) {
        reset.textContent = `${Math.round((window.__synapseMapState.zoom || 1) * 100)}%`;
    }
}

function installSynapseZoomControls() {
    const zoomIn = document.getElementById("synapse-zoom-in-btn");
    const zoomOut = document.getElementById("synapse-zoom-out-btn");
    const zoomReset = document.getElementById("synapse-zoom-reset-btn");

    if (zoomIn && !zoomIn.dataset.bound) {
        zoomIn.dataset.bound = "true";
        zoomIn.addEventListener("click", () => {
            setSynapseZoom((window.__synapseMapState.zoom || 1) * 1.18);
        });
    }

    if (zoomOut && !zoomOut.dataset.bound) {
        zoomOut.dataset.bound = "true";
        zoomOut.addEventListener("click", () => {
            setSynapseZoom((window.__synapseMapState.zoom || 1) / 1.18);
        });
    }

    if (zoomReset && !zoomReset.dataset.bound) {
        zoomReset.dataset.bound = "true";
        zoomReset.addEventListener("click", () => {
            setSynapseZoom(1);
        });
    }

    updateSynapseZoomLabel();
}

function drawSynapseMap() {
    const canvas = document.getElementById("synapse-canvas");
    const map = window.__synapseMapState.map;
    if (!canvas || !map) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const rect = canvas.getBoundingClientRect();
    const width = rect.width;
    const height = rect.height;
    const positions = window.__synapseMapState.positions;
    const selected = window.__synapseMapState.selected;
    const zoom = window.__synapseMapState.zoom || 1;

    ctx.clearRect(0, 0, width, height);

    // True black starfield base.
    ctx.fillStyle = "rgba(0, 0, 0, 1)";
    ctx.fillRect(0, 0, width, height);

    // Very subtle center falloff, still black — no blue wash.
    const gradient = ctx.createRadialGradient(
        width / 2,
        height / 2,
        20,
        width / 2,
        height / 2,
        Math.max(width, height)
    );
    gradient.addColorStop(0, "rgba(12, 12, 16, 0.42)");
    gradient.addColorStop(1, "rgba(0, 0, 0, 1)");
    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, width, height);

    ctx.save();
    ctx.translate(width / 2, height / 2);
    ctx.scale(zoom, zoom);
    ctx.translate(-width / 2, -height / 2);

    const selectedId = selected?.kind === "node" ? selected.item.id : null;
    const connectedIds = new Set();

    if (selectedId) {
        (map.edges || []).forEach(edge => {
            if (edge.source === selectedId || edge.target === selectedId) {
                connectedIds.add(edge.source);
                connectedIds.add(edge.target);
            }
        });
    }

    // Luminous relation threads.
    (map.edges || []).forEach(edge => {
        const a = positions.get(edge.source);
        const b = positions.get(edge.target);
        if (!a || !b) return;

        const isSelectedPath = selectedId && (edge.source === selectedId || edge.target === selectedId);
        const alpha = selectedId ? (isSelectedPath ? 0.86 : 0.09) : 0.22;
        const widthLine = isSelectedPath ? 1.7 / zoom : 0.75 / zoom;

        ctx.beginPath();
        ctx.moveTo(a.x, a.y);
        ctx.lineTo(b.x, b.y);
        ctx.lineWidth = widthLine;
        ctx.strokeStyle = `rgba(230, 235, 255, ${alpha})`;
        ctx.shadowColor = `rgba(255, 255, 255, ${alpha})`;
        ctx.shadowBlur = isSelectedPath ? 12 / zoom : 4 / zoom;
        ctx.stroke();
        ctx.shadowBlur = 0;
    });

    // Object-backed stars.
    (map.nodes || []).forEach(node => {
        const p = positions.get(node.id);
        if (!p) return;

        const isSelected = selectedId === node.id;
        const isConnected = connectedIds.has(node.id);
        const dimmed = selectedId && !isSelected && !isConnected;
        const salience = Number(node?.skin?.salience || node.weight || 0.5);
        const radius = p.radius * (isSelected ? 1.55 : 1);
        const color = synapseNodeColor(node.type, node.status);

        ctx.globalAlpha = dimmed ? 0.22 : 1;

        ctx.beginPath();
        ctx.arc(p.x, p.y, radius + 8 + salience * 7, 0, Math.PI * 2);
        ctx.fillStyle = color.replace(/[\d.]+\)$/g, dimmed ? "0.05)" : isSelected ? "0.26)" : "0.12)");
        ctx.shadowColor = color;
        ctx.shadowBlur = isSelected ? 24 / zoom : 11 / zoom;
        ctx.fill();

        ctx.beginPath();
        ctx.arc(p.x, p.y, radius, 0, Math.PI * 2);
        ctx.fillStyle = color;
        ctx.shadowBlur = isSelected ? 16 / zoom : 7 / zoom;
        ctx.fill();

        const shouldLabel =
            isSelected ||
            zoom >= 1.65 ||
            (!selectedId && (node.type === "project_context" || node.type === "doctrine"));

        if (shouldLabel) {
            ctx.font = `${12 / zoom}px system-ui, -apple-system, BlinkMacSystemFont, sans-serif`;
            ctx.fillStyle = "rgba(245, 247, 255, 0.92)";
            ctx.shadowBlur = 0;
            ctx.fillText(String(node.label || node.id).slice(0, 46), p.x + 12, p.y - 10);
        }

        ctx.globalAlpha = 1;
        ctx.shadowBlur = 0;
    });

    ctx.restore();
}

function handleSynapseCanvasClick(event) {
    const canvas = document.getElementById("synapse-canvas");
    const map = window.__synapseMapState.map;
    if (!canvas || !map) return;

    const rect = canvas.getBoundingClientRect();
    const zoom = window.__synapseMapState.zoom || 1;

    const screenX = event.clientX - rect.left;
    const screenY = event.clientY - rect.top;

    // Invert center-based zoom transform.
    const x = (screenX - rect.width / 2) / zoom + rect.width / 2;
    const y = (screenY - rect.height / 2) / zoom + rect.height / 2;

    const positions = window.__synapseMapState.positions;
    let hit = null;

    for (const node of map.nodes || []) {
        const p = positions.get(node.id);
        if (!p) continue;

        const dx = x - p.x;
        const dy = y - p.y;
        const distance = Math.sqrt(dx * dx + dy * dy);

        if (distance <= p.radius + 10) {
            hit = node;
            break;
        }
    }

    if (hit) {
        window.__synapseMapState.selected = { kind: "node", item: hit };
        updateSynapseInspector(window.__synapseMapState.selected);
        drawSynapseMap();
    }
}

document.addEventListener("DOMContentLoaded", () => {
    installSynapseZoomControls();
});

// --- End Technemachina Synapse Map Zoom + Black Starfield Patch ---


// --- Technemachina Synapse Map Galaxy Layout Engine v0.2.9d ---

if (!window.__synapseMapState) {
    window.__synapseMapState = {};
}

Object.assign(window.__synapseMapState, {
    zoom: window.__synapseMapState.zoom || 0.32,
    panX: window.__synapseMapState.panX || 0,
    panY: window.__synapseMapState.panY || 0,
    rotation: window.__synapseMapState.rotation || 0,
    autoRotate: true,
    isDragging: false,
    dragStart: null,
    positions3d: window.__synapseMapState.positions3d || new Map(),
});

function synapseIsGuideStar(node) {
    const text = `${node?.label || ""} ${node?.id || ""}`.toLowerCase();
    return (
        node?.type === "project_context" ||
        node?.type === "doctrine" ||
        text.includes("brain online") ||
        text.includes("memory") ||
        text.includes("knowledge") ||
        text.includes("synapse") ||
        text.includes("h.i.v.e") ||
        text.includes("hive")
    );
}

function synapseGalaxyForNode(node) {
    const type = node?.type || "";
    const text = `${node?.label || ""} ${node?.id || ""}`.toLowerCase();

    if (type === "project_context" || type === "doctrine") return "core";
    if (type === "memory_record" || type === "memory_layer") return "memory";
    if (type === "knowledge_record" || type === "knowledge_source") return "knowledge";
    if (type === "thread_candidate" || type === "knowledge_candidate") return "candidate";
    if (type === "review_item" || type === "review_decision") return "governance";
    if (type === "thread") return "threads";
    if (type === "milestone_cluster") return "deepfield";
    if (type === "milestone" && text.includes("synapse")) return "synapse";
    if (type === "milestone" && text.includes("knowledge")) return "knowledge";
    if (type === "milestone" && text.includes("memory")) return "memory";
    if (type === "milestone" && (text.includes("review") || text.includes("decision"))) return "governance";
    if (type === "milestone" && text.includes("candidate")) return "candidate";
    if (type === "milestone" && text.includes("thread")) return "threads";
    if (type === "milestone") return "milestones";
    return "deepfield";
}

function synapseGalaxyAnchor(galaxy, width, height) {
    const cx = width / 2;
    const cy = height / 2;

    const anchors = {
        core:       { x: cx,       y: cy,       z: 40,   spread: 70 },
        knowledge:  { x: cx - 310,  y: cy - 190, z: 120,  spread: 145 },
        memory:     { x: cx + 315,  y: cy - 185, z: -80,  spread: 145 },
        candidate:  { x: cx - 280,  y: cy + 205, z: -120, spread: 135 },
        governance: { x: cx + 300,  y: cy + 205, z: 100,  spread: 135 },
        threads:    { x: cx - 20,   y: cy + 330, z: -180, spread: 190 },
        synapse:    { x: cx + 25,   y: cy - 330, z: 180,  spread: 150 },
        milestones: { x: cx,        y: cy + 25,  z: -260, spread: 360 },
        deepfield:  { x: cx + 420,  y: cy,       z: 240,  spread: 190 },
    };

    return anchors[galaxy] || anchors.deepfield;
}

function prepareSynapseLayout(map) {
    const canvas = document.getElementById("synapse-canvas");
    if (!canvas || !map || !Array.isArray(map.nodes)) return;

    const rect = canvas.getBoundingClientRect();
    const width = rect.width || 900;
    const height = rect.height || 560;

    const positions3d = new Map();
    const galaxyCounts = {};

    map.nodes.forEach((node, index) => {
        const galaxy = synapseGalaxyForNode(node);
        const count = galaxyCounts[galaxy] || 0;
        galaxyCounts[galaxy] = count + 1;

        const anchor = synapseGalaxyAnchor(galaxy, width, height);
        const guide = synapseIsGuideStar(node);

        const angle = count * 2.399963229728653 + index * 0.017;
        const ring = guide ? 18 + (count % 4) * 18 : 34 + Math.floor(count / 11) * 38;
        const spread = guide ? anchor.spread * 0.38 : anchor.spread;
        const ripple = Math.sin(index * 1.713) * 55;
        const depth = anchor.z + Math.cos(angle * 1.7) * 130 + ripple;

        let x = anchor.x + Math.cos(angle) * Math.min(spread, ring + count * 1.8);
        let y = anchor.y + Math.sin(angle) * Math.min(spread, ring + count * 1.8);

        if (galaxy === "core") {
            x = anchor.x + (node.type === "doctrine" ? 55 : -55);
            y = anchor.y + (node.type === "doctrine" ? 12 : -12);
        }

        positions3d.set(node.id, {
            baseX: x,
            baseY: y,
            baseZ: depth,
            galaxy,
            guide,
            radius: (guide ? 6.4 : 3.2) + Math.max(0.4, Number(node.weight || 0.5)) * (guide ? 6.5 : 4.8),
        });
    });

    window.__synapseMapState.positions3d = positions3d;
    projectSynapse3DPositions();
}

function projectSynapse3DPositions() {
    const canvas = document.getElementById("synapse-canvas");
    if (!canvas) return;

    const rect = canvas.getBoundingClientRect();
    const width = rect.width || 900;
    const height = rect.height || 560;
    const cx = width / 2;
    const rotation = window.__synapseMapState.rotation || 0;
    const panX = window.__synapseMapState.panX || 0;
    const panY = window.__synapseMapState.panY || 0;

    const positions = new Map();

    for (const [id, p] of (window.__synapseMapState.positions3d || new Map()).entries()) {
        const dx = p.baseX - cx;
        const dz = p.baseZ || 0;

        const rx = dx * Math.cos(rotation) - dz * Math.sin(rotation);
        const rz = dx * Math.sin(rotation) + dz * Math.cos(rotation);

        const perspective = 620 / (620 + rz);
        positions.set(id, {
            x: cx + rx * perspective + panX,
            y: p.baseY + panY,
            z: rz,
            radius: Math.max(1.4, p.radius * perspective),
            depthAlpha: Math.max(0.22, Math.min(1, perspective)),
            galaxy: p.galaxy,
            guide: p.guide,
        });
    }

    window.__synapseMapState.positions = positions;
}

function synapseEdgeVisible(edge, zoom, selectedId) {
    if (selectedId && (edge.source === selectedId || edge.target === selectedId)) return true;

    const type = edge?.type || "";
    const strength = Number(edge?.strength || 0);

    if (zoom < 0.86) {
        return (
            type === "has_milestone" ||
            type === "belongs_to_cluster" ||
            type === "precedes" ||
            strength >= 0.9
        );
    }

    if (zoom < 1.45) {
        return strength >= 0.65 || type === "candidate_from" || type === "queued_as";
    }

    return true;
}

function synapseNodeLabelVisible(node, zoom, selectedId, connectedIds) {
    if (selectedId === node.id) return true;
    if (synapseIsGuideStar(node) && zoom >= 0.72) return true;
    if (connectedIds && connectedIds.has(node.id) && zoom >= 1.18) return true;
    if (zoom >= 1.85) return true;
    return false;
}

function drawSynapseMap() {
    const canvas = document.getElementById("synapse-canvas");
    const map = window.__synapseMapState.map;
    if (!canvas || !map) return;

    projectSynapse3DPositions();

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const rect = canvas.getBoundingClientRect();
    const width = rect.width;
    const height = rect.height;
    const zoom = window.__synapseMapState.zoom || 1;
    const positions = window.__synapseMapState.positions || new Map();
    const selected = window.__synapseMapState.selected;
    const selectedId = selected?.kind === "node" ? selected.item.id : null;

    ctx.clearRect(0, 0, width, height);
    ctx.fillStyle = "#000000";
    ctx.fillRect(0, 0, width, height);

    ctx.save();
    ctx.translate(width / 2, height / 2);
    ctx.scale(zoom, zoom);
    ctx.translate(-width / 2, -height / 2);

    const connectedIds = new Set();

    if (selectedId) {
        (map.edges || []).forEach(edge => {
            if (edge.source === selectedId || edge.target === selectedId) {
                connectedIds.add(edge.source);
                connectedIds.add(edge.target);
            }
        });
    }

    // Sparse cross-galaxy edges first.
    (map.edges || []).forEach(edge => {
        if (!synapseEdgeVisible(edge, zoom, selectedId)) return;

        const a = positions.get(edge.source);
        const b = positions.get(edge.target);
        if (!a || !b) return;

        const selectedPath = selectedId && (edge.source === selectedId || edge.target === selectedId);
        const crossGalaxy = a.galaxy !== b.galaxy;

        let alpha = selectedPath ? 0.78 : 0.15;
        if (crossGalaxy) alpha *= zoom < 1.2 ? 0.34 : 0.62;
        if (!selectedPath && edge.type === "precedes") alpha *= 0.42;

        const depth = Math.min(a.depthAlpha, b.depthAlpha);
        alpha *= depth;

        ctx.beginPath();
        ctx.moveTo(a.x, a.y);
        ctx.lineTo(b.x, b.y);
        ctx.lineWidth = selectedPath ? 1.55 / zoom : 0.55 / zoom;
        ctx.strokeStyle = `rgba(235, 240, 255, ${alpha})`;
        ctx.shadowColor = `rgba(255, 255, 255, ${alpha})`;
        ctx.shadowBlur = selectedPath ? 13 / zoom : 2 / zoom;
        ctx.stroke();
        ctx.shadowBlur = 0;
    });

    const sortedNodes = [...(map.nodes || [])].sort((a, b) => {
        const pa = positions.get(a.id);
        const pb = positions.get(b.id);
        return (pa?.z || 0) - (pb?.z || 0);
    });

    sortedNodes.forEach(node => {
        const p = positions.get(node.id);
        if (!p) return;

        const selectedNode = selectedId === node.id;
        const connected = connectedIds.has(node.id);
        const dimmed = selectedId && !selectedNode && !connected;
        const guide = synapseIsGuideStar(node);
        const salience = Number(node?.skin?.salience || node.weight || 0.5);
        const radius = p.radius * (selectedNode ? 1.7 : 1);
        const color = typeof synapseNodeColor === "function"
            ? synapseNodeColor(node.type, node.status)
            : "rgba(245, 247, 255, 0.95)";

        ctx.globalAlpha = dimmed ? 0.15 : p.depthAlpha;

        // Halo
        ctx.beginPath();
        ctx.arc(p.x, p.y, radius + (guide ? 15 : 7) + salience * 5, 0, Math.PI * 2);
        ctx.fillStyle = color.replace(/[\d.]+\)$/g, selectedNode ? "0.24)" : guide ? "0.16)" : "0.08)");
        ctx.shadowColor = color;
        ctx.shadowBlur = selectedNode ? 28 / zoom : guide ? 16 / zoom : 8 / zoom;
        ctx.fill();

        // Star core
        ctx.beginPath();
        ctx.arc(p.x, p.y, radius, 0, Math.PI * 2);
        ctx.fillStyle = color;
        ctx.shadowBlur = selectedNode ? 20 / zoom : guide ? 12 / zoom : 6 / zoom;
        ctx.fill();

        if (synapseNodeLabelVisible(node, zoom, selectedId, connectedIds)) {
            ctx.globalAlpha = dimmed ? 0.25 : 0.92;
            ctx.font = `${guide ? 12.5 / zoom : 11 / zoom}px system-ui, -apple-system, BlinkMacSystemFont, sans-serif`;
            ctx.fillStyle = "rgba(245, 247, 255, 0.92)";
            ctx.shadowBlur = 0;
            ctx.fillText(String(node.label || node.id).slice(0, guide ? 52 : 42), p.x + 12, p.y - 9);
        }

        ctx.globalAlpha = 1;
        ctx.shadowBlur = 0;
    });

    ctx.restore();
}

function startSynapseOrbitLoop() {
    if (window.__synapseOrbitLoopStarted) return;
    window.__synapseOrbitLoopStarted = true;

    function loop() {
        if (window.__synapseMapState.autoRotate && !window.__synapseMapState.isDragging) {
            window.__synapseMapState.rotation += 0.00115;
            drawSynapseMap();
        }
        requestAnimationFrame(loop);
    }

    requestAnimationFrame(loop);
}

function installSynapseGalaxyControls() {
    const canvas = document.getElementById("synapse-canvas");
    if (!canvas || window.__synapseGalaxyControlsInstalled) return;

    window.__synapseGalaxyControlsInstalled = true;

    canvas.addEventListener("pointerdown", event => {
        window.__synapseMapState.isDragging = true;
        window.__synapseMapState.dragStart = {
            x: event.clientX,
            y: event.clientY,
            panX: window.__synapseMapState.panX || 0,
            panY: window.__synapseMapState.panY || 0,
            moved: false,
        };
        canvas.classList.add("is-grabbing");
    });

    window.addEventListener("pointermove", event => {
        const state = window.__synapseMapState;
        if (!state.isDragging || !state.dragStart) return;

        const dx = event.clientX - state.dragStart.x;
        const dy = event.clientY - state.dragStart.y;

        if (Math.abs(dx) + Math.abs(dy) > 4) state.dragStart.moved = true;

        state.panX = state.dragStart.panX + dx;
        state.panY = state.dragStart.panY + dy;
        drawSynapseMap();
    });

    window.addEventListener("pointerup", event => {
        const state = window.__synapseMapState;
        const wasClick = state.dragStart && !state.dragStart.moved;

        state.isDragging = false;
        canvas.classList.remove("is-grabbing");

        if (wasClick && typeof handleSynapseCanvasClick === "function") {
            handleSynapseCanvasClick(event);
        }

        state.dragStart = null;
    });

    canvas.addEventListener("wheel", event => {
        event.preventDefault();
        const next = (window.__synapseMapState.zoom || 1) * (event.deltaY < 0 ? 1.08 : 0.92);
        if (typeof setSynapseZoom === "function") {
            setSynapseZoom(next);
        } else {
            window.__synapseMapState.zoom = Math.max(0.2, Math.min(4.5, next));
            drawSynapseMap();
        }
    }, { passive: false });

    startSynapseOrbitLoop();
}

document.addEventListener("DOMContentLoaded", () => {
    installSynapseGalaxyControls();
});

setTimeout(installSynapseGalaxyControls, 500);
setTimeout(installSynapseGalaxyControls, 1500);

// --- End Technemachina Synapse Map Galaxy Layout Engine ---


// --- Technemachina Synapse Map Safe Orbit Controls v0.2.9e-safe ---

if (!window.__synapseMapState) {
    window.__synapseMapState = {};
}

window.__synapseMapState.interactionMode = window.__synapseMapState.interactionMode || "pan";
window.__synapseMapState.tilt = window.__synapseMapState.tilt || 0;
window.__synapseMapState.safeOrbitDrag = null;
window.__synapseMapState.focusTween = null;

function synapseSafeClamp(value, min, max) {
    return Math.max(min, Math.min(max, value));
}

function synapseSafeSetZoom(nextZoom) {
    if (typeof setSynapseZoom === "function") {
        setSynapseZoom(nextZoom);
    } else {
        window.__synapseMapState.zoom = synapseSafeClamp(nextZoom, 0.2, 4.5);
        drawSynapseMap();
    }
}

function updateSynapseSafeButtons() {
    const modeBtn = document.getElementById("synapse-drag-mode-btn");
    const lockBtn = document.getElementById("synapse-orbit-lock-btn");

    if (modeBtn) {
        modeBtn.textContent = `Drag: ${window.__synapseMapState.interactionMode === "orbit" ? "Orbit" : "Pan"}`;
    }

    if (lockBtn) {
        lockBtn.textContent = window.__synapseMapState.autoRotate ? "Lock" : "Resume";
    }
}

function toggleSynapseOrbitMode() {
    window.__synapseMapState.interactionMode =
        window.__synapseMapState.interactionMode === "orbit" ? "pan" : "orbit";
    updateSynapseSafeButtons();
}

function toggleSynapseRotationLock() {
    window.__synapseMapState.autoRotate = !window.__synapseMapState.autoRotate;
    updateSynapseSafeButtons();
}

function resetSynapseViewSafe() {
    window.__synapseMapState.panX = 0;
    window.__synapseMapState.panY = 0;
    window.__synapseMapState.zoom = 0.32;
    window.__synapseMapState.tilt = 0;
    window.__synapseMapState.rotation = 0;
    updateSynapseZoomLabel?.();
    drawSynapseMap();
}

function focusSelectedSynapseStar() {
    const selected = window.__synapseMapState.selected;
    const positions = window.__synapseMapState.positions;
    const canvas = document.getElementById("synapse-canvas");

    if (!selected || !positions || !canvas) return;

    const p = positions.get(selected.item.id);
    if (!p) return;

    const rect = canvas.getBoundingClientRect();

    const targetPanX = (window.__synapseMapState.panX || 0) + rect.width / 2 - p.x;
    const targetPanY = (window.__synapseMapState.panY || 0) + rect.height / 2 - p.y;
    const targetZoom = Math.max(window.__synapseMapState.zoom || 1, 1.65);

    window.__synapseMapState.focusTween = {
        startTime: performance.now(),
        duration: 520,
        fromPanX: window.__synapseMapState.panX || 0,
        fromPanY: window.__synapseMapState.panY || 0,
        fromZoom: window.__synapseMapState.zoom || 1,
        targetPanX,
        targetPanY,
        targetZoom,
    };

    runSynapseFocusTween();
}

function runSynapseFocusTween() {
    const tween = window.__synapseMapState.focusTween;
    if (!tween) return;

    const now = performance.now();
    const raw = Math.min(1, (now - tween.startTime) / tween.duration);
    const eased = 1 - Math.pow(1 - raw, 3);

    window.__synapseMapState.panX = tween.fromPanX + (tween.targetPanX - tween.fromPanX) * eased;
    window.__synapseMapState.panY = tween.fromPanY + (tween.targetPanY - tween.fromPanY) * eased;
    window.__synapseMapState.zoom = tween.fromZoom + (tween.targetZoom - tween.fromZoom) * eased;

    updateSynapseZoomLabel?.();
    drawSynapseMap();

    if (raw < 1) {
        requestAnimationFrame(runSynapseFocusTween);
    } else {
        window.__synapseMapState.focusTween = null;
    }
}

function installSynapseSafeControlButtons() {
    const modeBtn = document.getElementById("synapse-drag-mode-btn");
    const lockBtn = document.getElementById("synapse-orbit-lock-btn");
    const focusBtn = document.getElementById("synapse-focus-btn");

    if (modeBtn && !modeBtn.dataset.safeBound) {
        modeBtn.dataset.safeBound = "true";
        modeBtn.addEventListener("click", toggleSynapseOrbitMode);
    }

    if (lockBtn && !lockBtn.dataset.safeBound) {
        lockBtn.dataset.safeBound = "true";
        lockBtn.addEventListener("click", toggleSynapseRotationLock);
    }

    if (focusBtn && !focusBtn.dataset.safeBound) {
        focusBtn.dataset.safeBound = "true";
        focusBtn.addEventListener("click", focusSelectedSynapseStar);
    }

    updateSynapseSafeButtons();
}

const previousProjectSynapse3DPositions_safe = projectSynapse3DPositions;

projectSynapse3DPositions = function() {
    const canvas = document.getElementById("synapse-canvas");
    if (!canvas) return previousProjectSynapse3DPositions_safe();

    const rect = canvas.getBoundingClientRect();
    const width = rect.width || 900;
    const height = rect.height || 560;
    const cx = width / 2;
    const cy = height / 2;

    const rotation = window.__synapseMapState.rotation || 0;
    const tilt = window.__synapseMapState.tilt || 0;
    const panX = window.__synapseMapState.panX || 0;
    const panY = window.__synapseMapState.panY || 0;
    const positions = new Map();

    for (const [id, p] of (window.__synapseMapState.positions3d || new Map()).entries()) {
        const dx = p.baseX - cx;
        const dy = p.baseY - cy;
        const dz = p.baseZ || 0;

        const rx = dx * Math.cos(rotation) - dz * Math.sin(rotation);
        let rz = dx * Math.sin(rotation) + dz * Math.cos(rotation);

        const ry = dy * Math.cos(tilt) - rz * Math.sin(tilt);
        rz = dy * Math.sin(tilt) + rz * Math.cos(tilt);

        const perspective = 620 / (620 + rz);

        positions.set(id, {
            x: cx + rx * perspective + panX,
            y: cy + ry * perspective + panY,
            z: rz,
            radius: Math.max(1.4, p.radius * perspective),
            depthAlpha: Math.max(0.22, Math.min(1, perspective)),
            galaxy: p.galaxy,
            guide: p.guide,
        });
    }

    window.__synapseMapState.positions = positions;
};

function installSynapseSafeOrbitDrag() {
    const canvas = document.getElementById("synapse-canvas");
    if (!canvas || window.__synapseSafeOrbitDragInstalled) return;

    window.__synapseSafeOrbitDragInstalled = true;

    canvas.addEventListener("pointerdown", event => {
        if (window.__synapseMapState.interactionMode !== "orbit") return;

        window.__synapseMapState.autoRotate = false;
        window.__synapseMapState.safeOrbitDrag = {
            x: event.clientX,
            y: event.clientY,
            rotation: window.__synapseMapState.rotation || 0,
            tilt: window.__synapseMapState.tilt || 0,
            moved: false,
        };

        canvas.classList.add("is-grabbing");
        updateSynapseSafeButtons();
    });

    window.addEventListener("pointermove", event => {
        const drag = window.__synapseMapState.safeOrbitDrag;
        if (!drag) return;

        const dx = event.clientX - drag.x;
        const dy = event.clientY - drag.y;

        if (Math.abs(dx) + Math.abs(dy) > 4) {
            drag.moved = true;
        }

        window.__synapseMapState.rotation = drag.rotation + dx * 0.0055;
        window.__synapseMapState.tilt = synapseSafeClamp(drag.tilt + dy * 0.0035, -0.72, 0.72);

        drawSynapseMap();
    });

    window.addEventListener("pointerup", () => {
        if (!window.__synapseMapState.safeOrbitDrag) return;

        window.__synapseMapState.safeOrbitDrag = null;

        const canvas = document.getElementById("synapse-canvas");
        if (canvas) canvas.classList.remove("is-grabbing");
    });
}

function installSynapseKeyboardShortcuts() {
    if (window.__synapseKeyboardShortcutsInstalled) return;
    window.__synapseKeyboardShortcutsInstalled = true;

    window.addEventListener("keydown", event => {
        const target = event.target;
        const tag = target?.tagName?.toLowerCase();
        if (tag === "input" || tag === "textarea" || target?.isContentEditable) return;

        const key = event.key.toLowerCase();

        if (key === "o") {
            event.preventDefault();
            toggleSynapseOrbitMode();
        } else if (key === "l") {
            event.preventDefault();
            toggleSynapseRotationLock();
        } else if (key === "f") {
            event.preventDefault();
            focusSelectedSynapseStar();
        } else if (key === "r") {
            event.preventDefault();
            resetSynapseViewSafe();
        } else if (event.key === "+" || event.key === "=") {
            event.preventDefault();
            synapseSafeSetZoom((window.__synapseMapState.zoom || 1) * 1.12);
        } else if (event.key === "-" || event.key === "_") {
            event.preventDefault();
            synapseSafeSetZoom((window.__synapseMapState.zoom || 1) / 1.12);
        }
    });
}

document.addEventListener("DOMContentLoaded", () => {
    installSynapseSafeControlButtons();
    installSynapseSafeOrbitDrag();
    installSynapseKeyboardShortcuts();
});

setTimeout(() => {
    installSynapseSafeControlButtons();
    installSynapseSafeOrbitDrag();
    installSynapseKeyboardShortcuts();
}, 500);

// --- End Technemachina Synapse Map Safe Orbit Controls ---


// --- Technemachina Synapse Map Red Trace + Orbit Override Fix v0.2.9e-1 ---

function synapseIsSelectedPath(edge, selectedId) {
    return selectedId && (edge.source === selectedId || edge.target === selectedId);
}

const previousDrawSynapseMap_redTrace = drawSynapseMap;

drawSynapseMap = function() {
    const canvas = document.getElementById("synapse-canvas");
    const map = window.__synapseMapState.map;
    if (!canvas || !map) return;

    projectSynapse3DPositions();

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const rect = canvas.getBoundingClientRect();
    const width = rect.width;
    const height = rect.height;
    const zoom = window.__synapseMapState.zoom || 1;
    const positions = window.__synapseMapState.positions || new Map();
    const selected = window.__synapseMapState.selected;
    const selectedId = selected?.kind === "node" ? selected.item.id : null;

    ctx.clearRect(0, 0, width, height);
    ctx.fillStyle = "#000000";
    ctx.fillRect(0, 0, width, height);

    ctx.save();
    ctx.translate(width / 2, height / 2);
    ctx.scale(zoom, zoom);
    ctx.translate(-width / 2, -height / 2);

    const connectedIds = new Set();

    if (selectedId) {
        (map.edges || []).forEach(edge => {
            if (synapseIsSelectedPath(edge, selectedId)) {
                connectedIds.add(edge.source);
                connectedIds.add(edge.target);
            }
        });
    }

    // Edges: non-selected faint, selected path red.
    (map.edges || []).forEach(edge => {
        if (!synapseEdgeVisible(edge, zoom, selectedId)) return;

        const a = positions.get(edge.source);
        const b = positions.get(edge.target);
        if (!a || !b) return;

        const selectedPath = synapseIsSelectedPath(edge, selectedId);
        const crossGalaxy = a.galaxy !== b.galaxy;

        let alpha = selectedPath ? 0.95 : 0.13;
        if (!selectedPath && crossGalaxy) alpha *= zoom < 1.2 ? 0.28 : 0.55;

        const depth = Math.min(a.depthAlpha || 1, b.depthAlpha || 1);
        alpha *= selectedPath ? 1 : depth;

        ctx.beginPath();
        ctx.moveTo(a.x, a.y);
        ctx.lineTo(b.x, b.y);

        if (selectedPath) {
            ctx.lineWidth = 2.3 / zoom;
            ctx.strokeStyle = `rgba(255, 45, 45, ${alpha})`;
            ctx.shadowColor = `rgba(255, 0, 0, ${alpha})`;
            ctx.shadowBlur = 18 / zoom;
        } else {
            ctx.lineWidth = 0.5 / zoom;
            ctx.strokeStyle = `rgba(225, 232, 255, ${alpha})`;
            ctx.shadowColor = `rgba(255, 255, 255, ${alpha})`;
            ctx.shadowBlur = 2 / zoom;
        }

        ctx.stroke();
        ctx.shadowBlur = 0;
    });

    const sortedNodes = [...(map.nodes || [])].sort((a, b) => {
        const pa = positions.get(a.id);
        const pb = positions.get(b.id);
        return (pa?.z || 0) - (pb?.z || 0);
    });

    sortedNodes.forEach(node => {
        const p = positions.get(node.id);
        if (!p) return;

        const selectedNode = selectedId === node.id;
        const connected = connectedIds.has(node.id);
        const dimmed = selectedId && !selectedNode && !connected;
        const guide = typeof synapseIsGuideStar === "function" ? synapseIsGuideStar(node) : false;
        const salience = Number(node?.skin?.salience || node.weight || 0.5);
        const radius = p.radius * (selectedNode ? 1.8 : connected ? 1.18 : 1);
        const color = typeof synapseNodeColor === "function"
            ? synapseNodeColor(node.type, node.status)
            : "rgba(245, 247, 255, 0.95)";

        ctx.globalAlpha = dimmed ? 0.14 : p.depthAlpha;

        // Red halo on selected node and directly connected nodes.
        const haloColor = selectedNode
            ? "rgba(255, 40, 40, 0.28)"
            : connected
                ? "rgba(255, 70, 70, 0.14)"
                : color.replace(/[\d.]+\)$/g, guide ? "0.14)" : "0.08)");

        ctx.beginPath();
        ctx.arc(p.x, p.y, radius + (guide ? 15 : 7) + salience * 5, 0, Math.PI * 2);
        ctx.fillStyle = haloColor;
        ctx.shadowColor = selectedNode || connected ? "rgba(255, 0, 0, 0.95)" : color;
        ctx.shadowBlur = selectedNode ? 28 / zoom : connected ? 17 / zoom : guide ? 14 / zoom : 7 / zoom;
        ctx.fill();

        ctx.beginPath();
        ctx.arc(p.x, p.y, radius, 0, Math.PI * 2);
        ctx.fillStyle = selectedNode ? "rgba(255, 80, 80, 1)" : color;
        ctx.shadowBlur = selectedNode ? 20 / zoom : guide ? 12 / zoom : 6 / zoom;
        ctx.fill();

        if (synapseNodeLabelVisible(node, zoom, selectedId, connectedIds)) {
            ctx.globalAlpha = dimmed ? 0.25 : 0.94;
            ctx.font = `${guide ? 12.5 / zoom : 11 / zoom}px system-ui, -apple-system, BlinkMacSystemFont, sans-serif`;
            ctx.fillStyle = selectedNode || connected ? "rgba(255, 210, 210, 0.96)" : "rgba(245, 247, 255, 0.92)";
            ctx.shadowBlur = 0;
            ctx.fillText(String(node.label || node.id).slice(0, guide ? 52 : 42), p.x + 12, p.y - 9);
        }

        ctx.globalAlpha = 1;
        ctx.shadowBlur = 0;
    });

    ctx.restore();
};

// Hard override: in Orbit mode, dragging rotates instead of panning.
function installSynapseOrbitOverrideFix() {
    const canvas = document.getElementById("synapse-canvas");
    if (!canvas || window.__synapseOrbitOverrideFixInstalled) return;

    window.__synapseOrbitOverrideFixInstalled = true;

    canvas.addEventListener("pointerdown", event => {
        if (window.__synapseMapState.interactionMode !== "orbit") return;

        event.preventDefault();
        event.stopImmediatePropagation();

        window.__synapseMapState.autoRotate = false;
        window.__synapseMapState.safeOrbitDrag = {
            x: event.clientX,
            y: event.clientY,
            rotation: window.__synapseMapState.rotation || 0,
            tilt: window.__synapseMapState.tilt || 0,
            moved: false,
        };

        canvas.classList.add("is-orbiting");
        canvas.classList.add("is-grabbing");

        if (typeof updateSynapseSafeButtons === "function") updateSynapseSafeButtons();
    }, true);

    window.addEventListener("pointermove", event => {
        const drag = window.__synapseMapState.safeOrbitDrag;
        if (!drag || window.__synapseMapState.interactionMode !== "orbit") return;

        event.preventDefault();
        event.stopImmediatePropagation();

        const dx = event.clientX - drag.x;
        const dy = event.clientY - drag.y;

        if (Math.abs(dx) + Math.abs(dy) > 3) drag.moved = true;

        window.__synapseMapState.rotation = drag.rotation + dx * 0.0065;
        window.__synapseMapState.tilt = Math.max(-0.82, Math.min(0.82, drag.tilt + dy * 0.004));

        drawSynapseMap();
    }, true);

    window.addEventListener("pointerup", event => {
        const drag = window.__synapseMapState.safeOrbitDrag;
        if (!drag || window.__synapseMapState.interactionMode !== "orbit") return;

        event.preventDefault();
        event.stopImmediatePropagation();

        window.__synapseMapState.safeOrbitDrag = null;

        const c = document.getElementById("synapse-canvas");
        if (c) {
            c.classList.remove("is-orbiting");
            c.classList.remove("is-grabbing");
        }
    }, true);
}

document.addEventListener("DOMContentLoaded", installSynapseOrbitOverrideFix);
setTimeout(installSynapseOrbitOverrideFix, 500);
setTimeout(installSynapseOrbitOverrideFix, 1500);

// --- End Technemachina Synapse Map Red Trace + Orbit Override Fix ---


// --- Technemachina Layout Separation v0.2.9f ---
// Chat = cockpit mode: sidebar/thread spine stays visible.
// Synapse Map = command-center mode: sidebar hidden, map takes the room.

function applyTechnemachinaLayoutMode(mode) {
    const body = document.body;
    const chatPage = document.getElementById("chat-page");
    const synapsePage = document.getElementById("synapse-map-page");

    const isSynapse = mode === "synapse" || (synapsePage && synapsePage.classList.contains("active"));
    const isChat = mode === "chat" || (chatPage && chatPage.classList.contains("active"));

    body.classList.toggle("tm-synapse-command-mode", !!isSynapse);
    body.classList.toggle("tm-chat-cockpit-mode", !!isChat && !isSynapse);

    // Force a redraw after layout changes so the canvas recenters correctly.
    if (isSynapse) {
        setTimeout(() => {
            if (typeof drawSynapseMap === "function") drawSynapseMap();
        }, 80);

        setTimeout(() => {
            if (typeof drawSynapseMap === "function") drawSynapseMap();
        }, 300);
    }
}

(function installTechnemachinaLayoutSeparationPatch() {
    if (window.__tmLayoutSeparationPatchInstalled) return;
    window.__tmLayoutSeparationPatchInstalled = true;

    const originalSetAppMode = window.setAppMode || setAppMode;

    if (typeof originalSetAppMode === "function") {
        window.setAppMode = function(mode) {
            const result = originalSetAppMode(mode);
            applyTechnemachinaLayoutMode(mode);
            return result;
        };
    }

    document.querySelectorAll(".mode-btn").forEach(button => {
        button.addEventListener("click", () => {
            const id = button.id || "";
            if (id.includes("synapse")) applyTechnemachinaLayoutMode("synapse");
            if (id.includes("chat")) applyTechnemachinaLayoutMode("chat");
        });
    });

    document.addEventListener("DOMContentLoaded", () => {
        const activePage = document.querySelector(".mode-page.active");
        if (activePage && activePage.id === "synapse-map-page") {
            applyTechnemachinaLayoutMode("synapse");
        } else {
            applyTechnemachinaLayoutMode("chat");
        }
    });

    setTimeout(() => {
        const activePage = document.querySelector(".mode-page.active");
        if (activePage && activePage.id === "synapse-map-page") {
            applyTechnemachinaLayoutMode("synapse");
        } else {
            applyTechnemachinaLayoutMode("chat");
        }
    }, 500);
})();

// --- End Technemachina Layout Separation ---


// --- Technemachina Synapse Click + Readout Fix v0.2.9h ---
// Fixes:
// 1. Blank canvas clicks should not zoom/reset the map.
// 2. Clicking a star/node should update the lower Selected Signal readout.

function tmSynapseFindNodeById(nodeId) {
    const map = window.__synapseMapState && window.__synapseMapState.map;
    const nodes = map && Array.isArray(map.nodes) ? map.nodes : [];

    return nodes.find(node =>
        String(node.id || node.node_id || node.key || node.name || node.title) === String(nodeId)
    ) || null;
}

function tmSynapseNodeTitle(node) {
    if (!node) return "Unknown Signal";
    return node.title || node.name || node.label || node.id || node.node_id || "Unknown Signal";
}

function tmSynapseNodeSubtitle(node) {
    if (!node) return "No metadata available.";

    const parts = [];

    if (node.type) parts.push(node.type);
    if (node.status) parts.push(node.status);
    if (node.kind && !parts.includes(node.kind)) parts.push(node.kind);

    return parts.length ? parts.join(" · ") : "Synapse signal";
}

function tmSynapseNodeDescription(node) {
    if (!node) return "No signal selected.";

    return (
        node.description ||
        node.summary ||
        node.text ||
        node.content ||
        node.reason ||
        node.note ||
        node.notes ||
        node.id ||
        "No description stored for this signal yet."
    );
}

function tmUpdateSynapseLowerReadout(node) {
    const title = document.getElementById("synapse-inspector-title");
    const subtitle = document.getElementById("synapse-inspector-subtitle");
    const jsonBlock = document.getElementById("synapse-inspector-json");

    if (title) title.textContent = tmSynapseNodeTitle(node);
    if (subtitle) subtitle.textContent = `${tmSynapseNodeSubtitle(node)} — ${tmSynapseNodeDescription(node)}`;

    if (jsonBlock) {
        jsonBlock.textContent = JSON.stringify(node || {}, null, 2);
    }
}

function tmSynapseGetCanvasPoint(event, canvas) {
    const rect = canvas.getBoundingClientRect();

    return {
        x: (event.clientX - rect.left) * (canvas.width / rect.width),
        y: (event.clientY - rect.top) * (canvas.height / rect.height)
    };
}

function tmSynapseDynamicHitRadius(node, pos, zoom) {
    const nodeType = String(node?.type || "");
    const label = String(node?.label || "");
    const id = String(node?.id || "");
    const weight = Number(node?.weight || 0.5);
    const visualRadius = Number(pos?.radius || 3);

    const isGuide =
        nodeType === "project_context" ||
        nodeType === "doctrine" ||
        nodeType === "milestone_cluster" ||
        id.includes("project_context") ||
        id.includes("doctrine") ||
        label.toLowerCase().includes("cluster");

    let radius = Math.max(12, visualRadius + 10);

    if (visualRadius <= 3.5) radius += 4;
    if (weight >= 0.8) radius += 3;
    if (isGuide) radius += 8;

    // When zoomed out, the visible stars become harder to target.
    // Add forgiveness, but cap it so nearby stars do not merge into one click zone.
    if (zoom < 0.45) radius += 9;
    else if (zoom < 0.75) radius += 6;
    else if (zoom < 1.0) radius += 3;

    return Math.max(12, Math.min(30, radius));
}

function tmSynapseFindClickedNode(event) {
    const canvas = document.getElementById("synapse-canvas");
    const state = window.__synapseMapState || {};

    if (!canvas || !state.positions) return null;

    const point = tmSynapseGetCanvasPoint(event, canvas);
    const zoom = Number(state.zoom || 1);

    let best = null;
    let bestScore = Infinity;

    const positions = state.positions;

    const entries = positions instanceof Map
        ? Array.from(positions.entries())
        : Object.entries(positions || {});

    for (const [nodeId, pos] of entries) {
        if (!pos) continue;

        const px = typeof pos.x === "number" ? pos.x : Array.isArray(pos) ? pos[0] : null;
        const py = typeof pos.y === "number" ? pos.y : Array.isArray(pos) ? pos[1] : null;

        if (typeof px !== "number" || typeof py !== "number") continue;

        const node = tmSynapseFindNodeById(nodeId);
        if (!node) continue;

        const dx = point.x - px;
        const dy = point.y - py;
        const distance = Math.sqrt(dx * dx + dy * dy);
        const hitRadius = tmSynapseDynamicHitRadius(node, pos, zoom);

        if (distance > hitRadius) continue;

        // Nearest eligible star wins. The ratio avoids huge guide-star hitboxes
        // stealing clicks from smaller stars when the click is closer to the small star.
        const score = distance / hitRadius;

        if (score < bestScore) {
            bestScore = score;
            best = {
                id: nodeId,
                distance,
                hitRadius,
                score
            };
        }
    }

    if (!best) return null;

    return tmSynapseFindNodeById(best.id);
}

function tmInstallSynapseClickReadoutFix() {
    const canvas = document.getElementById("synapse-canvas");
    if (!canvas || canvas.dataset.tmClickReadoutFix === "installed") return;

    canvas.dataset.tmClickReadoutFix = "installed";

    canvas.addEventListener("click", event => {
        const node = tmSynapseFindClickedNode(event);

        // Stop old buggy canvas click behavior from firing.
        event.preventDefault();
        event.stopPropagation();
        event.stopImmediatePropagation();

        // Blank space should do nothing. No zoom collapse. No reset.
        if (!node) return false;

        window.__synapseMapState.selected = {
            kind: "node",
            item: node
        };

        tmUpdateSynapseLowerReadout(node);

        if (typeof drawSynapseMap === "function") {
            drawSynapseMap();
        }

        return false;
    }, true);
}

document.addEventListener("DOMContentLoaded", tmInstallSynapseClickReadoutFix);
setTimeout(tmInstallSynapseClickReadoutFix, 500);
setTimeout(tmInstallSynapseClickReadoutFix, 1500);

// --- End Technemachina Synapse Click + Readout Fix ---


// --- Technemachina Synapse Long Signal Description v0.2.9j ---
// Goal: when a star/node is selected, show a human-readable long description
// beneath the map instead of forcing the user to read raw JSON.

function tmLongSignalEnsureCard() {
    const canvasCard = document.querySelector(".synapse-canvas-card");
    if (!canvasCard) return null;

    let card = document.getElementById("tm-long-signal-card");

    if (!card) {
        card = document.createElement("section");
        card.id = "tm-long-signal-card";
        card.className = "tm-long-signal-card";

        card.innerHTML = `
            <div class="tm-long-signal-kicker">SELECTED SIGNAL</div>
            <h2 id="tm-long-signal-title">Select a star</h2>
            <div id="tm-long-signal-meta" class="tm-long-signal-meta">No signal selected.</div>
            <p id="tm-long-signal-description" class="tm-long-signal-description">
                Click a star/node to reveal what it actually is.
            </p>
            <div id="tm-long-signal-links" class="tm-long-signal-links"></div>
        `;

        canvasCard.insertAdjacentElement("afterend", card);
    }

    return card;
}

function tmLongSignalCleanText(value) {
    if (value === null || value === undefined) return "";
    if (typeof value === "string") return value.trim();
    if (typeof value === "number" || typeof value === "boolean") return String(value);
    return "";
}

function tmLongSignalTitle(node) {
    if (!node) return "Select a star";

    return (
        tmLongSignalCleanText(node.title) ||
        tmLongSignalCleanText(node.name) ||
        tmLongSignalCleanText(node.label) ||
        tmLongSignalCleanText(node.display_name) ||
        tmLongSignalCleanText(node.id) ||
        tmLongSignalCleanText(node.node_id) ||
        "Unknown Signal"
    );
}

function tmLongSignalMeta(node) {
    if (!node) return "No signal selected.";

    const parts = [];

    [
        node.type,
        node.kind,
        node.category,
        node.status,
        node.source,
        node.realm,
        node.provider
    ].forEach(value => {
        const cleaned = tmLongSignalCleanText(value);
        if (cleaned && !parts.includes(cleaned)) parts.push(cleaned);
    });

    return parts.length ? parts.join(" · ") : "Synapse signal";
}

function tmLongSignalDescriptionFromObject(node) {
    if (!node) return "";

    const directFields = [
        "description",
        "long_description",
        "summary",
        "details",
        "detail",
        "meaning",
        "purpose",
        "content",
        "text",
        "body",
        "note",
        "notes",
        "reason",
        "rationale",
        "memory",
        "value"
    ];

    let best = "";

    for (const field of directFields) {
        const value = tmLongSignalCleanText(node[field]);
        if (value.length > best.length) best = value;
    }

    // Some node data may hide the real description inside metadata-like objects.
    const nestedObjects = [
        node.metadata,
        node.meta,
        node.data,
        node.payload,
        node.record,
        node.item
    ];

    for (const obj of nestedObjects) {
        if (!obj || typeof obj !== "object") continue;

        for (const field of directFields) {
            const value = tmLongSignalCleanText(obj[field]);
            if (value.length > best.length) best = value;
        }
    }

    return best;
}

function tmLongSignalLinkedText(node) {
    if (!node) return "";

    const candidates = [
        node.links,
        node.linked,
        node.linked_nodes,
        node.related,
        node.related_nodes,
        node.edges,
        node.connections,
        node.neighbors
    ];

    for (const value of candidates) {
        if (Array.isArray(value) && value.length) {
            return value
                .map(item => {
                    if (typeof item === "string") return item;
                    if (item && typeof item === "object") {
                        return item.title || item.name || item.label || item.id || item.node_id || "";
                    }
                    return "";
                })
                .filter(Boolean)
                .slice(0, 8)
                .join(" · ");
        }

        if (typeof value === "string" && value.trim()) return value.trim();
    }

    return "";
}

function tmLongSignalFallbackDescription(node) {
    if (!node) return "Click a star/node to reveal what it actually is.";

    const title = tmLongSignalTitle(node);
    const meta = tmLongSignalMeta(node);

    return `${title} is a ${meta.toLowerCase()} inside the Technemachina Synapse Map. A longer doctrine-grade description has not been stored on this node yet.`;
}

function tmLongSignalExtractSelection(selection) {
    if (!selection) return null;
    if (selection.item) return selection.item;
    if (selection.node) return selection.node;
    if (selection.data) return selection.data;
    return selection;
}

function tmLongSignalRender(selection) {
    tmLongSignalEnsureCard();

    const node = tmLongSignalExtractSelection(selection);

    const titleEl = document.getElementById("tm-long-signal-title");
    const metaEl = document.getElementById("tm-long-signal-meta");
    const descEl = document.getElementById("tm-long-signal-description");
    const linksEl = document.getElementById("tm-long-signal-links");

    const title = tmLongSignalTitle(node);
    const meta = tmLongSignalMeta(node);
    const description = tmLongSignalDescriptionFromObject(node) || tmLongSignalFallbackDescription(node);
    const links = tmLongSignalLinkedText(node);

    if (titleEl) titleEl.textContent = title;
    if (metaEl) metaEl.textContent = meta;
    if (descEl) descEl.textContent = description;

    if (linksEl) {
        if (links) {
            linksEl.innerHTML = `<span>Linked Signals</span><p>${links}</p>`;
            linksEl.style.display = "block";
        } else {
            linksEl.innerHTML = "";
            linksEl.style.display = "none";
        }
    }
}

function tmLongSignalMirrorOldInspector() {
    tmLongSignalEnsureCard();

    const oldTitle = document.getElementById("synapse-inspector-title");
    const oldSubtitle = document.getElementById("synapse-inspector-subtitle");
    const oldJson = document.getElementById("synapse-inspector-json");

    const titleEl = document.getElementById("tm-long-signal-title");
    const metaEl = document.getElementById("tm-long-signal-meta");
    const descEl = document.getElementById("tm-long-signal-description");
    const linksEl = document.getElementById("tm-long-signal-links");

    let parsed = null;

    if (oldJson && oldJson.textContent && oldJson.textContent.trim() && oldJson.textContent.trim() !== "{}") {
        try {
            parsed = JSON.parse(oldJson.textContent);
        } catch {
            parsed = null;
        }
    }

    if (parsed) {
        tmLongSignalRender(parsed);
        return;
    }

    if (titleEl && oldTitle && oldTitle.textContent.trim()) {
        titleEl.textContent = oldTitle.textContent.trim();
    }

    if (metaEl && oldSubtitle && oldSubtitle.textContent.trim()) {
        metaEl.textContent = oldSubtitle.textContent.trim();
    }

    if (descEl && oldJson && oldJson.textContent.trim() && oldJson.textContent.trim() !== "{}") {
        descEl.textContent = oldJson.textContent.trim().slice(0, 700);
    }

    if (linksEl) {
        linksEl.innerHTML = "";
        linksEl.style.display = "none";
    }
}

function tmLongSignalInstall() {
    if (window.__tmLongSignalInstallComplete) return;
    window.__tmLongSignalInstallComplete = true;

    tmLongSignalEnsureCard();

    const oldUpdate = window.updateSynapseInspector;

    if (typeof oldUpdate === "function") {
        window.updateSynapseInspector = function(selection) {
            const result = oldUpdate.apply(this, arguments);
            tmLongSignalRender(selection);
            setTimeout(tmLongSignalMirrorOldInspector, 30);
            return result;
        };

        try {
            updateSynapseInspector = window.updateSynapseInspector;
        } catch (error) {
            // Safe fallback: mutation observer below still mirrors the inspector.
        }
    }

    const inspector = document.querySelector(".synapse-inspector");

    if (inspector) {
        const observer = new MutationObserver(() => {
            tmLongSignalMirrorOldInspector();
        });

        observer.observe(inspector, {
            childList: true,
            subtree: true,
            characterData: true
        });
    }

    setTimeout(tmLongSignalMirrorOldInspector, 300);
    setTimeout(tmLongSignalMirrorOldInspector, 900);
    setTimeout(tmLongSignalMirrorOldInspector, 1800);
}

document.addEventListener("DOMContentLoaded", tmLongSignalInstall);
setTimeout(tmLongSignalInstall, 500);
setTimeout(tmLongSignalInstall, 1500);

// --- End Technemachina Synapse Long Signal Description ---


// --- Technemachina Synapse Navigation Smoothing v0.2.9k ---
// No surprise motion. Click selects. Drag navigates only while held.
// Release always releases. Wheel zoom is disabled. Zoom cannot collapse.

function tmClampSynapseSafeZoom(value) {
    const number = Number(value);
    if (!Number.isFinite(number)) return 0.82;
    return Math.max(0.20, Math.min(5.0, number));
}

function tmReleaseSynapseGrip() {
    const canvas = document.getElementById("synapse-canvas");

    if (window.__synapseMapState) {
        window.__synapseMapState.safeOrbitDrag = null;
        window.__synapseMapState.drag = null;
        window.__synapseMapState.isDragging = false;
        window.__synapseMapState.isPanning = false;
        window.__synapseMapState.isOrbiting = false;
        window.__synapseMapState.pointerDown = false;
        window.__synapseMapState.mouseDown = false;
    }

    if (canvas) {
        canvas.classList.remove("is-orbiting");
        canvas.classList.remove("is-grabbing");
        canvas.classList.remove("is-panning");
        canvas.classList.remove("is-dragging");
    }

    document.body.classList.remove("tm-synapse-is-grabbing");
}

function tmInstallSynapseNavigationSmoothing() {
    const canvas = document.getElementById("synapse-canvas");
    if (!canvas || canvas.dataset.tmNavigationSmoothing === "installed") return;

    canvas.dataset.tmNavigationSmoothing = "installed";

    canvas.addEventListener("wheel", event => {
        event.preventDefault();
        event.stopPropagation();
        event.stopImmediatePropagation();
        return false;
    }, { capture: true, passive: false });

    canvas.addEventListener("pointerdown", () => {
        document.body.classList.add("tm-synapse-is-grabbing");
    }, true);

    window.addEventListener("pointerup", tmReleaseSynapseGrip, true);
    window.addEventListener("mouseup", tmReleaseSynapseGrip, true);
    window.addEventListener("blur", tmReleaseSynapseGrip, true);
    document.addEventListener("mouseleave", tmReleaseSynapseGrip, true);

    if (window.__synapseMapState) {
        window.__synapseMapState.zoom = tmClampSynapseSafeZoom(window.__synapseMapState.zoom || 0.82);
    }

    const zoomFunctionNames = [
        "setSynapseZoom",
        "synapseSafeSetZoom"
    ];

    zoomFunctionNames.forEach(name => {
        const existing = window[name];

        if (typeof existing === "function" && !existing.__tmSmoothed) {
            const wrapped = function(nextZoom) {
                return existing.call(this, tmClampSynapseSafeZoom(nextZoom));
            };

            wrapped.__tmSmoothed = true;
            window[name] = wrapped;

            try {
                eval(`${name} = window["${name}"]`);
            } catch (error) {}
        }
    });

    setInterval(() => {
        if (!window.__synapseMapState) return;

        const current = Number(window.__synapseMapState.zoom || 0.82);
        const clamped = tmClampSynapseSafeZoom(current);

        if (current !== clamped) {
            window.__synapseMapState.zoom = clamped;
            if (typeof drawSynapseMap === "function") {
                drawSynapseMap();
            }
        }
    }, 500);
}

document.addEventListener("DOMContentLoaded", tmInstallSynapseNavigationSmoothing);
setTimeout(tmInstallSynapseNavigationSmoothing, 500);
setTimeout(tmInstallSynapseNavigationSmoothing, 1500);
setTimeout(tmInstallSynapseNavigationSmoothing, 3000);

// --- End Technemachina Synapse Navigation Smoothing ---


// --- Technemachina Synapse Perception Frontend Panel v0.3.0b ---

function tmSynapseAnalysisEndpoint() {
    return window.location.protocol === "file:"
        ? "http://127.0.0.1:8000/synapse/analysis"
        : "http://127.0.0.1:8000/synapse/analysis";
}

function tmClearElement(element) {
    if (!element) return;
    while (element.firstChild) element.removeChild(element.firstChild);
}

function tmSynapsePerceptionKey(detail) {
    const safe = detail || {};

    if (safe.nodeId) {
        return `node::${safe.nodeId}`;
    }

    if (safe.sourceId || safe.targetId) {
        return `bridge::${safe.sourceId || "unknown-source"}::${safe.targetId || "unknown-target"}`;
    }

    return `fallback::${safe.kind || "signal"}::${safe.title || "untitled"}`;
}

function tmGetSynapseOracleDraftStore() {
    if (!window.__synapseMapState) window.__synapseMapState = {};
    if (!window.__synapseMapState.oracleNoteDrafts) {
        window.__synapseMapState.oracleNoteDrafts = {};
    }
    return window.__synapseMapState.oracleNoteDrafts;
}

function tmRenderSynapseOracleNoteBox(detail) {
    const box = document.getElementById("synapse-oracle-note-box");
    const input = document.getElementById("synapse-oracle-note-input");
    const status = document.getElementById("synapse-oracle-note-status");
    const saveBtn = document.getElementById("synapse-oracle-note-save-btn");
    const clearBtn = document.getElementById("synapse-oracle-note-clear-btn");

    if (!box || !input || !saveBtn || !clearBtn) return;

    const key = tmSynapsePerceptionKey(detail);
    const store = tmGetSynapseOracleDraftStore();

    box.classList.remove("hidden");
    input.dataset.synapsePerceptionKey = key;
    input.value = store[key]?.note || "";

    if (status) {
        status.textContent = store[key]?.note
            ? "Local draft restored. Not sent to memory. Pending Oracle review."
            : "Local draft only. Not sent to memory. Pending Oracle review.";
    }

    saveBtn.onclick = () => {
        const note = input.value.trim();

        if (!note) {
            if (status) {
                status.textContent = "No draft saved because the note is empty. No memory mutation.";
            }
            return;
        }

        store[key] = {
            key,
            note,
            detail: detail || {},
            updatedAt: new Date().toISOString(),
            mutationAllowed: false,
            status: "local_oracle_draft"
        };

        if (status) {
            status.textContent = "Local draft saved in browser state. Not sent to memory.";
        }
    };

    clearBtn.onclick = () => {
        input.value = "";
        delete store[key];

        if (status) {
            status.textContent = "Local draft cleared. No memory mutation.";
        }
    };
}

function tmRenderSynapsePerceptionDetail(detail) {
    const drawer = document.getElementById("synapse-perception-detail-drawer");
    const title = document.getElementById("synapse-perception-detail-title");
    const confidence = document.getElementById("synapse-perception-detail-confidence");
    const body = document.getElementById("synapse-perception-detail-body");

    if (!drawer || !title || !confidence || !body) return;

    drawer.classList.remove("hidden");

    const safeDetail = detail || {};
    const kind = safeDetail.kind || "signal";
    const detailTitle = safeDetail.title || "Unnamed perception result";
    const detailConfidence = safeDetail.confidence || "unknown";

    title.textContent = detailTitle;
    confidence.textContent = detailConfidence;
    confidence.className = `synapse-confidence synapse-confidence-${String(detailConfidence).toLowerCase()}`;

    const rows = [
        ["Type", kind],
        ["Galaxy", safeDetail.galaxy],
        ["Degree", safeDetail.degree],
        ["Weighted degree", safeDetail.weightedDegree],
        ["Source", safeDetail.sourceLabel],
        ["Target", safeDetail.targetLabel],
        ["Relation", safeDetail.relationType],
        ["Node ID", safeDetail.nodeId],
        ["Source ID", safeDetail.sourceId],
        ["Target ID", safeDetail.targetId],
        ["Reason", safeDetail.reason],
        ["Description", safeDetail.description]
    ].filter(([, value]) => value !== undefined && value !== null && value !== "");

    body.innerHTML = "";

    rows.forEach(([label, value]) => {
        const row = document.createElement("div");
        row.className = "synapse-perception-detail-row";

        const key = document.createElement("span");
        key.textContent = label;

        const val = document.createElement("strong");
        val.textContent = String(value);

        row.appendChild(key);
        row.appendChild(val);
        body.appendChild(row);
    });

    if (!rows.length) {
        body.textContent = "No detail metadata available for this perception result.";
    }

    tmRenderSynapseOracleNoteBox(safeDetail);
}

function tmBuildSynapsePerceptionDetail(kind, item, extra) {
    const data = item || {};
    const patch = extra || {};

    return {
        kind,
        title: data.label || patch.title || "Unnamed perception result",
        confidence: data.confidence || patch.confidence || "unknown",
        galaxy: data.galaxy || patch.galaxy,
        degree: data.degree,
        weightedDegree: data.weighted_degree,
        nodeId: data.id || patch.nodeId,
        sourceId: data.source || patch.sourceId,
        targetId: data.target || patch.targetId,
        sourceLabel: data.source_label || patch.sourceLabel,
        targetLabel: data.target_label || patch.targetLabel,
        relationType: data.type || patch.relationType,
        reason: data.bridge_reason || data.explanation || patch.reason,
        description: data.description || patch.description
    };
}

function tmSetActiveSynapsePerceptionCard(card) {
    document.querySelectorAll(".synapse-perception-item-active").forEach(item => {
        item.classList.remove("synapse-perception-item-active");
    });

    if (card) {
        card.classList.add("synapse-perception-item-active");
        window.__synapseMapState.activePerceptionCard = {
            nodeId: card.dataset.synapseNodeId || null,
            sourceId: card.dataset.synapseSourceId || null,
            targetId: card.dataset.synapseTargetId || null,
            title: card.querySelector("strong")?.textContent || null,
            activatedAt: Date.now()
        };
    }
}

function tmFocusSynapsePerceptionNode(nodeId) {
    if (!nodeId) return false;

    const node = tmSynapseFindNodeById(nodeId);
    if (!node) return false;

    window.__synapseMapState.selected = {
        kind: "node",
        item: node
    };

    if (typeof tmUpdateSynapseLowerReadout === "function") {
        tmUpdateSynapseLowerReadout(node);
    } else if (typeof updateSynapseInspector === "function") {
        updateSynapseInspector(window.__synapseMapState.selected);
    }

    if (typeof focusSelectedSynapseStar === "function") {
        focusSelectedSynapseStar();
    }

    if (typeof drawSynapseMap === "function") {
        drawSynapseMap();
    }

    return true;
}

function tmCreatePerceptionItem(title, meta, body, confidence, linkTarget, detailTarget) {
    const item = document.createElement("div");
    item.className = "synapse-perception-item";

    const top = document.createElement("div");
    top.className = "synapse-perception-item-top";

    const titleEl = document.createElement("strong");
    titleEl.textContent = title || "Unnamed signal";

    const confidenceEl = document.createElement("span");
    confidenceEl.className = `synapse-confidence synapse-confidence-${String(confidence || "unknown").toLowerCase()}`;
    confidenceEl.textContent = confidence || "unknown";

    top.appendChild(titleEl);
    top.appendChild(confidenceEl);

    const metaEl = document.createElement("p");
    metaEl.className = "synapse-perception-meta";
    metaEl.textContent = meta || "";

    const bodyEl = document.createElement("p");
    bodyEl.className = "synapse-perception-body";
    bodyEl.textContent = body || "";

    item.appendChild(top);
    if (meta) item.appendChild(metaEl);
    if (body) item.appendChild(bodyEl);

    if (linkTarget?.nodeId) {
        item.classList.add("synapse-perception-clickable");
        item.dataset.synapseNodeId = linkTarget.nodeId;
        item.title = "Click to select this signal on the Synapse Map";
        item.addEventListener("click", () => {
            tmSetActiveSynapsePerceptionCard(item);
            if (detailTarget) tmRenderSynapsePerceptionDetail(detailTarget);
            tmFocusSynapsePerceptionNode(linkTarget.nodeId);
        });
    }

    if (linkTarget?.sourceId || linkTarget?.targetId) {
        item.classList.add("synapse-perception-clickable");
        item.dataset.synapseSourceId = linkTarget.sourceId || "";
        item.dataset.synapseTargetId = linkTarget.targetId || "";
        item.title = "Click to select this bridge source on the Synapse Map";
        item.addEventListener("click", () => {
            tmFocusSynapsePerceptionNode(linkTarget.sourceId || linkTarget.targetId);
        });
    }

    return item;
}

function tmRenderSynapsePerception(data) {
    const panel = document.getElementById("synapse-perception-panel");
    const title = document.getElementById("synapse-perception-title");
    const badge = document.getElementById("synapse-perception-badge");
    const overview = document.getElementById("synapse-perception-overview");
    const galaxies = document.getElementById("synapse-perception-galaxies");
    const central = document.getElementById("synapse-perception-central");
    const bridges = document.getElementById("synapse-perception-bridges");
    const limitations = document.getElementById("synapse-perception-limitations");

    if (!panel) return;

    panel.classList.remove("hidden");

    if (title) {
        title.textContent = `Read-only analysis ${data?.meta?.analysis_version || ""}`.trim();
    }

    if (badge) {
        badge.textContent = data?.meta?.mutation_allowed ? "Mutation enabled" : "Read-only / No mutation";
        badge.classList.toggle("danger", !!data?.meta?.mutation_allowed);
    }

    if (overview) {
        overview.textContent = data?.overview?.summary || "No overview returned.";
    }

    tmClearElement(galaxies);
    tmClearElement(central);
    tmClearElement(bridges);
    tmClearElement(limitations);

    (data?.galaxy_summaries || []).slice(0, 6).forEach((item) => {
        galaxies?.appendChild(tmCreatePerceptionItem(
            item.galaxy,
            `nodes ${item.node_count} · edges ${item.edge_touch_count} · coverage ${item.edge_coverage}`,
            item.summary,
            item.confidence
        ));
    });

    (data?.central_nodes || []).slice(0, 6).forEach((item) => {
        central?.appendChild(tmCreatePerceptionItem(
            item.label,
            `${item.galaxy} · degree ${item.degree} · weighted ${item.weighted_degree}`,
            item.description,
            item.confidence,
            { nodeId: item.id },
            tmBuildSynapsePerceptionDetail("central signal", item)
        ));
    });

    const bridgeItems = (data?.bridge_nodes || []).slice(0, 5);
    const bridgeEdgeItems = (data?.bridge_edges || []).slice(0, 3);

    bridgeItems.forEach((item) => {
        bridges?.appendChild(tmCreatePerceptionItem(
            item.label,
            `${item.galaxy} · degree ${item.degree}`,
            item.bridge_reason || item.description,
            item.confidence,
            { nodeId: item.id },
            tmBuildSynapsePerceptionDetail("bridge candidate", item)
        ));
    });

    bridgeEdgeItems.forEach((item) => {
        bridges?.appendChild(tmCreatePerceptionItem(
            `${item.source_label} → ${item.target_label}`,
            `${item.source_galaxy} → ${item.target_galaxy} · ${item.type}`,
            item.explanation,
            item.confidence,
            { sourceId: item.source, targetId: item.target },
            tmBuildSynapsePerceptionDetail("bridge relationship", item)
        ));
    });

    (data?.limitations || []).forEach((text) => {
        limitations?.appendChild(tmCreatePerceptionItem(
            "Caution",
            "analysis limitation",
            text,
            "tentative"
        ));
    });

    if (limitations && !limitations.children.length) {
        limitations.appendChild(tmCreatePerceptionItem(
            "No major limitations reported",
            "analysis status",
            "The backend did not return caveats for this map snapshot.",
            "moderate"
        ));
    }
}

async function tmAnalyzeSynapseMap() {
    const button = document.getElementById("synapse-analyze-btn");
    const panel = document.getElementById("synapse-perception-panel");
    const overview = document.getElementById("synapse-perception-overview");

    if (button) {
        button.disabled = true;
        button.textContent = "Analyzing…";
    }

    if (panel) panel.classList.remove("hidden");
    if (overview) overview.textContent = "Reading Synapse analysis without mutation…";

    try {
        const response = await fetch(tmSynapseAnalysisEndpoint());

        if (!response.ok) {
            throw new Error(`Synapse analysis returned HTTP ${response.status}`);
        }

        const data = await response.json();
        window.__synapseMapState.analysis = data;
        tmRenderSynapsePerception(data);
    } catch (error) {
        console.error("Synapse perception analysis failed:", error);
        if (overview) {
            overview.textContent = `Synapse perception failed: ${error.message}`;
        }
    } finally {
        if (button) {
            button.disabled = false;
            button.textContent = "Analyze Map";
        }
    }
}

function tmInstallSynapsePerceptionPanel() {
    const button = document.getElementById("synapse-analyze-btn");
    if (!button || button.dataset.tmPerceptionInstalled === "true") return;

    button.dataset.tmPerceptionInstalled = "true";
    button.addEventListener("click", tmAnalyzeSynapseMap);
}

document.addEventListener("DOMContentLoaded", tmInstallSynapsePerceptionPanel);
setTimeout(tmInstallSynapsePerceptionPanel, 500);
setTimeout(tmInstallSynapsePerceptionPanel, 1500);

// --- End Technemachina Synapse Perception Frontend Panel ---


// --- Technemachina Synapse Perception Frontend Panel v0.3.0b ---

function tmSynapseAnalysisEndpoint() {
    return window.location.protocol === "file:"
        ? "http://127.0.0.1:8000/synapse/analysis"
        : "http://127.0.0.1:8000/synapse/analysis";
}

function tmClearElement(element) {
    if (!element) return;
    while (element.firstChild) element.removeChild(element.firstChild);
}

function tmCreatePerceptionItem(title, meta, body, confidence) {
    const item = document.createElement("div");
    item.className = "synapse-perception-item";

    const top = document.createElement("div");
    top.className = "synapse-perception-item-top";

    const titleEl = document.createElement("strong");
    titleEl.textContent = title || "Unnamed signal";

    const confidenceEl = document.createElement("span");
    confidenceEl.className = `synapse-confidence synapse-confidence-${String(confidence || "unknown").toLowerCase()}`;
    confidenceEl.textContent = confidence || "unknown";

    top.appendChild(titleEl);
    top.appendChild(confidenceEl);

    const metaEl = document.createElement("p");
    metaEl.className = "synapse-perception-meta";
    metaEl.textContent = meta || "";

    const bodyEl = document.createElement("p");
    bodyEl.className = "synapse-perception-body";
    bodyEl.textContent = body || "";

    item.appendChild(top);
    if (meta) item.appendChild(metaEl);
    if (body) item.appendChild(bodyEl);

    return item;
}

function tmRenderSynapsePerception(data) {
    const panel = document.getElementById("synapse-perception-panel");
    const title = document.getElementById("synapse-perception-title");
    const badge = document.getElementById("synapse-perception-badge");
    const overview = document.getElementById("synapse-perception-overview");
    const galaxies = document.getElementById("synapse-perception-galaxies");
    const central = document.getElementById("synapse-perception-central");
    const bridges = document.getElementById("synapse-perception-bridges");
    const limitations = document.getElementById("synapse-perception-limitations");

    if (!panel) return;

    panel.classList.remove("hidden");

    if (title) {
        title.textContent = `Read-only analysis ${data?.meta?.analysis_version || ""}`.trim();
    }

    if (badge) {
        badge.textContent = data?.meta?.mutation_allowed ? "Mutation enabled" : "Read-only / No mutation";
        badge.classList.toggle("danger", !!data?.meta?.mutation_allowed);
    }

    if (overview) {
        overview.textContent = data?.overview?.summary || "No overview returned.";
    }

    tmClearElement(galaxies);
    tmClearElement(central);
    tmClearElement(bridges);
    tmClearElement(limitations);

    (data?.galaxy_summaries || []).slice(0, 6).forEach((item) => {
        galaxies?.appendChild(tmCreatePerceptionItem(
            item.galaxy,
            `nodes ${item.node_count} · edges ${item.edge_touch_count} · coverage ${item.edge_coverage}`,
            item.summary,
            item.confidence
        ));
    });

    (data?.central_nodes || []).slice(0, 6).forEach((item) => {
        central?.appendChild(tmCreatePerceptionItem(
            item.label,
            `${item.galaxy} · degree ${item.degree} · weighted ${item.weighted_degree}`,
            item.description,
            item.confidence,
            { nodeId: item.id },
            tmBuildSynapsePerceptionDetail("central signal", item)
        ));
    });

    const bridgeItems = (data?.bridge_nodes || []).slice(0, 5);
    const bridgeEdgeItems = (data?.bridge_edges || []).slice(0, 3);

    bridgeItems.forEach((item) => {
        bridges?.appendChild(tmCreatePerceptionItem(
            item.label,
            `${item.galaxy} · degree ${item.degree}`,
            item.bridge_reason || item.description,
            item.confidence,
            { nodeId: item.id },
            tmBuildSynapsePerceptionDetail("bridge candidate", item)
        ));
    });

    bridgeEdgeItems.forEach((item) => {
        bridges?.appendChild(tmCreatePerceptionItem(
            `${item.source_label} → ${item.target_label}`,
            `${item.source_galaxy} → ${item.target_galaxy} · ${item.type}`,
            item.explanation,
            item.confidence,
            { sourceId: item.source, targetId: item.target },
            tmBuildSynapsePerceptionDetail("bridge relationship", item)
        ));
    });

    (data?.limitations || []).forEach((text) => {
        limitations?.appendChild(tmCreatePerceptionItem(
            "Caution",
            "analysis limitation",
            text,
            "tentative"
        ));
    });

    if (limitations && !limitations.children.length) {
        limitations.appendChild(tmCreatePerceptionItem(
            "No major limitations reported",
            "analysis status",
            "The backend did not return caveats for this map snapshot.",
            "moderate"
        ));
    }
}

async function tmAnalyzeSynapseMap() {
    const button = document.getElementById("synapse-analyze-btn");
    const panel = document.getElementById("synapse-perception-panel");
    const overview = document.getElementById("synapse-perception-overview");

    if (button) {
        button.disabled = true;
        button.textContent = "Analyzing…";
    }

    if (panel) panel.classList.remove("hidden");
    if (overview) overview.textContent = "Reading Synapse analysis without mutation…";

    try {
        const response = await fetch(tmSynapseAnalysisEndpoint());

        if (!response.ok) {
            throw new Error(`Synapse analysis returned HTTP ${response.status}`);
        }

        const data = await response.json();
        window.__synapseMapState.analysis = data;
        tmRenderSynapsePerception(data);
    } catch (error) {
        console.error("Synapse perception analysis failed:", error);
        if (overview) {
            overview.textContent = `Synapse perception failed: ${error.message}`;
        }
    } finally {
        if (button) {
            button.disabled = false;
            button.textContent = "Analyze Map";
        }
    }
}

function tmInstallSynapsePerceptionPanel() {
    const button = document.getElementById("synapse-analyze-btn");
    if (!button || button.dataset.tmPerceptionInstalled === "true") return;

    button.dataset.tmPerceptionInstalled = "true";
    button.addEventListener("click", tmAnalyzeSynapseMap);
}

document.addEventListener("DOMContentLoaded", tmInstallSynapsePerceptionPanel);
setTimeout(tmInstallSynapsePerceptionPanel, 500);
setTimeout(tmInstallSynapsePerceptionPanel, 1500);

// --- End Technemachina Synapse Perception Frontend Panel ---


// --- Technemachina Synapse Perception Card Click Repair v0.3.5r ---

function tmSynapseBuildDetailFromRepair(kind, item) {
    const data = item || {};

    return {
        kind,
        title: data.label || data.source_label && data.target_label
            ? `${data.source_label} → ${data.target_label}`
            : "Unnamed perception result",
        confidence: data.confidence || "unknown",
        galaxy: data.galaxy || data.source_galaxy,
        degree: data.degree,
        weightedDegree: data.weighted_degree,
        nodeId: data.id,
        sourceId: data.source,
        targetId: data.target,
        sourceLabel: data.source_label,
        targetLabel: data.target_label,
        relationType: data.type,
        reason: data.bridge_reason || data.explanation,
        description: data.description
    };
}

function tmSynapseRepairClickableCard(card, detail, action) {
    if (!card || card.dataset.tmClickRepair === "installed") return;

    card.dataset.tmClickRepair = "installed";
    card.classList.add("synapse-perception-clickable");
    card.title = "Click to inspect this perception result";

    card.addEventListener("click", event => {
        event.preventDefault();
        event.stopPropagation();

        if (typeof tmSetActiveSynapsePerceptionCard === "function") {
            tmSetActiveSynapsePerceptionCard(card);
        } else {
            document.querySelectorAll(".synapse-perception-item-active").forEach(item => {
                item.classList.remove("synapse-perception-item-active");
            });
            card.classList.add("synapse-perception-item-active");
        }

        if (typeof tmRenderSynapsePerceptionDetail === "function") {
            tmRenderSynapsePerceptionDetail(detail);
        }

        if (typeof action === "function") {
            action();
        }
    });
}

function tmRepairSynapsePerceptionCardLinks(data) {
    const safe = data || window.__synapseMapState?.analysis || {};

    const centralCards = Array.from(
        document.querySelectorAll("#synapse-perception-central .synapse-perception-item")
    );

    centralCards.forEach((card, index) => {
        const item = safe.central_nodes?.[index];
        if (!item) return;

        const detail = tmSynapseBuildDetailFromRepair("central signal", item);
        card.dataset.synapseNodeId = item.id || "";

        tmSynapseRepairClickableCard(card, detail, () => {
            if (typeof tmFocusSynapsePerceptionNode === "function") {
                tmFocusSynapsePerceptionNode(item.id);
            }
        });
    });

    const bridgeCards = Array.from(
        document.querySelectorAll("#synapse-perception-bridges .synapse-perception-item")
    );

    const bridgeNodes = safe.bridge_nodes || [];
    const bridgeEdges = safe.bridge_edges || [];

    bridgeCards.forEach((card, index) => {
        if (index < bridgeNodes.length) {
            const item = bridgeNodes[index];
            const detail = tmSynapseBuildDetailFromRepair("bridge candidate", item);
            card.dataset.synapseNodeId = item.id || "";

            tmSynapseRepairClickableCard(card, detail, () => {
                if (typeof tmFocusSynapsePerceptionNode === "function") {
                    tmFocusSynapsePerceptionNode(item.id);
                }
            });

            return;
        }

        const edgeIndex = index - bridgeNodes.length;
        const item = bridgeEdges[edgeIndex];
        if (!item) return;

        const detail = tmSynapseBuildDetailFromRepair("bridge relationship", item);
        card.dataset.synapseSourceId = item.source || "";
        card.dataset.synapseTargetId = item.target || "";

        tmSynapseRepairClickableCard(card, detail, () => {
            if (typeof tmFocusSynapseBridgePath === "function") {
                tmFocusSynapseBridgePath(item.source, item.target);
            } else if (typeof tmFocusSynapsePerceptionNode === "function") {
                tmFocusSynapsePerceptionNode(item.source || item.target);
            }
        });
    });
}

(function tmInstallSynapsePerceptionRenderRepair() {
    const install = () => {
        if (typeof tmRenderSynapsePerception !== "function") return false;
        if (tmRenderSynapsePerception.__tmClickRepairWrapped) return true;

        const originalRender = tmRenderSynapsePerception;

        tmRenderSynapsePerception = function repairedSynapsePerceptionRender(data) {
            const result = originalRender.call(this, data);

            window.__synapseMapState = window.__synapseMapState || {};
            window.__synapseMapState.analysis = data;

            setTimeout(() => tmRepairSynapsePerceptionCardLinks(data), 0);
            setTimeout(() => tmRepairSynapsePerceptionCardLinks(data), 100);

            return result;
        };

        tmRenderSynapsePerception.__tmClickRepairWrapped = true;
        return true;
    };

    if (!install()) {
        setTimeout(install, 500);
        setTimeout(install, 1500);
    }
})();

// --- End Technemachina Synapse Perception Card Click Repair ---


// --- Technemachina Detail Drawer Back-to-Map Repair v0.3.6b ---

function tmSynapseFindMapAnchor() {
    return (
        document.getElementById("synapse-map-canvas") ||
        document.getElementById("synapse-map") ||
        document.querySelector(".synapse-map") ||
        document.querySelector(".synapse-layout")
    );
}

function tmSynapseReturnToMap() {
    const map = tmSynapseFindMapAnchor();

    if (map && typeof map.scrollIntoView === "function") {
        map.scrollIntoView({
            behavior: "smooth",
            block: "center",
            inline: "nearest"
        });
    }

    if (typeof tmUpdateSynapseCompanionContext === "function") {
        tmUpdateSynapseCompanionContext();
    }
}

function tmSynapseCloseDetailDrawer() {
    const drawer = document.getElementById("synapse-perception-detail-drawer");
    const title = document.getElementById("synapse-perception-detail-title");
    const confidence = document.getElementById("synapse-perception-detail-confidence");
    const body = document.getElementById("synapse-perception-detail-body");

    if (title) title.textContent = "No detail selected";
    if (confidence) confidence.textContent = "Select a perception card";
    if (body) body.textContent = "Click a Central Signal or Bridge Candidate to inspect why it matters.";

    document
        .querySelectorAll(".synapse-perception-item-active")
        .forEach(card => card.classList.remove("synapse-perception-item-active"));

    if (window.__synapseMapState) {
        window.__synapseMapState.activePerceptionCard = null;
    }

    tmSynapseReturnToMap();
}

function tmInstallSynapseBackToMapControls() {
    const back = document.getElementById("synapse-detail-back-to-map");
    const close = document.getElementById("synapse-detail-close");

    if (back && back.dataset.tmBackInstalled !== "true") {
        back.dataset.tmBackInstalled = "true";
        back.addEventListener("click", tmSynapseReturnToMap);
    }

    if (close && close.dataset.tmCloseInstalled !== "true") {
        close.dataset.tmCloseInstalled = "true";
        close.addEventListener("click", tmSynapseCloseDetailDrawer);
    }
}

document.addEventListener("DOMContentLoaded", tmInstallSynapseBackToMapControls);
setTimeout(tmInstallSynapseBackToMapControls, 500);
setTimeout(tmInstallSynapseBackToMapControls, 1500);

// --- End Technemachina Detail Drawer Back-to-Map Repair ---


// --- Technemachina Synapse Map-Only View Toggle v0.3.6c ---

function tmSynapseSetMapOnlyMode(enabled) {
    const root =
        document.querySelector(".synapse-panel") ||
        document.querySelector(".synapse-view") ||
        document.body;

    if (!root) return;

    root.classList.toggle("synapse-map-only-mode", !!enabled);

    if (window.__synapseMapState) {
        window.__synapseMapState.mapOnlyMode = !!enabled;
        window.__synapseMapState.activePerceptionCard = null;
    }

    document
        .querySelectorAll(".synapse-perception-item-active")
        .forEach(card => card.classList.remove("synapse-perception-item-active"));

    const title = document.getElementById("synapse-perception-detail-title");
    const confidence = document.getElementById("synapse-perception-detail-confidence");
    const body = document.getElementById("synapse-perception-detail-body");

    if (enabled) {
        if (title) title.textContent = "Map only";
        if (confidence) confidence.textContent = "Perception cards hidden";
        if (body) body.textContent = "The Synapse Map is now the primary view. Cards are hidden until Show Cards is selected.";
    }

    if (typeof tmSynapseReturnToMap === "function") {
        tmSynapseReturnToMap();
    } else {
        const map =
            document.getElementById("synapse-map-canvas") ||
            document.querySelector(".synapse-layout");

        if (map && typeof map.scrollIntoView === "function") {
            map.scrollIntoView({ behavior: "smooth", block: "center" });
        }
    }

    if (typeof tmUpdateSynapseCompanionContext === "function") {
        tmUpdateSynapseCompanionContext();
    }
}

function tmInstallSynapseMapOnlyControls() {
    const mapOnly = document.getElementById("synapse-map-only-toggle");
    const showCards = document.getElementById("synapse-show-cards-toggle");

    if (mapOnly && mapOnly.dataset.tmMapOnlyInstalled !== "true") {
        mapOnly.dataset.tmMapOnlyInstalled = "true";
        mapOnly.addEventListener("click", () => tmSynapseSetMapOnlyMode(true));
    }

    if (showCards && showCards.dataset.tmShowCardsInstalled !== "true") {
        showCards.dataset.tmShowCardsInstalled = "true";
        showCards.addEventListener("click", () => tmSynapseSetMapOnlyMode(false));
    }
}

document.addEventListener("DOMContentLoaded", tmInstallSynapseMapOnlyControls);
setTimeout(tmInstallSynapseMapOnlyControls, 500);
setTimeout(tmInstallSynapseMapOnlyControls, 1500);

// --- End Technemachina Synapse Map-Only View Toggle ---


// --- Technemachina Synapse Map-Only View Toggle v0.3.6c ---

function tmSynapseSetMapOnlyMode(enabled) {
    const root =
        document.querySelector(".synapse-panel") ||
        document.querySelector(".synapse-view") ||
        document.body;

    if (!root) return;

    root.classList.toggle("synapse-map-only-mode", !!enabled);

    if (window.__synapseMapState) {
        window.__synapseMapState.mapOnlyMode = !!enabled;
        window.__synapseMapState.activePerceptionCard = null;
    }

    document
        .querySelectorAll(".synapse-perception-item-active")
        .forEach(card => card.classList.remove("synapse-perception-item-active"));

    const title = document.getElementById("synapse-perception-detail-title");
    const confidence = document.getElementById("synapse-perception-detail-confidence");
    const body = document.getElementById("synapse-perception-detail-body");

    if (enabled) {
        if (title) title.textContent = "Map only";
        if (confidence) confidence.textContent = "Perception cards hidden";
        if (body) body.textContent = "The Synapse Map is now the primary view. Cards are hidden until Show Cards is selected.";
    }

    if (typeof tmSynapseReturnToMap === "function") {
        tmSynapseReturnToMap();
    } else {
        const map =
            document.getElementById("synapse-map-canvas") ||
            document.querySelector(".synapse-layout");

        if (map && typeof map.scrollIntoView === "function") {
            map.scrollIntoView({ behavior: "smooth", block: "center" });
        }
    }

    if (typeof tmUpdateSynapseCompanionContext === "function") {
        tmUpdateSynapseCompanionContext();
    }
}

function tmInstallSynapseMapOnlyControls() {
    const mapOnly = document.getElementById("synapse-map-only-toggle");
    const showCards = document.getElementById("synapse-show-cards-toggle");

    if (mapOnly && mapOnly.dataset.tmMapOnlyInstalled !== "true") {
        mapOnly.dataset.tmMapOnlyInstalled = "true";
        mapOnly.addEventListener("click", () => tmSynapseSetMapOnlyMode(true));
    }

    if (showCards && showCards.dataset.tmShowCardsInstalled !== "true") {
        showCards.dataset.tmShowCardsInstalled = "true";
        showCards.addEventListener("click", () => tmSynapseSetMapOnlyMode(false));
    }
}

document.addEventListener("DOMContentLoaded", tmInstallSynapseMapOnlyControls);
setTimeout(tmInstallSynapseMapOnlyControls, 500);
setTimeout(tmInstallSynapseMapOnlyControls, 1500);

// --- End Technemachina Synapse Map-Only View Toggle ---


// --- Technemachina Synapse Museum View Activation v0.3.6d ---
function tmActivateSynapseMuseumView() {
    document.body.classList.add("synapse-museum-view-active");

    if (window.__synapseMapState) {
        if (typeof window.__synapseMapState.zoom !== "number") {
            window.__synapseMapState.zoom = 0.32;
        }
        if (typeof window.__synapseMapState.rotation !== "number") {
            window.__synapseMapState.rotation = 0;
        }
        if (typeof window.__synapseMapState.autoRotate !== "boolean") {
            window.__synapseMapState.autoRotate = true;
        }
    }

    if (typeof drawSynapseMap === "function") {
        drawSynapseMap();
    }
}

document.addEventListener("DOMContentLoaded", tmActivateSynapseMuseumView);
setTimeout(tmActivateSynapseMuseumView, 500);
setTimeout(tmActivateSynapseMuseumView, 1500);
// --- End Technemachina Synapse Museum View Activation ---



// --- Technemachina True Museum Distance Override v0.3.6e ---

function tmApplyTrueMuseumDistance(force = false) {
    if (!window.__synapseMapState) return;

    const state = window.__synapseMapState;

    if (force || !state.__tmTrueMuseumDistanceApplied) {
        state.zoom = 0.32;
        state.panX = 0;
        state.panY = 0;
        state.rotation = state.rotation || 0;
        state.autoRotate = true;
        state.__tmTrueMuseumDistanceApplied = true;
    }

    document.body.classList.add("synapse-museum-view-active");

    if (typeof drawSynapseMap === "function") {
        drawSynapseMap();
    }

    if (typeof updateSynapseZoomLabel === "function") {
        updateSynapseZoomLabel();
    }

    const reset = document.getElementById("synapse-zoom-reset-btn");
    if (reset) {
        reset.textContent = `${Math.round((state.zoom || 0.32) * 100)}%`;
    }
}

function tmInstallTrueMuseumDistance() {
    tmApplyTrueMuseumDistance(false);

    const reset = document.getElementById("synapse-zoom-reset-btn");
    if (reset && reset.dataset.tmMuseumResetBound !== "true") {
        reset.dataset.tmMuseumResetBound = "true";
        reset.addEventListener("click", () => {
            setTimeout(() => tmApplyTrueMuseumDistance(true), 20);
        });
    }
}

document.addEventListener("DOMContentLoaded", tmInstallTrueMuseumDistance);
setTimeout(tmInstallTrueMuseumDistance, 500);
setTimeout(tmInstallTrueMuseumDistance, 1500);
setTimeout(tmInstallTrueMuseumDistance, 3000);

// --- End Technemachina True Museum Distance Override ---



// --- Technemachina Visible Ambient Orbit v0.3.6f ---

function tmSynapseSetAmbientOrbitDefaults() {
    if (!window.__synapseMapState) return;

    const state = window.__synapseMapState;

    // Museum-trance orbit: visible, smooth, not frantic.
    // About one full turn per 65-85 seconds depending on frame timing.
    state.ambientOrbitSpeed = 0.000085;
    state.autoRotate = true;
    state.__tmAmbientOrbitEnabled = true;

    document.body.classList.add("synapse-museum-view-active");
}

function tmSynapseAmbientOrbitLoop(timestamp) {
    if (!window.__synapseMapState) {
        requestAnimationFrame(tmSynapseAmbientOrbitLoop);
        return;
    }

    const state = window.__synapseMapState;

    if (!state.__tmLastAmbientOrbitTimestamp) {
        state.__tmLastAmbientOrbitTimestamp = timestamp;
    }

    const delta = Math.min(48, Math.max(0, timestamp - state.__tmLastAmbientOrbitTimestamp));
    state.__tmLastAmbientOrbitTimestamp = timestamp;

    if (
        state.__tmAmbientOrbitEnabled &&
        state.autoRotate !== false &&
        !state.isDragging &&
        !state.focusTween
    ) {
        state.rotation = (state.rotation || 0) + delta * (state.ambientOrbitSpeed || 0.000085);

        if (typeof drawSynapseMap === "function") {
            drawSynapseMap();
        }
    }

    requestAnimationFrame(tmSynapseAmbientOrbitLoop);
}

function tmInstallVisibleAmbientOrbit() {
    tmSynapseSetAmbientOrbitDefaults();

    if (!window.__tmSynapseAmbientOrbitLoopStarted) {
        window.__tmSynapseAmbientOrbitLoopStarted = true;
        requestAnimationFrame(tmSynapseAmbientOrbitLoop);
    }

    const lockBtn = document.getElementById("synapse-orbit-lock-btn");
    if (lockBtn && lockBtn.dataset.tmAmbientOrbitLabel !== "true") {
        lockBtn.dataset.tmAmbientOrbitLabel = "true";
        lockBtn.textContent = "Lock Orbit";
    }
}

document.addEventListener("DOMContentLoaded", tmInstallVisibleAmbientOrbit);
setTimeout(tmInstallVisibleAmbientOrbit, 500);
setTimeout(tmInstallVisibleAmbientOrbit, 1500);
setTimeout(tmInstallVisibleAmbientOrbit, 3000);

// --- End Technemachina Visible Ambient Orbit ---


// --- Technemachina Synapse Companion Console Shell Repair ---

function tmSynapseCompanionSelectedLabel() {
    const selected = window.__synapseMapState?.selected;
    if (selected?.item) {
        if (typeof tmSynapseNodeTitle === "function") {
            return tmSynapseNodeTitle(selected.item);
        }
        return selected.item.title || selected.item.label || selected.item.id || "Selected signal";
    }

    const active = window.__synapseMapState?.activePerceptionCard;
    if (active?.title) return active.title;

    return "No signal selected";
}

function tmUpdateSynapseCompanionContext() {
    const context = document.getElementById("synapse-companion-context");
    if (!context) return;
    context.textContent = `Looking at: ${tmSynapseCompanionSelectedLabel()}`;
}

function tmAppendSynapseCompanionMessage(role, text) {
    const messages = document.getElementById("synapse-companion-messages");
    if (!messages) return;

    const item = document.createElement("div");
    item.className = `synapse-companion-message ${role || "companion"}`;
    item.textContent = text || "";
    messages.appendChild(item);
    messages.scrollTop = messages.scrollHeight;
}

function tmSynapseCompanionLocalReply(prompt) {
    const selected = window.__synapseMapState?.selected?.item || null;
    const promptText = String(prompt || "").trim();

    if (/reset view/i.test(promptText)) {
        if (typeof resetSynapseView === "function") resetSynapseView();
        if (typeof tmApplyTrueMuseumDistance === "function") tmApplyTrueMuseumDistance(true);
        return "I reset the view to the museum-distance constellation. This was a view action only.";
    }

    if (/explain selected|this star|this signal/i.test(promptText)) {
        if (!selected) {
            return "No star is selected yet. Select a star, then I can explain what it is and where its associations lead.";
        }

        const title = typeof tmSynapseNodeTitle === "function" ? tmSynapseNodeTitle(selected) : selected.title || selected.label || selected.id;
        const subtitle = typeof tmSynapseNodeSubtitle === "function" ? tmSynapseNodeSubtitle(selected) : selected.type || "Synapse signal";
        const description = typeof tmSynapseNodeDescription === "function" ? tmSynapseNodeDescription(selected) : selected.description || "No description is available yet.";

        return `${title}: ${subtitle}. ${description} Would you like to continue down its associations?`;
    }

    if (/association|associations|continue/i.test(promptText)) {
        if (!selected) return "Select a star first, then I can trace its visible associations.";
        return "Association tracing is staged for v0.3.7. I can see the selected signal; next we wire connected-star listing.";
    }

    if (/summarize galaxy|galaxy/i.test(promptText)) {
        return "I’m answering from Synapse Map context. Galaxy summarization will connect to the perception layer next.";
    }

    if (/suggest next|next/i.test(promptText)) {
        return "I suggest using Map Only to view the constellation, then selecting a central signal and following a bridge candidate.";
    }

    return "I’m answering from the Synapse mini-console. I can explain selected stars, guide inspection, and prepare safe view actions. Memory mutation remains Oracle-gated.";
}

function tmHandleSynapseCompanionSubmit(prompt) {
    const text = String(prompt || "").trim();
    if (!text) return;

    tmAppendSynapseCompanionMessage("oracle", text);
    tmAppendSynapseCompanionMessage("companion", tmSynapseCompanionLocalReply(text));
    tmUpdateSynapseCompanionContext();
}

function tmInstallSynapseCompanionConsole() {
    const form = document.getElementById("synapse-companion-form");
    const input = document.getElementById("synapse-companion-input");

    if (form && input && form.dataset.tmCompanionInstalled !== "true") {
        form.dataset.tmCompanionInstalled = "true";
        form.addEventListener("submit", event => {
            event.preventDefault();
            const value = input.value;
            input.value = "";
            tmHandleSynapseCompanionSubmit(value);
        });
    }

    document.querySelectorAll("[data-companion-prompt]").forEach(button => {
        if (button.dataset.tmCompanionInstalled === "true") return;
        button.dataset.tmCompanionInstalled = "true";
        button.addEventListener("click", () => {
            tmHandleSynapseCompanionSubmit(button.dataset.companionPrompt || button.textContent);
        });
    });

    tmUpdateSynapseCompanionContext();
}

document.addEventListener("DOMContentLoaded", tmInstallSynapseCompanionConsole);
setTimeout(tmInstallSynapseCompanionConsole, 500);
setTimeout(tmInstallSynapseCompanionConsole, 1500);
setInterval(tmUpdateSynapseCompanionContext, 1200);

// --- End Technemachina Synapse Companion Console Shell Repair ---
