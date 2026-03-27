(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const isFile = window.location.protocol === "file:";

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
})();
