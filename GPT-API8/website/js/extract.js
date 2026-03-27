(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const inputEl = $("input_text");
  const qsEl = $("qs_output");
  const explainEl = $("explain_output");
  const statusEl = $("status");
  const actionMetaEl = $("action_meta");
  const objectsMetaEl = $("objects_meta");
  const relationsMetaEl = $("relations_meta");
  const genTimeMetaEl = $("gen_time_meta");
  const genTokensMetaEl = $("gen_tokens_meta");
  const sessionTokensMetaEl = $("session_tokens_meta");
  const generateBtn = $("generate_btn");
  const approveBtn = $("approve_btn");
  const finalizeBtn = $("finalize_btn");
  const navFinalizeBtn = $("nav_finalize_btn");
  const clearSessionBtn = $("clear_session_btn");
  const showNewContextToggle = $("showNewContextToggle");
  const resetViewBtn = $("resetViewBtn");
  const kgHint = $("kgHint");
  const toggleOutputsBtn = $("toggleOutputsBtn");
  const outputsPanel = $("outputsPanel");

  let cy = null;
  let graphOldRows = [];
  let graphNewRows = [];
  let sessionId = localStorage.getItem("wikibase_extractor_session_id") || "";
  let lastProposalId = localStorage.getItem("wikibase_extractor_last_proposal_id") || null;
  let approvedRows = [];

  function updateHint() {
    if (!kgHint || !cy) {
      return;
    }
    kgHint.textContent = `Visible: ${cy.nodes(":visible").length} nodes, ${cy.edges(":visible").length} edges.`;
  }

  function applyGraphVisibility() {
    if (!cy) {
      return;
    }

    const showFullGraph = !!showNewContextToggle?.checked;
    cy.resize();
    if (showFullGraph) {
      cy.elements().removeClass("cy-hidden");
      cy.fit(cy.elements(), 20);
      updateHint();
      if (cy.elements(":visible").length === 0) {
        cy.elements().removeClass("cy-hidden");
        cy.fit(cy.elements(), 20);
        updateHint();
      }
      return;
    }

    const newEdges = cy.edges('[status="new"]');
    const endpoints = newEdges.connectedNodes();
    const newNodes = cy.nodes('[status="new"]');
    const existingEdgesOnNewNodes = newNodes.connectedEdges('[status="existing"]');
    const visible = newEdges.union(endpoints).union(newNodes).union(existingEdgesOnNewNodes);
    if (visible.length === 0) {
      cy.elements().removeClass("cy-hidden");
      cy.fit(cy.elements(), 20);
      updateHint();
      return;
    }

    cy.elements().addClass("cy-hidden");
    visible.removeClass("cy-hidden");
    cy.fit(cy.elements(":visible"), 20);
    updateHint();
    if (cy.elements(":visible").length === 0) {
      cy.elements().removeClass("cy-hidden");
      cy.fit(cy.elements(), 20);
      updateHint();
    }
  }

  function renderGraph(oldArr, newArr) {
    const container = $("cy");
    const shared = window.TriExtractGraph?.renderGraph;
    if (!container || !shared) {
      if (kgHint) {
        kgHint.textContent = "Graph library not loaded.";
      }
      return;
    }

    cy = shared(cy, container, oldArr || [], newArr || [], true);
    if (!cy) {
      if (kgHint) {
        kgHint.textContent = "Graph library not loaded.";
      }
      return;
    }

    window.__triExtractCy = cy;
    cy.one("layoutstop", () => requestAnimationFrame(() => applyGraphVisibility()));
    applyGraphVisibility();

    const bb = cy.elements().boundingBox();
    if (cy.nodes().length > 0 && bb && bb.w === 0 && bb.h === 0 && window.TriExtractGraph?.relayout) {
      window.TriExtractGraph.relayout(cy)?.one?.("layoutstop", () => requestAnimationFrame(() => applyGraphVisibility()));
    }
  }

  function setStatus(message, cls = "") {
    const text = (message || "").trim() || "Idle";
    statusEl.textContent = text;
    statusEl.className = "status" + (cls ? ` ${cls}` : "");
  }

  const isFile = window.location.protocol === "file:";
  if (isFile) {
    setStatus(
      "Open via the FastAPI server (run `python app.py` and browse to `http://127.0.0.1:8000/website/pages/start.html`).",
      "warn"
    );
    generateBtn.disabled = true;
    approveBtn.disabled = true;
    finalizeBtn.disabled = true;
    navFinalizeBtn.disabled = true;
  }

  function setMeta() {
    const itemSet = new Set();
    for (const row of approvedRows) {
      if (row && typeof row === "object" && row.item != null) {
        itemSet.add(String(row.item));
      }
    }
    objectsMetaEl.textContent = String(itemSet.size);
    relationsMetaEl.textContent = String(approvedRows.length);
  }

  function setAction(message) {
    actionMetaEl.textContent = message || "—";
  }

  function asNonNegativeInt(value) {
    const number = Number(value);
    return Number.isFinite(number) && number > 0 ? Math.trunc(number) : 0;
  }

  function formatGenerationTime(seconds) {
    const value = Number(seconds);
    if (!Number.isFinite(value) || value < 0) {
      return "—";
    }
    if (value < 1) {
      return `${Math.round(value * 1000)} ms`;
    }
    return `${value.toFixed(2)} s`;
  }

  function setGenerationMeta(generationSeconds, generationTokens, sessionTokensTotal) {
    genTimeMetaEl.textContent = formatGenerationTime(generationSeconds);
    genTokensMetaEl.textContent = asNonNegativeInt(generationTokens).toLocaleString();
    sessionTokensMetaEl.textContent = asNonNegativeInt(sessionTokensTotal).toLocaleString();
  }

  function errorMessage(error) {
    return error && error.message ? error.message : String(error);
  }

  async function runWithStatus(startMessage, startAction, failAction, requestFn) {
    setStatus(startMessage, "warn");
    setAction(startAction);
    try {
      return await requestFn();
    } catch (error) {
      setStatus(`Error: ${errorMessage(error)}`, "err");
      setAction(failAction);
      throw error;
    }
  }

  async function postJson(url, payload, fallbackMessage) {
    if (isFile) {
      throw new Error("This page must be opened via the FastAPI server (not as a local file).");
    }
    const response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || data.error || fallbackMessage);
    }
    return data;
  }

  function persistSession() {
    if (sessionId) {
      localStorage.setItem("wikibase_extractor_session_id", sessionId);
    }
  }

  function persistLastProposalId() {
    if (lastProposalId) {
      localStorage.setItem("wikibase_extractor_last_proposal_id", lastProposalId);
    } else {
      localStorage.removeItem("wikibase_extractor_last_proposal_id");
    }
  }

  async function hydrateSessionTokenTotal() {
    if (!sessionId) {
      return;
    }

    try {
      const response = await fetch(`/api/state/${encodeURIComponent(sessionId)}`);
      if (!response.ok) {
        return;
      }
      const data = await response.json();
      if (data && data.exists === false) {
        localStorage.removeItem("wikibase_extractor_session_id");
        localStorage.removeItem("wikibase_extractor_last_proposal_id");
        sessionId = "";
        lastProposalId = null;
        setStatus("Session expired (server restarted). Start a new session.", "warn");
        return;
      }
      setGenerationMeta(null, 0, data.token_usage_total);
    } catch {
    }
  }

  function clearProposalState() {
    lastProposalId = null;
    persistLastProposalId();
    approveBtn.disabled = true;
    setMeta();
  }

  const minRelevanceForUi = 0.5;

  function formatReasoningReport(report) {
    if (!report || typeof report !== "object") {
      return "No reasoning report available.";
    }

    const summary = report.summary || {};
    const changes = Array.isArray(report.proposed_changes) ? report.proposed_changes : [];
    const visibleChanges = changes.filter((change) => change.relevance == null || change.relevance >= minRelevanceForUi);
    const hiddenCount = changes.length - visibleChanges.length;
    const warnings = Array.isArray(report.validation_warnings) ? report.validation_warnings : [];

    const lines = [];
    lines.push("Summary");
    lines.push(`- Creates: ${summary.creates ?? 0}`);
    lines.push(`- Edits: ${summary.edits ?? 0}`);
    lines.push(`- Links: ${summary.links ?? 0}`);
    lines.push(`- Deletes: ${summary.deletes ?? 0}`);
    lines.push(`- Uncertain: ${summary.uncertain ?? 0}`);
    lines.push(`- Validation warnings: ${summary.validation_warnings ?? warnings.length}`);
    lines.push("");

    if (warnings.length) {
      lines.push("Validation warnings");
      for (const warning of warnings) {
        lines.push(`- ${warning}`);
      }
      lines.push("");
    }

    lines.push("Proposed changes");
    if (hiddenCount > 0) {
      lines.push(`- (${hiddenCount} change${hiddenCount === 1 ? "" : "s"} hidden due to low relevance)`);
    }
    if (!visibleChanges.length) {
      lines.push("- None");
    } else {
      visibleChanges.forEach((change, index) => {
        lines.push(`${index + 1}. ${change.what || "Change"}`);
        lines.push(`Subject: ${change.subject || "—"}`);
        lines.push(`Statement: ${change.statement || "—"}`);
        lines.push(`Why: ${change.why || "—"}`);

        const evidence = Array.isArray(change.evidence) ? change.evidence.filter(Boolean) : [];
        if (evidence.length) {
          lines.push(`Evidence: ${evidence.join(" | ")}`);
        }
        if (change.confidence !== undefined && change.confidence !== null) {
          lines.push(`Confidence: ${change.confidence}`);
        }
        if (change.relevance !== undefined && change.relevance !== null) {
          lines.push(`Relevance: ${change.relevance}`);
        }
        if (change.needs_review) {
          lines.push(`Needs review: ${change.needs_review}`);
        }
        lines.push("");
      });
    }

    return lines.join("\n").trim();
  }

  async function generateProposal() {
    const inputText = (inputEl.value || "").trim();
    if (!inputText) {
      setStatus("Please paste some text first.", "warn");
      return;
    }

    generateBtn.disabled = true;
    approveBtn.disabled = true;
    try {
      const data = await runWithStatus(
        "Generating proposal…",
        "Generating",
        "Failed",
        () => postJson("/api/propose", {
          input_text: inputText,
          session_id: sessionId || null,
        }, "Request failed")
      );

      if (data.session_id) {
        sessionId = data.session_id;
        persistSession();
      }

      lastProposalId = data.proposal_id || null;
      persistLastProposalId();
      const patchRows = Array.isArray(data.patch_kb_json)
        ? data.patch_kb_json
        : ((data && data.diff && Array.isArray(data.diff.added_rows))
          ? data.diff.added_rows
          : (Array.isArray(data.proposal_rows_only) ? data.proposal_rows_only : []));

      qsEl.value = JSON.stringify(patchRows, null, 2);
      explainEl.value = formatReasoningReport(data.reasoning_report || {});
      approveBtn.disabled = !lastProposalId;
      finalizeBtn.disabled = !sessionId;
      if (navFinalizeBtn) {
        navFinalizeBtn.disabled = !sessionId;
      }

      graphOldRows = Array.isArray(data.base_kb_json) ? data.base_kb_json : [];
      graphNewRows = Array.isArray(data.proposed_kb_json) ? data.proposed_kb_json : [];
      renderGraph(graphOldRows, graphNewRows);
      setGenerationMeta(data.generation_seconds, data.generation_tokens, data.session_tokens_total);
      setStatus("Proposal ready. Review reasoning and click Apply to update session state.", "ok");
      setAction("Proposal generated");
      setMeta();
    } catch {
    } finally {
      generateBtn.disabled = false;
    }
  }

  async function approveProposal() {
    if (!sessionId || !lastProposalId) {
      setStatus("No proposal to approve yet.", "warn");
      return false;
    }

    let editedKbJson;
    try {
      editedKbJson = JSON.parse(qsEl.value || "[]");
      if (!Array.isArray(editedKbJson)) {
        throw new Error("Proposed Wikibase JSON must be a JSON array.");
      }
    } catch (error) {
      setStatus(`Invalid proposed JSON: ${error.message}`, "err");
      setAction("Approve failed");
      return false;
    }

    approveBtn.disabled = true;
    try {
      const data = await runWithStatus(
        "Approving proposal…",
        "Approving",
        "Approve failed",
        () => postJson("/api/approve", {
          session_id: sessionId,
          proposal_id: lastProposalId,
          edited_kb_json: editedKbJson,
        }, "Approve failed")
      );

      approvedRows = Array.isArray(data.current_kb_json) ? data.current_kb_json : [];
      inputEl.value = "";
      explainEl.value = "";
      qsEl.value = "";
      clearProposalState();
      finalizeBtn.disabled = !sessionId;
      if (navFinalizeBtn) {
        navFinalizeBtn.disabled = !sessionId;
      }
      setStatus("Approved. Cleared input/reasoning/JSON. Ready for next batch.", "ok");
      setAction("Proposal approved");
      return true;
    } catch {
      approveBtn.disabled = false;
      return false;
    } finally {
      setMeta();
    }
  }

  async function finalizeWithAppend() {
    if (lastProposalId) {
      const approved = await approveProposal();
      if (!approved) {
        return;
      }
    }
    goToFinalize();
  }

  function goToFinalize() {
    if (!sessionId) {
      setStatus("No session ID available. Generate a proposal first.", "warn");
      return;
    }
    setStatus("Opening finalize view…", "ok");
    setAction("Finalizing");
    window.location.href = `./finalize.html?session_id=${encodeURIComponent(sessionId)}`;
  }

  function isCollapsed() {
    return !outputsPanel || outputsPanel.getAttribute("data-collapsed") === "true";
  }

  function setCollapsed(collapsed) {
    if (outputsPanel) {
      outputsPanel.setAttribute("data-collapsed", collapsed ? "true" : "false");
    }
    if (toggleOutputsBtn) {
      toggleOutputsBtn.textContent = collapsed ? "Expand ▾" : "Collapse ▴";
      toggleOutputsBtn.setAttribute("aria-expanded", collapsed ? "false" : "true");
    }
  }

  showNewContextToggle?.addEventListener("change", applyGraphVisibility);
  resetViewBtn?.addEventListener("click", () => {
    if (!cy) {
      return;
    }
    if (window.TriExtractGraph?.relayout) {
      return window.TriExtractGraph.relayout(cy);
    }
    cy.resize();
    cy.fit(cy.elements(":visible"), 20);
  });

  clearSessionBtn.addEventListener("click", () => {
    localStorage.removeItem("wikibase_extractor_session_id");
    localStorage.removeItem("wikibase_extractor_last_proposal_id");
    sessionId = "";
    approvedRows = [];
    clearProposalState();
    finalizeBtn.disabled = true;
    if (navFinalizeBtn) {
      navFinalizeBtn.disabled = true;
    }
    graphOldRows = [];
    graphNewRows = [];
    renderGraph([], []);
    setStatus("Local browser session cleared. Server-side session may still exist until restart.", "warn");
    setAction("Cleared local session");
    setGenerationMeta(null, 0, 0);
    setMeta();
  });

  generateBtn.addEventListener("click", generateProposal);
  approveBtn.addEventListener("click", approveProposal);
  finalizeBtn.addEventListener("click", finalizeWithAppend);
  navFinalizeBtn?.addEventListener("click", finalizeWithAppend);

  setMeta();
  setAction("Idle");
  setStatus("Idle");
  setGenerationMeta(null, 0, 0);
  finalizeBtn.disabled = !sessionId;
  if (navFinalizeBtn) {
    navFinalizeBtn.disabled = !sessionId;
  }
  renderGraph([], []);
  hydrateSessionTokenTotal();

  setCollapsed(isCollapsed());
  toggleOutputsBtn?.addEventListener("click", () => {
    setCollapsed(!isCollapsed());
    requestAnimationFrame(() => applyGraphVisibility());
  });

  window.addEventListener("resize", () => {
    if (!cy) {
      return;
    }
    requestAnimationFrame(() => applyGraphVisibility());
  });
})();
