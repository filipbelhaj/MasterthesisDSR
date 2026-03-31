(function (global) {
  "use strict";

  async function copyText(rawText) {
    const text = typeof rawText === "string" ? rawText : "";
    if (!text.trim()) {
      throw new Error("Nothing to copy.");
    }

    if (navigator.clipboard?.writeText && global.isSecureContext) {
      await navigator.clipboard.writeText(text);
      return;
    }

    const fallback = document.createElement("textarea");
    fallback.value = text;
    fallback.setAttribute("readonly", "");
    fallback.style.position = "fixed";
    fallback.style.top = "0";
    fallback.style.left = "0";
    fallback.style.opacity = "0";
    document.body.appendChild(fallback);
    fallback.focus();
    fallback.select();
    fallback.setSelectionRange(0, fallback.value.length);
    const copied = document.execCommand("copy");
    fallback.remove();

    if (!copied) {
      throw new Error("Copy failed. Select the text and copy it manually.");
    }
  }

  function setCopyUi(button, status, label, message, className) {
    button.textContent = label;
    if (!status) {
      return;
    }
    status.textContent = message;
    status.className = `sparql-copy-status${className ? ` ${className}` : ""}`;
  }

  function bindCopyButtons(root = document) {
    root.querySelectorAll("[data-copy-target]").forEach((button) => {
      if (button.dataset.copyBound === "true") {
        return;
      }
      button.dataset.copyBound = "true";

      const defaultLabel = button.textContent.trim() || "Copy";
      let resetTimer = 0;

      button.addEventListener("click", async () => {
        const targetId = button.getAttribute("data-copy-target");
        const target = targetId ? document.getElementById(targetId) : null;
        const status = targetId
          ? document.querySelector(`[data-copy-status-for="${targetId}"]`)
          : null;
        const resetMs = Number(button.dataset.copyResetMs || (status ? 2200 : 1200));

        try {
          await copyText(target?.value || "");
          setCopyUi(
            button,
            status,
            button.dataset.copySuccessLabel || "Copied",
            button.dataset.copySuccessText || "Copied to clipboard.",
            status ? "ok" : ""
          );
        } catch (error) {
          const message = error?.message || "Copy failed. Select the text and copy it manually.";
          const label = message === "Nothing to copy."
            ? "Nothing to copy"
            : (button.dataset.copyFailureLabel || "Copy failed");
          setCopyUi(button, status, label, message, status ? "err" : "");
        }

        global.clearTimeout(resetTimer);
        resetTimer = global.setTimeout(() => {
          setCopyUi(button, status, defaultLabel, "", "");
        }, resetMs);
      });
    });
  }

  bindCopyButtons();
})(window);