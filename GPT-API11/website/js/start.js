(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const shared = window.TriExtractShared;
  const isFile = shared?.isFileProtocol ? shared.isFileProtocol() : window.location.protocol === "file:";
  const startStatusEl = $("startStatus");
  const startHealthStatusEl = $("startHealthStatus");
  const startNavExtractBtn = $("startNavExtractBtn");

  function setStatus(el, message, tone) {
    if (!el) {
      return;
    }
    el.textContent = message || "";
    el.className = tone ? `status ${tone}` : "status";
  }

  function setExtractReady(isReady) {
    if (!startNavExtractBtn) {
      return;
    }

    const targetHref = startNavExtractBtn.dataset.href || "./extract.html";
    if (isReady) {
      startNavExtractBtn.setAttribute("href", targetHref);
      startNavExtractBtn.classList.remove("disabled");
      startNavExtractBtn.removeAttribute("aria-disabled");
      return;
    }

    startNavExtractBtn.removeAttribute("href");
    startNavExtractBtn.classList.add("disabled");
    startNavExtractBtn.setAttribute("aria-disabled", "true");
  }

  function consumeFlashMessage() {
    const message = shared?.consumeFlashMessage ? shared.consumeFlashMessage() : "";
    setStatus(startStatusEl, message, message ? "warn" : "");
  }

  async function refreshHealthStatus() {
    if (isFile) {
      setExtractReady(false);
      setStatus(startHealthStatusEl, "Open this page via the FastAPI server before extracting or uploading files.", "warn");
      return;
    }

    try {
      const data = await shared.fetchJson("/api/health", undefined, "Could not load server status.");
      const ontologyReady = !data.ontology_load_error;
      setExtractReady(ontologyReady);
      if (ontologyReady) {
        const graphStatus = data.default_query_file_exists
          ? "An existing knowledge graph is uploaded. You can continue to Extract."
          : "No existing knowledge graph is uploaded. ORS Explorer will start a new one when you continue to Extract.";
        setStatus(startHealthStatusEl, `Ontology is loaded. ${graphStatus}`, "ok");
        return;
      }

      const detail = data.ontology_load_error ? ` Current server issue: ${data.ontology_load_error}` : "";
      const message = `Ontology is required before extracting. Upload ontology.json below first.${detail}`;
      setStatus(
        startHealthStatusEl,
        message,
        "err"
      );
    } catch (error) {
      setExtractReady(false);
      const message = error.message || "Could not load server status.";
      setStatus(startHealthStatusEl, message, "warn");
    }
  }

  async function uploadFile(inputId, statusId, endpoint) {
    const input = $(inputId);
    const status = $(statusId);
    const file = input?.files?.[0];

    if (!status) {
      return;
    }
    if (!file) {
      status.textContent = "Please choose a file first.";
      status.className = "upload-status err";
      return;
    }
    if (isFile) {
      status.textContent = "Open via the FastAPI server to enable uploads (run `python app.py`).";
      status.className = "upload-status err";
      return;
    }

    const fd = new FormData();
    fd.append("file", file);

    try {
      const response = await fetch(endpoint, { method: "POST", body: fd });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || "Upload failed.");
      }
      status.textContent = endpoint === "/api/upload-query"
        ? `Knowledge graph uploaded: ${data.original_filename}`
        : `Uploaded: ${data.original_filename} -> ${data.saved_as}`;
      status.className = "upload-status ok";
      await refreshHealthStatus();
    } catch (error) {
      status.textContent = error.message || "Upload failed.";
      status.className = "upload-status err";
    }
  }

  [
    ["uploadOntologyBtn", "ontologyFile", "ontologyStatus", "/api/upload-ontology"],
    ["uploadQueryBtn", "queryFile", "queryStatus", "/api/upload-query"],
  ].forEach(([buttonId, inputId, statusId, endpoint]) => {
    $(buttonId)?.addEventListener("click", () => uploadFile(inputId, statusId, endpoint));
  });

  consumeFlashMessage();
  refreshHealthStatus();
})();
