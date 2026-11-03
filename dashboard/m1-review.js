/* Baby Vision M1 — local-file-only, read-only review. No network or approvals.
 * Imported JSON and diffs are untrusted and rendered only via textContent.
 */
(function (root, factory) {
  'use strict';
  const app = Object.freeze(factory());
  if (typeof module === 'object' && module.exports) module.exports = app;
  else root.BabyVisionM1Review = app;
})(typeof window === 'object' ? window : globalThis, function () {
  'use strict';
  const MAX_JSON = 262144;
  const MAX_DIFF = 12000;
  const MAX_FILES = 3;
  const SHA = /^[0-9a-f]{40}$/;
  const DIGEST = /^[0-9a-f]{64}$/;
  const PATH = /^[A-Za-z0-9][A-Za-z0-9_./-]{0,199}$/;
  const ALLOWED_CONFIDENCE = new Set(['low', 'medium', 'high']);

  function plain(value) {
    return value !== null && typeof value === 'object' &&
      !Array.isArray(value) && Object.getPrototypeOf(value) === Object.prototype;
  }
  function safePath(value) {
    return typeof value === 'string' && PATH.test(value) &&
      !value.split('/').includes('..') && !value.split('/').includes('.') &&
      !value.includes('//');
  }
  function boundedText(value, limit, allowEmpty) {
    return typeof value === 'string' && value.length <= limit &&
      (allowEmpty || value.trim().length > 0);
  }
  function validCitations(value) {
    return Array.isArray(value) && value.length <= 8 && value.every(c =>
      plain(c) && safePath(c.path) && Number.isSafeInteger(c.line) &&
      c.line > 0 && c.line <= 2000000);
  }
  function validAnalysis(value) {
    return plain(value) &&
      ['summary', 'suspected_cause', 'suggested_change'].every(k =>
        boundedText(value[k], 2500, true)) &&
      ALLOWED_CONFIDENCE.has(value.confidence) && validCitations(value.citations);
  }
  function fail(reason) { return {ok: false, error: reason, value: null}; }
  function success(value) { return {ok: true, error: null, value}; }

  function validateInvestigation(raw) {
    if (!plain(raw) || typeof raw.source_commit !== 'string' || !SHA.test(raw.source_commit) ||
        !boundedText(raw.query, 160, false) || typeof raw.partial_scan !== 'boolean' ||
        !Number.isSafeInteger(raw.searched_files) || raw.searched_files < 0 ||
        raw.searched_files > 2000 || !validAnalysis(raw.analysis) ||
        !Array.isArray(raw.evidence) || raw.evidence.length < 1 || raw.evidence.length > 12) {
      return fail('Invalid investigation report structure.');
    }
    const evidence = raw.evidence;
    if (!evidence.every(e => plain(e) && safePath(e.path) &&
        Number.isSafeInteger(e.line) && e.line > 0 && e.line <= 2000000 &&
        boundedText(e.excerpt, 2000, true))) {
      return fail('Invalid investigation source evidence.');
    }
    const indexed = new Set(evidence.map(e => `${e.path}\u0000${e.line}`));
    if (!raw.analysis.citations.every(c => indexed.has(`${c.path}\u0000${c.line}`))) {
      return fail('Investigation includes citations outside its evidence list.');
    }
    return success({kind: 'investigation', source_commit: raw.source_commit,
      query: raw.query, partial_scan: raw.partial_scan, searched_files: raw.searched_files,
      analysis: raw.analysis, evidence: evidence.map(e => ({path: e.path, line: e.line,
        excerpt: e.excerpt}))});
  }

  function validateProposal(raw) {
    if (!plain(raw) || typeof raw.source_commit !== 'string' || !SHA.test(raw.source_commit) ||
        !boundedText(raw.query, 160, false) || !safePath(raw.target) ||
        !boundedText(raw.model, 120, false) || typeof raw.diff_sha256 !== 'string' ||
        !DIGEST.test(raw.diff_sha256) ||
        typeof raw.partial_scan !== 'boolean' || !validAnalysis(raw.analysis) ||
        !validCitations(raw.citations) || raw.citations.length < 1 ||
        !raw.citations.every(c => c.path === raw.target)) {
      return fail('Invalid proposal metadata structure.');
    }
    const analysisCites = new Set(raw.analysis.citations.map(c => `${c.path}\u0000${c.line}`));
    if (!raw.citations.every(c => analysisCites.has(`${c.path}\u0000${c.line}`))) {
      return fail('Proposal citations disagree with its analysis.');
    }
    return success({kind: 'proposal', source_commit: raw.source_commit,
      query: raw.query, target: raw.target, model: raw.model,
      diff_sha256: raw.diff_sha256, partial_scan: raw.partial_scan,
      analysis: raw.analysis, citations: raw.citations.map(c => ({path: c.path, line: c.line}))});
  }

  function correlate(investigation, proposal) {
    if (!investigation || !proposal) return 'unpaired';
    if (investigation.source_commit !== proposal.source_commit ||
        investigation.query !== proposal.query) return 'mismatch';
    const evidence = new Set(investigation.evidence.map(e => `${e.path}\u0000${e.line}`));
    return proposal.citations.every(c => evidence.has(`${c.path}\u0000${c.line}`))
      ? 'matching-claims' : 'mismatch';
  }

  async function parseFiles(files, subtle) {
    if (!Array.isArray(files) || !files.length || files.length > MAX_FILES) {
      return fail('Choose one to three local review files.');
    }
    let investigation = null, proposal = null, diff = null;
    const names = new Set();
    for (const file of files) {
      if (!file || typeof file.name !== 'string' ||
          !Number.isSafeInteger(file.size) || file.size < 0 ||
          names.has(file.name.toLowerCase())) return fail('Invalid or duplicate file selection.');
      names.add(file.name.toLowerCase());
      const isJson = file.name.toLowerCase().endsWith('.json');
      const isDiff = file.name.toLowerCase().endsWith('.diff');
      if ((!isJson && !isDiff) || file.size > (isDiff ? MAX_DIFF : MAX_JSON)) {
        return fail('Unsupported or oversized review file.');
      }
      let raw;
      try { raw = await file.text(); }
      catch (_) { return fail('Unable to read selected file.'); }
      if (typeof raw !== 'string' || raw.length > (isDiff ? MAX_DIFF : MAX_JSON)) {
        return fail('Selected file exceeds the review size limit.');
      }
      if (isDiff) {
        if (diff !== null) return fail('Choose only one diff.');
        diff = raw;
      } else {
        let packet;
        try { packet = JSON.parse(raw); }
        catch (_) { return fail('Invalid JSON review file.'); }
        const isInvestigation = plain(packet) && Array.isArray(packet.evidence) &&
          Object.prototype.hasOwnProperty.call(packet, 'searched_files');
        const validated = isInvestigation ? validateInvestigation(packet) : validateProposal(packet);
        if (!validated.ok) return validated;
        if (isInvestigation) {
          if (investigation) return fail('Choose only one investigation.');
          investigation = validated.value;
        } else {
          if (proposal) return fail('Choose only one proposal.');
          proposal = validated.value;
        }
      }
    }
    if (!investigation && !proposal) return fail('An M1 JSON report is required.');
    if (diff !== null && !proposal) return fail('A diff requires its proposal JSON.');
    const pairing = correlate(investigation, proposal);
    if (pairing === 'mismatch') return fail('Selected reports have inconsistent source evidence.');
    let diffStatus = 'not supplied';
    if (diff !== null) {
      if (diff.includes('\u0000') || diff.includes('\r') ||
          !diff.startsWith(`--- a/${proposal.target}\n+++ b/${proposal.target}\n@@ `)) {
        return fail('Diff does not have the expected review-only file headers.');
      }
      if (!subtle || typeof subtle.digest !== 'function' ||
          typeof TextEncoder !== 'function') {
        diffStatus = 'checksum unavailable';
        diff = null; // Never display an unchecked private patch as a matching proposal.
      } else {
        let hash;
        try {
          const bytes = new TextEncoder().encode(diff);
          if (bytes.byteLength > MAX_DIFF) return fail('Diff exceeds the review size limit.');
          const buf = await subtle.digest('SHA-256', bytes);
          hash = Array.from(new Uint8Array(buf), b => b.toString(16).padStart(2, '0')).join('');
        } catch (_) { return fail('Could not check the diff digest.'); }
        if (hash !== proposal.diff_sha256) return fail('Diff SHA-256 does not match proposal metadata.');
        diffStatus = 'matches supplied SHA-256 claim';
      }
    }
    return success({investigation, proposal, diff, diffStatus, pairing});
  }

  function startDashboard(doc, subtle) {
    const get = id => doc.getElementById(id);
    const input = get('localFiles');
    let current = null, generation = 0;
    function text(id, value) { get(id).textContent = value; }
    function reset() {
      current = null;
      for (const id of ['sourceCommit', 'reviewQuery', 'modelTag', 'targetFile',
        'coverageState', 'confidence', 'summary', 'suspectedCause', 'suggestedChange',
        'pairState', 'checksumState', 'citationList']) text(id, '—');
      get('sourcePreview').textContent = '';
      get('diffPreview').textContent = '';
      get('sourcePreview').hidden = true;
      get('diffPreview').hidden = true;
      get('toggleSource').disabled = true;
      get('toggleDiff').disabled = true;
      text('toggleSource', 'Show evidence excerpts');
      text('toggleDiff', 'Show proposed diff');
      text('reviewStatus', 'No report selected');
      text('reviewDetail', 'Choose local JSON files, and optionally a matching .diff.');
    }
    async function load() {
      const own = ++generation;
      reset();
      const files = Array.from(input.files || []);
      if (!files.length) return;
      const result = await parseFiles(files, subtle);
      if (own !== generation) return;
      if (!result.ok) {
        text('reviewStatus', 'Review blocked');
        text('reviewDetail', result.error);
        return;
      }
      current = result.value;
      const obj = current.proposal || current.investigation;
      const analysis = obj.analysis;
      text('reviewStatus', 'Local review • unverified report claims');
      text('reviewDetail', 'This page cannot authenticate the report, confirm Git state, run tests, or approve changes.');
      text('sourceCommit', obj.source_commit);
      text('reviewQuery', obj.query);
      text('modelTag', current.proposal ? current.proposal.model : 'Not saved in investigation');
      text('targetFile', current.proposal ? current.proposal.target : 'Investigation only');
      text('coverageState', obj.partial_scan ? 'Partial search — not exhaustive' :
        'Claims a complete bounded scan — not independently checked');
      text('confidence', analysis.confidence + ' (model-reported)');
      text('summary', analysis.summary);
      text('suspectedCause', analysis.suspected_cause);
      text('suggestedChange', analysis.suggested_change);
      text('pairState', current.pairing === 'matching-claims' ?
        'Matching file, commit, query and citations (claims only)' : 'Only one report type loaded');
      text('checksumState', current.diffStatus);
      const cites = current.proposal ? current.proposal.citations : analysis.citations;
      text('citationList', cites.length ? cites.map(c => `${c.path}:${c.line}`).join('\n') : 'None supplied');
      if (current.investigation) get('toggleSource').disabled = false;
      if (current.diff !== null) get('toggleDiff').disabled = false;
    }
    input.addEventListener('change', load);
    get('toggleSource').addEventListener('click', () => {
      if (!current || !current.investigation) return;
      const el = get('sourcePreview');
      el.hidden = !el.hidden;
      el.textContent = el.hidden ? '' : current.investigation.evidence.map(e =>
        `${e.path}:${e.line}\n${e.excerpt}`).join('\n\n');
      text('toggleSource', el.hidden ? 'Show evidence excerpts' : 'Hide evidence excerpts');
    });
    get('toggleDiff').addEventListener('click', () => {
      if (!current || current.diff === null) return;
      const el = get('diffPreview');
      el.hidden = !el.hidden;
      el.textContent = el.hidden ? '' : current.diff;
      text('toggleDiff', el.hidden ? 'Show proposed diff' : 'Hide proposed diff');
    });
    get('clearAll').addEventListener('click', () => {
      ++generation;
      input.value = '';
      reset();
    });
    reset();
  }

  if (typeof document !== 'undefined' && document.getElementById) {
    const start = () => startDashboard(document, globalThis.crypto && globalThis.crypto.subtle);
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
    else start();
  }
  return Object.freeze({validateInvestigation, validateProposal, correlate, parseFiles,
    startDashboard, MAX_JSON, MAX_DIFF, MAX_FILES});
});
