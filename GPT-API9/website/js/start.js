(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const shared = window.TriExtractShared;
  const isFile = shared?.isFileProtocol ? shared.isFileProtocol() : window.location.protocol === "file:";
  const startStatusEl = $("startStatus");
  const startHealthStatusEl = $("startHealthStatus");
  const startExtractBtn = $("startExtractBtn");
  const startCtaNoteEl = $("startCtaNote");

  function setStatus(el, message, tone) {
    if (!el) {
      return;
    }
    el.textContent = message || "";
    el.className = tone ? `status ${tone}` : "status";
  }

  function setExtractReady(isReady) {
    if (!startExtractBtn) {
      return;
    }

    const targetHref = startExtractBtn.dataset.href || "./extract.html";
    if (isReady) {
      startExtractBtn.setAttribute("href", targetHref);
      startExtractBtn.classList.remove("disabled");
      startExtractBtn.removeAttribute("aria-disabled");
      return;
    }

    startExtractBtn.removeAttribute("href");
    startExtractBtn.classList.add("disabled");
    startExtractBtn.setAttribute("aria-disabled", "true");
  }

  function setCtaNote(message, tone) {
    if (!startCtaNoteEl) {
      return;
    }
    startCtaNoteEl.textContent = message || "";
    startCtaNoteEl.className = tone ? `start-cta-note ${tone}` : "start-cta-note";
  }

  function consumeFlashMessage() {
    const message = shared?.consumeFlashMessage ? shared.consumeFlashMessage() : "";
    setStatus(startStatusEl, message, message ? "warn" : "");
  }

  async function refreshHealthStatus() {
    if (isFile) {
      setExtractReady(false);
      setCtaNote("Open this page via the FastAPI server before extracting or uploading files.", "warn");
      setStatus(startHealthStatusEl, "Open this page via the FastAPI server before extracting or uploading files.", "warn");
      return;
    }

    try {
      const data = await shared.fetchJson("/api/health", undefined, "Could not load server status.");
      const ontologyReady = !data.ontology_load_error;
      setExtractReady(ontologyReady);
      if (ontologyReady) {
        const queryStatus = data.default_query_file_exists
          ? "query.json is uploaded."
          : "query.json is not uploaded. Upload is optional.";
        setCtaNote(`Ontology is loaded. ${queryStatus}`, "ok");
        setStatus(startHealthStatusEl, "", "");
        return;
      }

      const detail = data.ontology_load_error ? ` Current server issue: ${data.ontology_load_error}` : "";
      const message = `Ontology is required before extracting. Upload ontology.json below first.${detail}`;
      setCtaNote(message, "err");
      setStatus(
        startHealthStatusEl,
        message,
        "err"
      );
    } catch (error) {
      setExtractReady(false);
      const message = error.message || "Could not load server status.";
      setCtaNote(message, "warn");
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
      status.textContent = `Uploaded: ${data.original_filename} -> ${data.saved_as}`;
      status.className = "upload-status ok";
      if (endpoint === "/api/upload-ontology") {
        await refreshHealthStatus();
      }
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