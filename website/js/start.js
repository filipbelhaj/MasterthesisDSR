(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const shared = window.TriExtractShared;
  const isFile = shared?.isFileProtocol ? shared.isFileProtocol() : window.location.protocol === "file:";
  const startStatusEl = $("startStatus");
  const startHealthStatusEl = $("startHealthStatus");
  const startNavExtractBtn = $("startNavExtractBtn");
  const removeOntologyBtn = $("removeOntologyBtn");
  const removeQueryBtn = $("removeQueryBtn");

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

  function setRemoveButtons({ ontologyFileExists = false, queryFileExists = false } = {}) {
    if (removeOntologyBtn) {
      removeOntologyBtn.disabled = isFile || !ontologyFileExists;
    }
    if (removeQueryBtn) {
      removeQueryBtn.disabled = isFile || !queryFileExists;
    }
  }

  function consumeFlashMessage() {
    const message = shared?.consumeFlashMessage ? shared.consumeFlashMessage() : "";
    setStatus(startStatusEl, message, message ? "warn" : "");
  }

  async function refreshHealthStatus() {
    if (isFile) {
      setExtractReady(false);
      setRemoveButtons();
      setStatus(startHealthStatusEl, "Open this page via the FastAPI server before extracting or uploading files.", "warn");
      return;
    }

    try {
      const sessionId = shared?.getSessionId ? shared.getSessionId() : "";
      const healthUrl = sessionId ? `/api/health?session_id=${encodeURIComponent(sessionId)}` : "/api/health";
      const data = await shared.fetchJson(healthUrl, undefined, "Could not load server status.");
      const ontologyReady = !data.ontology_load_error;
      setRemoveButtons({
        ontologyFileExists: !!data.session_ontology_file_exists,
        queryFileExists: !!data.session_query_file_exists,
      });
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
      setRemoveButtons();
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
    const sessionId = shared?.getSessionId ? shared.getSessionId() : "";
    if (sessionId) {
      fd.append("session_id", sessionId);
    }

    try {
      const response = await fetch(endpoint, { method: "POST", body: fd });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || "Upload failed.");
      }
      if (data.session_id) {
        shared?.setSessionId?.(data.session_id);
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

  async function removeUploadedFile(statusId, endpoint, confirmMessage, successMessage) {
    const status = $(statusId);
    if (!status) {
      return;
    }
    if (isFile) {
      status.textContent = "Open via the FastAPI server to remove uploads.";
      status.className = "upload-status err";
      return;
    }
    if (!window.confirm(confirmMessage)) {
      return;
    }

    status.textContent = "Removing...";
    status.className = "upload-status";
    try {
      const sessionId = shared?.getSessionId ? shared.getSessionId() : "";
      const url = sessionId ? `${endpoint}?session_id=${encodeURIComponent(sessionId)}` : endpoint;
      const data = await shared.fetchJson(
        url,
        { method: "DELETE" },
        "Remove failed."
      );
      if (data.session_id) {
        shared?.setSessionId?.(data.session_id);
      }
      status.textContent = data.message || successMessage;
      status.className = "upload-status ok";
      await refreshHealthStatus();
    } catch (error) {
      status.textContent = error.message || "Remove failed.";
      status.className = "upload-status err";
    }
  }

  [
    ["uploadOntologyBtn", "ontologyFile", "ontologyStatus", "/api/upload-ontology"],
    ["uploadQueryBtn", "queryFile", "queryStatus", "/api/upload-query"],
  ].forEach(([buttonId, inputId, statusId, endpoint]) => {
    $(buttonId)?.addEventListener("click", () => uploadFile(inputId, statusId, endpoint));
  });

  removeOntologyBtn?.addEventListener("click", () => removeUploadedFile(
    "ontologyStatus",
    "/api/upload-ontology",
    "Remove the uploaded ontology? Current server sessions will be cleared.",
    "Ontology removed."
  ));
  removeQueryBtn?.addEventListener("click", () => removeUploadedFile(
    "queryStatus",
    "/api/upload-query",
    "Remove the uploaded knowledge graph? Current server sessions will be cleared.",
    "Knowledge graph removed."
  ));

  consumeFlashMessage();
  refreshHealthStatus();
})();
