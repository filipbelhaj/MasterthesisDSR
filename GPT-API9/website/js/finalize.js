(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const shared = window.TriExtractShared;
  const newSessionBtn = $("newSessionBtn");
  const generateStep2Btn = $("generateStep2Btn");
  const objectsMetaEl = $("objects_meta");
  const relationsMetaEl = $("relations_meta");
  const sessionTokensMetaEl = $("session_tokens_meta");
  const quickstatementsWarningsEl = $("quickstatements_warnings");
  const step2WarningsEl = $("step2_warnings");
  const bindingsEl = $("placeholder_bindings");
  const step2OutputEl = $("step2_quickstatements_output");
  let cy = null;

  function redirectToStart(message) {
    shared?.clearStoredSessionState?.();
    shared?.setFlashMessage?.(message);
    window.location.replace("./start.html");
  }

  function setHelpText(element, text) {
    if (!element) {
      return;
    }
    if (text) {
      element.textContent = text;
      element.hidden = false;
    } else {
      element.textContent = "";
      element.hidden = true;
    }
  }

  function renderGraph(oldArr, newArr) {
    const container = $("final_cy");
    const hint = $("final_kg_hint");
    const renderSharedGraph = window.TriExtractGraph?.renderGraph;
    if (!container || !renderSharedGraph) {
      if (hint) {
        hint.textContent = "Graph library not loaded.";
      }
      return;
    }

    cy = renderSharedGraph(cy, container, oldArr || [], newArr || [], false);
    if (!cy) {
      if (hint) {
        hint.textContent = "Graph library not loaded.";
      }
      return;
    }
    if (hint) {
      hint.textContent = `Visible: ${cy.nodes().length} nodes, ${cy.edges().length} edges.`;
    }
  }

  async function initFinalize() {
    shared?.requireServedPage?.("Open via the FastAPI server (run `python app.py` and use `/website/pages/finalize.html`).");

    const params = new URLSearchParams(window.location.search);
    const sessionId = params.get("session_id") || shared?.getSessionId?.() || "";
    if (!sessionId) {
      redirectToStart("No active session was found. Start or resume a session from the Extract page.");
      return;
    }
    shared?.setSessionId?.(sessionId);

    const stateData = await shared.fetchJson(
      `/api/state/${encodeURIComponent(sessionId)}`,
      undefined,
      "Could not load final state."
    );
    if (stateData && stateData.exists === false) {
      redirectToStart(stateData.detail || "Session expired. Start a new session from the Extract page.");
      return;
    }

    const [qsData] = await Promise.all([
      shared.fetchJson(
        `/api/quickstatements/${encodeURIComponent(sessionId)}`,
        undefined,
        "Could not generate QuickStatements."
      ),
    ]);
    if (qsData && qsData.exists === false) {
      redirectToStart(qsData.detail || "Session expired before QuickStatements could be loaded.");
      return;
    }

    const addedRows = Array.isArray(stateData.delta_kb_json) ? stateData.delta_kb_json : [];
    const removedRows = Array.isArray(stateData.removed_kb_json) ? stateData.removed_kb_json : [];
    const baseRows = Array.isArray(stateData.base_kb_json) ? stateData.base_kb_json : [];
    const finalRows = addedRows.length
      ? addedRows
      : (Array.isArray(stateData.current_kb_json) ? stateData.current_kb_json : []);
    const mode = String(qsData.mode || "single_step");
    const step1Quickstatements = typeof qsData.step1_quickstatements === "string" && qsData.step1_quickstatements
      ? qsData.step1_quickstatements
      : (typeof qsData.quickstatements === "string" ? qsData.quickstatements : "");
    const step2Quickstatements = typeof qsData.step2_quickstatements === "string" ? qsData.step2_quickstatements : "";
    const qsWarnings = Array.isArray(qsData.warnings) ? qsData.warnings : [];
    const bindings = Array.isArray(qsData.binding_template) ? qsData.binding_template : [];

    if (objectsMetaEl) {
      objectsMetaEl.textContent = String(shared?.countUniqueItems ? shared.countUniqueItems(finalRows) : 0);
    }
    if (relationsMetaEl) {
      relationsMetaEl.textContent = String(finalRows.length);
    }
    if (sessionTokensMetaEl) {
      sessionTokensMetaEl.textContent = String(Number(stateData.token_usage_total || 0) || 0);
    }

    $("final_output").value = JSON.stringify(
      removedRows.length
        ? {
            added_rows: addedRows,
            deleted_rows: removedRows,
          }
        : finalRows,
      null,
      2
    );
    $("quickstatements_output").value = step1Quickstatements;
    bindingsEl.value = bindings.length ? JSON.stringify(bindings, null, 2) : "[]";
    step2OutputEl.value = step2Quickstatements;
    setHelpText(
      quickstatementsWarningsEl,
      mode === "two_step"
        ? (qsWarnings.join(" ") || "Run Step 1 first, fill in the created QIDs below, then generate Step 2.")
        : (qsWarnings.join(" ") || "No placeholder mapping needed. Step 2 already contains the import batch.")
    );
    setHelpText(step2WarningsEl, "");
    renderGraph(baseRows, finalRows);
  }

  initFinalize().catch((error) => {
    const output = $("final_output");
    if (output) {
      output.value = `Error: ${error.message || error}`;
    }
  });

  newSessionBtn?.addEventListener("click", () => {
    redirectToStart("");
  });

  generateStep2Btn?.addEventListener("click", async () => {
    const params = new URLSearchParams(window.location.search);
    const sessionId = params.get("session_id") || shared?.getSessionId?.() || "";
    if (!sessionId) {
      redirectToStart("No active session was found. Start or resume a session from the Extract page.");
      return;
    }
    try {
      const bindings = JSON.parse(bindingsEl.value || "[]");
      const data = await shared.fetchJson(
        `/api/quickstatements/${encodeURIComponent(sessionId)}/step2`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ bindings }),
        },
        "Could not generate Step 2 QuickStatements."
      );
      if (data && data.exists === false) {
        redirectToStart(data.detail || "Session expired before Step 2 could be generated.");
        return;
      }

      step2OutputEl.value = typeof data.quickstatements === "string" ? data.quickstatements : "";
      const warnings = Array.isArray(data.warnings) ? data.warnings : [];
      const unresolved = Array.isArray(data.unresolved_placeholders) ? data.unresolved_placeholders : [];
      const parts = [];
      if (warnings.length) {
        parts.push(warnings.join(" "));
      }
      if (unresolved.length) {
        parts.push(`Still unresolved: ${unresolved.map((entry) => entry.placeholder).join(", ")}`);
      }
      if (!parts.length && step2OutputEl.value.trim()) {
        parts.push("Step 2 is ready to paste into Wikibase Cloud.");
      }
      setHelpText(step2WarningsEl, parts.join(" "));
    } catch (error) {
      setHelpText(step2WarningsEl, `Error: ${error.message || error}`);
    }
  });
})();
