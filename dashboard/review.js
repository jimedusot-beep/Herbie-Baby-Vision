/* Baby Vision Worker Bee #1: local-only review of existing private evidence packets.
 * No network, model calls, command execution, storage, or automatic approvals.
 */
(function (root, factory) {
  "use strict";
  const api = Object.freeze(factory());
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.BabyVisionReview = api;
})(typeof window === "object" ? window : globalThis, function () {
  "use strict";
  const TASK = "add-npm-test-entry-point";
  const SCRIPT = "npm run test:unit";
  const UNIT_SCRIPT = "node --test tests/*.test.cjs";
  const SHA = /^[0-9a-f]{40}$/;
  const MAX_FILE_BYTES = 262144;

  function plainObject(value) {
    return value !== null && typeof value === "object" &&
      !Array.isArray(value);
  }

  function validatePacket(packet) {
    const errors = [];
    if (!plainObject(packet)) {
      return { ok: false, errors: ["Expected a JSON object."], summary: null };
    }
    const status = packet.status;
    if (status !== "ready_for_human_review" && status !== "blocked") {
      errors.push("Unsupported or missing review status.");
    }
    if (packet.merge_allowed !== false) {
      errors.push("The packet must explicitly forbid automatic merging.");
    }
    const model = typeof packet.model === "string" &&
      packet.model.length > 0 && packet.model.length <= 200
      ? packet.model : "Not reported";
    if (status === "ready_for_human_review") {
      if (packet.task !== TASK) errors.push("Task is not the approved first-worker task.");
      if (typeof packet.source_commit !== "string" ||
          !SHA.test(packet.source_commit)) {
        errors.push("Source commit is missing or invalid.");
      }
      if (!Array.isArray(packet.allowed_files) ||
          packet.allowed_files.length !== 1 ||
          packet.allowed_files[0] !== "package.json") {
        errors.push("Changed-file scope was not explicitly approved.");
      }
      if (packet.test_exit_code !== 0) errors.push("Tests did not report success.");
      if (!Number.isInteger(packet.baseline_test_exit_code) ||
          packet.baseline_test_exit_code === 0) {
        errors.push("A prior failing baseline was not established.");
      }
      if (packet.model_generated !== true) {
        errors.push("The report does not identify a model proposal.");
      }
      if (!plainObject(packet.proposal) ||
          Object.keys(packet.proposal).sort().join(",") !== "reason,script" ||
          packet.proposal.script !== SCRIPT ||
          typeof packet.proposal.reason !== "string" ||
          !packet.proposal.reason.trim() ||
          packet.proposal.reason.length > 500) {
        errors.push("The proposed change is not the approved test-script edit.");
      }
      if (!plainObject(packet.package_json) ||
          !plainObject(packet.package_json.scripts) ||
          packet.package_json.scripts.test !== SCRIPT ||
          packet.package_json.scripts["test:unit"] !== UNIT_SCRIPT) {
        errors.push("The resulting package scripts do not match the approved task.");
      }
      if (typeof packet.patch !== "string" ||
          !packet.patch.startsWith("diff --git a/package.json b/package.json") ||
          packet.patch.length > 25000) {
        errors.push("A bounded package.json review diff is required.");
      }
    }
    const summary = {
      status: status === "ready_for_human_review" ? status : "blocked",
      task: status === "ready_for_human_review" ? TASK : "Blocked task",
      model,
      source_commit: typeof packet.source_commit === "string" &&
        SHA.test(packet.source_commit) ? packet.source_commit : "Not reported",
      test_exit_code: Number.isInteger(packet.test_exit_code)
        ? String(packet.test_exit_code) : "Not run",
      // No private output, prompts, stack traces or raw errors appear in summaries.
      evidence_claim_only: true
    };
    return {ok: errors.length === 0, errors, summary};
  }

  function startDashboard(document) {
    const get = id => document.getElementById(id);
    const fileInput = get("evidenceFile");
    const status = get("reviewStatus");
    const detail = get("reviewDetail");
    const preview = get("diffPreview");
    const showDiff = get("showDiff");
    const reviewed = get("markReviewed");
    const needsWork = get("markNeedsWork");
    const fields = ["taskName", "modelName", "commitSha", "testCode"];
    let packet = null;
    function reset() {
      packet = null;
      status.textContent = "No report loaded";
      detail.textContent = "Choose a private JSON evidence file. Nothing is uploaded.";
      preview.textContent = "";
      preview.hidden = true;
      showDiff.disabled = true;
      showDiff.textContent = "Show proposed diff";
      reviewed.disabled = true;
      needsWork.disabled = true;
      fields.forEach(id => { get(id).textContent = "—"; });
    }
    async function readFile() {
      reset();
      const file = fileInput.files && fileInput.files[0];
      if (!file) return;
      if (file.size > MAX_FILE_BYTES) {
        status.textContent = "Review blocked";
        detail.textContent = "File exceeds the 256 KiB local review limit.";
        return;
      }
      let parsed;
      try { parsed = JSON.parse(await file.text()); }
      catch (_) {
        status.textContent = "Review blocked";
        detail.textContent = "The file is not valid JSON.";
        return;
      }
      const result = validatePacket(parsed);
      if (!result.ok) {
        status.textContent = "Review blocked";
        detail.textContent = result.errors.join(" ");
        return;
      }
      packet = parsed;
      const v = result.summary;
      status.textContent = v.status === "ready_for_human_review"
        ? "Reported ready for human review — NOT independently verified"
        : "Worker reported blocked — no approval available";
      detail.textContent = "Local review only. This page cannot verify that commands ran or files changed.";
      get("taskName").textContent = v.task;
      get("modelName").textContent = v.model;
      get("commitSha").textContent = v.source_commit;
      get("testCode").textContent = v.test_exit_code;
      reviewed.disabled = v.status !== "ready_for_human_review";
      needsWork.disabled = false;
      showDiff.disabled = !(v.status === "ready_for_human_review" &&
        typeof packet.patch === "string");
    }
    fileInput.addEventListener("change", readFile);
    showDiff.addEventListener("click", () => {
      if (!packet || showDiff.disabled) return;
      preview.hidden = !preview.hidden;
      // Render source as text, never HTML. The diff may contain private code.
      preview.textContent = preview.hidden ? "" : packet.patch;
      showDiff.textContent = preview.hidden ? "Show proposed diff" : "Hide proposed diff";
    });
    reviewed.addEventListener("click", () => {
      if (reviewed.disabled || !packet) return;
      status.textContent = "Marked reviewed in this page only";
      detail.textContent = "No GitHub review, file change, merge or persistent approval occurred.";
    });
    needsWork.addEventListener("click", () => {
      if (needsWork.disabled || !packet) return;
      status.textContent = "Marked needs work in this page only";
      detail.textContent = "Return the report to the worker for correction. No repository action occurred.";
    });
    get("clearReview").addEventListener("click", () => {
      fileInput.value = "";
      reset();
    });
    reset();
  }

  if (typeof document !== "undefined" && document.getElementById) {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", () => startDashboard(document));
    } else {
      startDashboard(document);
    }
  }
  return {validatePacket, startDashboard, MAX_FILE_BYTES};
});
