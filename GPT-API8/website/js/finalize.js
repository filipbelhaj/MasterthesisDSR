(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const newSessionBtn = $("newSessionBtn");
  const copyStep1Btn = $("copyStep1Btn");
  const copyStep2Btn = $("copyStep2Btn");
  const generateStep2Btn = $("generateStep2Btn");
  const objectsMetaEl = $("objects_meta");
  const relationsMetaEl = $("relations_meta");
  const sessionTokensMetaEl = $("session_tokens_meta");
  const quickstatementsWarningsEl = $("quickstatements_warnings");
  const step2WarningsEl = $("step2_warnings");
  const bindingsEl = $("placeholder_bindings");
  const step2OutputEl = $("step2_quickstatements_output");
  let cy = null;

  async function copyTextarea(textarea, button) {
    const text = (textarea?.value || "").trim();
    const original = button.textContent;
    if (!text) {
      button.textContent = "Nothing to copy";
      setTimeout(() => {
        button.textContent = original;
      }, 1200);
      return;
    }

    try {
      await navigator.clipboard.writeText(text);
      button.textContent = "Copied";
    } catch {
      if (textarea) {
        textarea.focus();
        textarea.select();
        document.execCommand("copy");
        textarea.setSelectionRange(0, 0);
        button.textContent = "Copied";
      }
    } finally {
      setTimeout(() => {
        button.textContent = original;
      }, 1200);
    }
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
      hint.textContent = "Graph library not loaded.";
      return;
    }

    cy = renderSharedGraph(cy, container, oldArr || [], newArr || [], false);
    if (!cy) {
      hint.textContent = "Graph library not loaded.";
      return;
    }
    hint.textContent = `Visible: ${cy.nodes().length} nodes, ${cy.edges().length} edges.`;
  }

  async function initFinalize() {
    if (window.location.protocol === "file:") {
      throw new Error("Open via the FastAPI server (run `python app.py` and use `/website/pages/finalize.html`).");
    }

    const params = new URLSearchParams(window.location.search);
    const sessionId = params.get("session_id") || localStorage.getItem("wikibase_extractor_session_id") || "";
    if (!sessionId) {
      return;
    }

    const [stateRes, queryRes, qsRes] = await Promise.all([
      fetch(`/api/state/${encodeURIComponent(sessionId)}`),
      fetch("/api/default-query"),
      fetch(`/api/quickstatements/${encodeURIComponent(sessionId)}`),
    ]);

    const stateData = await stateRes.json();
    const queryData = await queryRes.json();
    const qsData = await qsRes.json();
    if (!stateRes.ok) {
      throw new Error(stateData.detail || "Could not load final state.");
    }
    if (stateData && stateData.exists === false) {
      localStorage.removeItem("wikibase_extractor_session_id");
      window.location.href = "./start.html";
      return;
    }
    if (!queryRes.ok) {
      throw new Error(queryData.detail || "Could not load the default query data.");
    }
    if (!qsRes.ok) {
      throw new Error(qsData.detail || "Could not generate QuickStatements.");
    }

    const addedRows = Array.isArray(stateData.delta_kb_json) ? stateData.delta_kb_json : [];
    const removedRows = Array.isArray(stateData.removed_kb_json) ? stateData.removed_kb_json : [];
    const finalRows = addedRows.length
      ? addedRows
      : (Array.isArray(stateData.current_kb_json) ? stateData.current_kb_json : []);
    const queryRows = queryData.exists && Array.isArray(queryData.rows) ? queryData.rows : [];
    const mode = String(qsData.mode || "single_step");
    const step1Quickstatements = typeof qsData.step1_quickstatements === "string" && qsData.step1_quickstatements
      ? qsData.step1_quickstatements
      : (typeof qsData.quickstatements === "string" ? qsData.quickstatements : "");
    const step2Quickstatements = typeof qsData.step2_quickstatements === "string" ? qsData.step2_quickstatements : "";
    const qsWarnings = Array.isArray(qsData.warnings) ? qsData.warnings : [];
    const bindings = Array.isArray(qsData.binding_template) ? qsData.binding_template : [];

    const itemSet = new Set();
    for (const row of finalRows) {
      if (row && typeof row === "object" && row.item != null) {
        itemSet.add(String(row.item));
      }
    }
    if (objectsMetaEl) {
      objectsMetaEl.textContent = String(itemSet.size);
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
    renderGraph(queryRows, finalRows);
  }

  initFinalize().catch((error) => {
    const output = $("final_output");
    if (output) {
      output.value = `Error: ${error.message || error}`;
    }
  });

  newSessionBtn?.addEventListener("click", () => {
    localStorage.removeItem("wikibase_extractor_session_id");
    window.location.href = "./start.html";
  });

  generateStep2Btn?.addEventListener("click", async () => {
    const params = new URLSearchParams(window.location.search);
    const sessionId = params.get("session_id") || localStorage.getItem("wikibase_extractor_session_id") || "";
    if (!sessionId) {
      return;
    }
    try {
      const bindings = JSON.parse(bindingsEl.value || "[]");
      const response = await fetch(`/api/quickstatements/${encodeURIComponent(sessionId)}/step2`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ bindings }),
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || "Could not generate Step 2 QuickStatements.");
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

  copyStep1Btn?.addEventListener("click", async () => {
    await copyTextarea($("quickstatements_output"), copyStep1Btn);
  });

  copyStep2Btn?.addEventListener("click", async () => {
    await copyTextarea(step2OutputEl, copyStep2Btn);
  });
})();
