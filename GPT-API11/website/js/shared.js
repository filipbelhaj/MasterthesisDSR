(function (global) {
  "use strict";

  const SESSION_KEY = "wikibase_extractor_session_id";
  const PROPOSAL_KEY = "wikibase_extractor_last_proposal_id";
  const FLASH_MESSAGE_KEY = "wikibase_extractor_notice";

  function isFileProtocol() {
    return global.location.protocol === "file:";
  }

  function requireServedPage(message) {
    if (isFileProtocol()) {
      throw new Error(message || "Open this page via the FastAPI server.");
    }
  }

  function getSessionId() {
    return localStorage.getItem(SESSION_KEY) || "";
  }

  function setSessionId(sessionId) {
    if (sessionId) {
      localStorage.setItem(SESSION_KEY, sessionId);
      return;
    }
    localStorage.removeItem(SESSION_KEY);
  }

  function getProposalId() {
    return localStorage.getItem(PROPOSAL_KEY) || null;
  }

  function setProposalId(proposalId) {
    if (proposalId) {
      localStorage.setItem(PROPOSAL_KEY, proposalId);
      return;
    }
    localStorage.removeItem(PROPOSAL_KEY);
  }

  function clearStoredSessionState() {
    localStorage.removeItem(SESSION_KEY);
    localStorage.removeItem(PROPOSAL_KEY);
  }

  function setFlashMessage(message) {
    if (message) {
      sessionStorage.setItem(FLASH_MESSAGE_KEY, message);
      return;
    }
    sessionStorage.removeItem(FLASH_MESSAGE_KEY);
  }

  function consumeFlashMessage() {
    const message = sessionStorage.getItem(FLASH_MESSAGE_KEY) || "";
    sessionStorage.removeItem(FLASH_MESSAGE_KEY);
    return message;
  }

  function countUniqueItems(rows) {
    const itemSet = new Set();
    for (const row of Array.isArray(rows) ? rows : []) {
      if (row && typeof row === "object" && row.item != null) {
        itemSet.add(String(row.item));
      }
    }
    return itemSet.size;
  }

  function pushListSection(lines, title, items) {
    if (!items.length) {
      return;
    }
    lines.push(title);
    items.forEach((item) => lines.push(`- ${item}`));
    lines.push("");
  }

  function formatReasoningReport(report, runtimeWarnings = [], minRelevance = 0.5) {
    if (!report || typeof report !== "object") {
      return "No reasoning report available.";
    }

    const summary = report.summary || {};
    const changes = Array.isArray(report.proposed_changes) ? report.proposed_changes : [];
    const visibleChanges = changes.filter((change) => change.relevance == null || change.relevance >= minRelevance);
    const hiddenCount = changes.length - visibleChanges.length;
    const warnings = Array.isArray(report.validation_warnings) ? report.validation_warnings : [];
    const visibleRuntimeWarnings = Array.isArray(runtimeWarnings) ? runtimeWarnings.filter(Boolean) : [];

    const lines = [
      "Summary",
      `- Creates: ${summary.creates ?? 0}`,
      `- Edits: ${summary.edits ?? 0}`,
      `- Links: ${summary.links ?? 0}`,
      `- Deletes: ${summary.deletes ?? 0}`,
      `- Uncertain: ${summary.uncertain ?? 0}`,
      `- Validation warnings: ${summary.validation_warnings ?? warnings.length}`,
      "",
    ];

    pushListSection(lines, "Validation warnings", warnings);
    pushListSection(lines, "Runtime warnings", visibleRuntimeWarnings);

    lines.push("Proposed changes");
    if (hiddenCount > 0) {
      lines.push(`- (${hiddenCount} change${hiddenCount === 1 ? "" : "s"} hidden due to low relevance)`);
    }
    if (!visibleChanges.length) {
      lines.push("- None");
      return lines.join("\n").trim();
    }

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

    return lines.join("\n").trim();
  }

  async function fetchJson(url, options, fallbackMessage) {
    const response = await fetch(url, options);
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(data.detail || data.error || fallbackMessage || "Request failed.");
    }
    return data;
  }

  global.TriExtractShared = {
    clearStoredSessionState,
    consumeFlashMessage,
    countUniqueItems,
    fetchJson,
    formatReasoningReport,
    getProposalId,
    getSessionId,
    isFileProtocol,
    requireServedPage,
    setFlashMessage,
    setProposalId,
    setSessionId,
  };
})(window);