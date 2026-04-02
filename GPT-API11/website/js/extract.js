(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const shared = window.TriExtractShared;
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
  const navFinalizeBtn = $("nav_finalize_btn");
  const clearSessionBtn = $("clear_session_btn");
  const showNewContextToggle = $("showNewContextToggle");
  const resetViewBtn = $("resetViewBtn");
  const kgHint = $("kgHint");
  const toggleOutputsBtn = $("toggleOutputsBtn");
  const outputsPanel = $("outputsPanel");

  let cy = null;
  let sessionId = shared?.getSessionId ? shared.getSessionId() : "";
  let lastProposalId = shared?.getProposalId ? shared.getProposalId() : null;
  let lastProposalPatchSignature = "";
  let createdRows = [];
  let graphRows = { baseRows: [], previewRows: [], fullRows: [] };
  let pendingGraphPayload = null;
  let generateRequestController = null;
  let hydrateRequestController = null;

  function isAbortError(error) {
    return !!error && (
      error.name === "AbortError" ||
      String(error.message || error).toLowerCase().includes("abort")
    );
  }

  function setGraphHint(message) {
    if (kgHint) {
      kgHint.textContent = message;
    }
  }

  function graphModeLabel() {
    return showNewContextToggle?.checked ? "Full graph" : "Proposal preview";
  }

  function updateHint() {
    if (!cy) {
      return;
    }
    setGraphHint(`${graphModeLabel()}: ${cy.nodes().length} nodes, ${cy.edges().length} edges.`);
  }

  function applyGraphVisibility() {
    if (!cy) {
      return;
    }
    cy.resize();
    const elements = cy.elements();
    if (elements.length > 0) {
      cy.fit(elements, 20);
    }
    updateHint();
  }

  function canRenderGraph() {
    const container = $("cy");
    return !!container && container.isConnected && !document.hidden && container.clientWidth > 0 && container.clientHeight > 0;
  }

  function rowArray(rows) {
    return Array.isArray(rows) ? rows : [];
  }

  function graphPayload(options = {}) {
    const showFullGraph = !!showNewContextToggle?.checked;
    return {
      oldArr: graphRows.baseRows,
      newArr: showFullGraph ? graphRows.fullRows : graphRows.previewRows,
      options,
    };
  }

  function rerenderGraph(options = {}) {
    pendingGraphPayload = graphPayload(options);
    flushPendingGraphRender();
  }

  function renderGraphNow(oldArr = [], newArr = [], options = {}) {
    const container = $("cy");
    const renderSharedGraph = window.TriExtractGraph?.renderGraph;
    if (!container || !renderSharedGraph) {
      setGraphHint("Graph library not loaded.");
      return;
    }

    cy = renderSharedGraph(cy, container, oldArr, newArr, false, options);
    if (!cy) {
      setGraphHint("Graph library not loaded.");
      return;
    }

    cy.one("layoutstop", () => requestAnimationFrame(() => applyGraphVisibility()));
    applyGraphVisibility();

    const bb = cy.elements().boundingBox();
    if (!options.preservePositions && cy.nodes().length > 0 && bb && bb.w === 0 && bb.h === 0 && window.TriExtractGraph?.relayout) {
      window.TriExtractGraph.relayout(cy)?.one?.("layoutstop", () => requestAnimationFrame(() => applyGraphVisibility()));
    }
  }

  function flushPendingGraphRender() {
    if (!pendingGraphPayload) {
      return;
    }
    if (!canRenderGraph()) {
      if (document.hidden) {
        setGraphHint("Graph will refresh when this tab is active again.");
      }
      return;
    }

    const { oldArr, newArr, options } = pendingGraphPayload;
    pendingGraphPayload = null;
    renderGraphNow(oldArr, newArr, options);
  }

  function renderGraph(baseRows = [], previewRows = [], fullRowsOrOptions = previewRows, maybeOptions = {}) {
    let fullRows = previewRows;
    let options = maybeOptions;

    if (Array.isArray(fullRowsOrOptions)) {
      fullRows = fullRowsOrOptions;
    } else {
      options = fullRowsOrOptions || {};
    }

    graphRows = {
      baseRows: rowArray(baseRows),
      previewRows: rowArray(previewRows),
      fullRows: rowArray(fullRows),
    };
    rerenderGraph(options);
  }

  function setStatus(message, cls = "") {
    const text = (message || "").trim() || "Idle";
    statusEl.textContent = text;
    statusEl.className = "status" + (cls ? ` ${cls}` : "");
  }

  function setFinalizeEnabled(enabled) {
    if (!navFinalizeBtn) {
      return;
    }
    navFinalizeBtn.disabled = isFile || !enabled;
  }

  function clearValues(...elements) {
    elements.forEach((element) => {
      if (element) {
        element.value = "";
      }
    });
  }

  const isFile = shared?.isFileProtocol ? shared.isFileProtocol() : window.location.protocol === "file:";
  if (isFile) {
    setStatus(
      "Open via the FastAPI server (run `python app.py` and browse to `http://127.0.0.1:8000/website/pages/start.html`).",
      "warn"
    );
    generateBtn.disabled = true;
    approveBtn.disabled = true;
    setFinalizeEnabled(false);
  }

  function setMeta() {
    const uniqueItemCount = shared?.countUniqueItems ? shared.countUniqueItems(createdRows) : 0;
    objectsMetaEl.textContent = String(uniqueItemCount);
    relationsMetaEl.textContent = String(createdRows.length);
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
      if (isAbortError(error)) {
        throw error;
      }
      setStatus(`Error: ${errorMessage(error)}`, "err");
      setAction(failAction);
      throw error;
    }
  }

  async function postJson(url, payload, fallbackMessage, signal) {
    shared?.requireServedPage?.("This page must be opened via the FastAPI server (not as a local file).");
    return shared.fetchJson(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal,
    }, fallbackMessage);
  }

  function persistSession() {
    shared?.setSessionId?.(sessionId);
  }

  function persistLastProposalId() {
    shared?.setProposalId?.(lastProposalId);
  }

  function setSessionIdState(nextSessionId) {
    sessionId = nextSessionId || "";
    persistSession();
    setFinalizeEnabled(!!sessionId);
  }

  function setProposalIdState(proposalId) {
    lastProposalId = proposalId || null;
    persistLastProposalId();
    approveBtn.disabled = !lastProposalId;
  }

  function applyCreatedRows(data) {
    createdRows = createdRowsFromState(data);
    setMeta();
  }

  function proposalPatchRows(data) {
    if (Array.isArray(data?.patch_kb_json)) {
      return data.patch_kb_json;
    }
    if (Array.isArray(data?.diff?.added_rows)) {
      return data.diff.added_rows;
    }
    return Array.isArray(data?.proposal_rows_only) ? data.proposal_rows_only : [];
  }

  function createdRowsFromState(data) {
    return Array.isArray(data?.delta_kb_json) ? data.delta_kb_json : [];
  }

  function rowArraySignature(rows) {
    return JSON.stringify(Array.isArray(rows) ? rows : []);
  }

  function resetSessionUi(message = "", statusClass = "", actionMessage = "Idle") {
    shared?.clearStoredSessionState?.();
    setSessionIdState("");
    setProposalIdState(null);
    lastProposalPatchSignature = "";
    createdRows = [];
    clearValues(inputEl, explainEl, qsEl);
    renderGraph([], []);
    setGenerationMeta(null, 0, 0);
    setMeta();
    setStatus(message || "Idle", statusClass);
    setAction(actionMessage);
  }

  async function hydrateSessionTokenTotal() {
    if (!sessionId) {
      return;
    }

    hydrateRequestController?.abort();
    const controller = new AbortController();
    hydrateRequestController = controller;

    try {
      const data = await shared.fetchJson(
        `/api/state/${encodeURIComponent(sessionId)}`,
        { signal: controller.signal }
      );
      if (hydrateRequestController !== controller) {
        return;
      }
      if (data && data.exists === false) {
        resetSessionUi();
        return;
      }
      applyCreatedRows(data);
      setGenerationMeta(null, 0, data.token_usage_total);
    } catch (error) {
      if (isAbortError(error)) {
        return;
      }
      console.error("Failed to hydrate session state.", error);
    } finally {
      if (hydrateRequestController === controller) {
        hydrateRequestController = null;
      }
    }
  }

  function clearProposalState() {
    setProposalIdState(null);
    setMeta();
  }

  async function generateProposal() {
    const inputText = (inputEl.value || "").trim();
    if (!inputText) {
      setStatus("Please paste some text first.", "warn");
      return;
    }

    generateRequestController?.abort();
    const controller = new AbortController();
    generateRequestController = controller;
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
        }, "Request failed", controller.signal)
      );
      if (generateRequestController !== controller || !data) {
        return;
      }

      if (data.session_id) {
        setSessionIdState(data.session_id);
      }

      setProposalIdState(data.proposal_id);
      const patchRows = proposalPatchRows(data);
      lastProposalPatchSignature = rowArraySignature(patchRows);

      qsEl.value = JSON.stringify(patchRows, null, 2);
      explainEl.value = shared?.formatReasoningReport
        ? shared.formatReasoningReport(
          data.reasoning_report || {},
          Array.isArray(data.warnings) ? data.warnings : [],
          0.5
        )
        : "No reasoning report available.";

      renderGraph(
        Array.isArray(data.base_kb_json) ? data.base_kb_json : [],
        patchRows,
        Array.isArray(data.proposed_kb_json) ? data.proposed_kb_json : []
      );
      setGenerationMeta(data.generation_seconds, data.generation_tokens, data.session_tokens_total);
      setStatus("Proposal ready. Review reasoning and click Apply to update session state.", "ok");
      setAction("Proposal generated");
      setMeta();
    } catch (error) {
      if (isAbortError(error)) {
        return;
      }
      console.error("Proposal generation failed.", error);
    } finally {
      if (generateRequestController === controller) {
        generateRequestController = null;
      }
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

      applyCreatedRows(data);
      const currentRows = Array.isArray(data.current_kb_json) ? data.current_kb_json : [];
      // After appending, there is no longer a pending fragment preview. Keep the
      // accumulated session graph available for "Show full graph", but clear the
      // proposal-preview view so the page is ready for the next extraction batch.
      renderGraph(
        currentRows,
        [],
        currentRows,
        { preservePositions: true }
      );
      clearValues(inputEl, explainEl, qsEl);
      lastProposalPatchSignature = "";
      clearProposalState();
      setStatus("Approved. Cleared input/reasoning/JSON. Ready for next batch.", "ok");
      setAction("Proposal approved");
      return true;
    } catch (error) {
      console.error("Proposal approval failed.", error);
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

  showNewContextToggle?.addEventListener("change", () => rerenderGraph());
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) {
      if (pendingGraphPayload) {
        setGraphHint("Graph will refresh when this tab is active again.");
      }
      return;
    }
    requestAnimationFrame(() => {
      flushPendingGraphRender();
      if (cy) {
        applyGraphVisibility();
      }
    });
  });
  window.addEventListener("pagehide", () => {
    generateRequestController?.abort();
    hydrateRequestController?.abort();
  });
  window.addEventListener("pageshow", () => {
    requestAnimationFrame(() => {
      flushPendingGraphRender();
      if (cy) {
        applyGraphVisibility();
      }
    });
  });
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
    resetSessionUi(
      "Local browser session cleared. Server-side session may still exist until restart.",
      "warn",
      "Session cleared"
    );
  });

  generateBtn.addEventListener("click", generateProposal);
  approveBtn.addEventListener("click", approveProposal);
  navFinalizeBtn?.addEventListener("click", finalizeWithAppend);

  setMeta();
  setAction("Idle");
  setStatus("Idle");
  setGenerationMeta(null, 0, 0);
  setFinalizeEnabled(!!sessionId);
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
