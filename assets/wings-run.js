(() => {
  "use strict";

  const LOCAL_HOSTS = new Set(["127.0.0.1", "localhost"]);
  const localOrigin = LOCAL_HOSTS.has(location.hostname) ? location.origin : "http://127.0.0.1:8765";
  const localMode = LOCAL_HOSTS.has(location.hostname);
  const initialParams = new URLSearchParams(location.search);
  let restorePending = localMode && !initialParams.has("run") && initialParams.get("new") !== "1";

  const stageDefinitions = [
    ["inputs", "Inputs & metadata"],
    ["read_qc", "Read QC"],
    ["assembly", "Influenza assembly & coverage"],
    ["polishing", "Consensus polishing & variants"],
    ["characterization", "Typing & annotation"],
    ["phylogeny", "Phylogenetics"],
    ["surveillance", "Surveillance integration"],
    ["reporting", "Reports & archival"]
  ];

  const state = {
    step: 0,
    runner: null,
    reads: [],
    metadata: null,
    metadataIds: [],
    metadataError: "",
    runId: null,
    poller: null,
    resumePending: false,
    statusRequest: 0,
    pollPending: false
  };

  const $ = (id) => document.getElementById(id);
  // A cached page may predate the optional activity indicator.
  function setActivity(running) {
    $("statusActivity")?.classList.toggle("running", running);
  }
  const stepMeta = [
    ["Run details", "Name the run and choose local compute settings."],
    ["Sequences", "Select the FASTQ files that will remain on this computer."],
    ["Metadata", "Select and validate the WINGS sample metadata."],
    ["Analysis", "Choose the major WINGS analysis modules."],
    ["Preflight", "Confirm the local runner, files, metadata, and analysis plan before launch."]
  ];

  function stripFastq(name) {
    return name.replace(/\.(fastq|fq)(\.gz)?$/i, "");
  }

  function fastqExtension(name) {
    const m = name.match(/(\.fastq\.gz|\.fq\.gz|\.fastq|\.fq)$/i);
    return m ? m[1].toLowerCase() : "";
  }

  function formatBytes(bytes) {
    if (!Number.isFinite(bytes) || bytes <= 0) return "0 B";
    const units = ["B", "KB", "MB", "GB", "TB"];
    let value = bytes;
    let unit = 0;
    while (value >= 1024 && unit < units.length - 1) { value /= 1024; unit += 1; }
    return `${value.toFixed(value >= 10 || unit === 0 ? 0 : 1)} ${units[unit]}`;
  }

  function setStep(next) {
    state.step = Math.max(0, Math.min(4, next));
    document.querySelectorAll("[data-step-panel]").forEach((panel) => {
      panel.hidden = Number(panel.dataset.stepPanel) !== state.step;
    });
    document.querySelectorAll(".step-button").forEach((button) => {
      if (Number(button.dataset.step) === state.step) button.setAttribute("aria-current", "step");
      else button.removeAttribute("aria-current");
    });
    $("stepTitle").textContent = stepMeta[state.step][0];
    $("stepSubtitle").textContent = stepMeta[state.step][1];
    $("backButton").disabled = state.step === 0;
    $("nextButton").hidden = state.step === 4;
    if (state.step === 4) renderPreflight();
  }

  async function checkRunner() {
    const pill = $("runnerPill");
    try {
      if (!localMode) throw new Error("hosted");
      const response = await fetch(`${localOrigin}/api/health`, {cache: "no-store"});
      if (!response.ok) throw new Error("runner unavailable");
      state.runner = await response.json();
      pill.className = "runner-pill ready";
      if (!state.runner.snakemake_available) $("runnerText").textContent = "Runner found · Snakemake missing";
      else if (!state.runner.config_yaml_present) $("runnerText").textContent = "Runner found · config.yaml missing";
      else $("runnerText").textContent = "Local runner ready";
      $("openLocalRunner").hidden = true;
    } catch (error) {
      state.runner = null;
      pill.className = "runner-pill error";
      $("runnerText").textContent = localMode ? "Local runner unavailable" : "Open local runner to execute";
      $("openLocalRunner").hidden = localMode;
    }
    if (state.step === 4) renderPreflight();
  }

  async function refreshRuns() {
    if (!localMode) return;
    $("savedRuns").hidden = false;
    try {
      const response = await fetch(`${localOrigin}/api/runs`, {cache: "no-store"});
      if (!response.ok) throw new Error("runs unavailable");
      const runs = await response.json();
      runs.sort((a, b) => (b.created_at || b.run_id).localeCompare(a.created_at || a.run_id));
      const select = $("savedRunSelect");
      select.replaceChildren(new Option("Choose a saved run", ""));
      for (const run of runs) {
        select.add(new Option(`${run.name || "WINGS run"} · ${run.status} · ${run.run_id}`, run.run_id));
      }
      select.value = state.runId || "";
      $("savedRunsMessage").textContent = runs.length
        ? "Saved on this computer. Opening a run shows its latest status."
        : "No saved runs on this computer yet.";
      if (restorePending) {
        restorePending = false;
        const recent = runs.find((run) => ["running", "stopping"].includes(run.status))
          || runs.find((run) => run.status !== "created");
        if (recent) openRun(recent.run_id);
      }
    } catch (error) {
      $("savedRunsMessage").textContent = "Unable to load saved runs. Keep the local runner open and try Refresh runs.";
    }
  }

  function openRun(runId) {
    if (!localMode || !runId) return;
    restorePending = false;
    clearInterval(state.poller);
    state.runId = runId;
    state.statusRequest += 1;
    state.pollPending = false;
    const url = new URL(location.href);
    url.searchParams.set("run", runId);
    url.searchParams.delete("new");
    history.replaceState(null, "", url);
    $("savedRunSelect").value = runId;
    $("setupView").hidden = true;
    $("runStatus").hidden = false;
    $("statusTitle").textContent = "WINGS run";
    $("statusSubtitle").textContent = "Loading saved run status…";
    $("metricRunId").textContent = runId;
    for (const id of ["metricStatus", "metricSamples", "metricElapsed"]) $(id).textContent = "—";
    setActivity(false);
    $("runLog").textContent = "Waiting for log output…";
    $("stopRun").disabled = true;
    $("resumeRun").hidden = true;
    $("resultsLink").hidden = true;
    $("resultsLink").removeAttribute("href");
    renderTimeline();
    renderIrmaProgress();
    renderFailures();
    renderAttempts();
    state.poller = setInterval(pollStatus, 3000);
    pollStatus();
  }

  function parseMetadata(text) {
    const normalized = text.replace(/\r\n/g, "\n").replace(/\r/g, "\n");
    const lines = normalized.split("\n").filter((line) => line.trim().length > 0);
    if (!lines.length) throw new Error("Metadata file is empty.");
    const header = lines[0].split("\t");
    const index = header.indexOf("sample_id");
    if (index < 0) throw new Error("Metadata must contain a sample_id column.");
    const ids = [];
    for (const line of lines.slice(1)) {
      const fields = line.split("\t");
      const id = (fields[index] || "").trim();
      if (id) ids.push(id);
    }
    if (!ids.length) throw new Error("Metadata contains no sample_id values.");
    return ids;
  }

  function validateMetadataMatch() {
    if (!state.reads.length || !state.metadataIds.length) return {ok: false, detail: "Select both sequencing files and metadata."};
    const reads = new Set(state.reads.map((file) => stripFastq(file.name)));
    const metadata = new Set(state.metadataIds);
    const missingMetadata = [...reads].filter((id) => !metadata.has(id));
    const missingReads = [...metadata].filter((id) => !reads.has(id));
    if (missingMetadata.length || missingReads.length) {
      const parts = [];
      if (missingMetadata.length) parts.push(`${missingMetadata.length} FASTQ sample(s) missing from metadata`);
      if (missingReads.length) parts.push(`${missingReads.length} metadata sample(s) missing a FASTQ`);
      return {ok: false, detail: parts.join("; ")};
    }
    return {ok: true, detail: `${reads.size} sample IDs match exactly.`};
  }

  function renderReads() {
    if (!state.reads.length) {
      $("readsSummary").textContent = "No sequencing files selected.";
      return;
    }
    const total = state.reads.reduce((sum, file) => sum + file.size, 0);
    const extensions = new Set(state.reads.map((file) => fastqExtension(file.name)));
    const duplicateIds = state.reads.map((f) => stripFastq(f.name)).filter((id, i, all) => all.indexOf(id) !== i);
    const notes = [`${state.reads.length} FASTQ file(s) · ${formatBytes(total)}`];
    if (extensions.has("")) notes.push("⚠ One or more files do not have a supported FASTQ extension.");
    if (extensions.size > 1) notes.push("⚠ Use a consistent FASTQ extension for this run.");
    if (duplicateIds.length) notes.push(`⚠ Duplicate sample IDs detected: ${[...new Set(duplicateIds)].join(", ")}`);
    $("readsSummary").textContent = notes.join("\n");
  }

  function renderMetadata() {
    if (!state.metadata) {
      $("metadataSummary").textContent = "No metadata file selected.";
      return;
    }
    if (state.metadataError) {
      $("metadataSummary").textContent = `⚠ ${state.metadataError}`;
      return;
    }
    const match = validateMetadataMatch();
    $("metadataSummary").textContent = `${state.metadata.name} · ${state.metadataIds.length} metadata sample(s)\n${match.ok ? "✓" : "⚠"} ${match.detail}`;
  }

  function preflightRows() {
    const match = validateMetadataMatch();
    const extensions = new Set(state.reads.map((f) => fastqExtension(f.name)));
    const readsOk = state.reads.length > 0 && !extensions.has("") && extensions.size === 1;
    const metadataOk = Boolean(state.metadata && !state.metadataError);
    const runnerOk = Boolean(state.runner && state.runner.snakemake_available && state.runner.config_yaml_present);
    let runnerDetail = "Start the local runner with: python scripts/wings_local_runner.py";
    if (state.runner && !state.runner.snakemake_available) runnerDetail = "Snakemake is not available in the runner environment.";
    else if (state.runner && !state.runner.config_yaml_present) runnerDetail = "Create the local base config: cp config/config.example.yaml config.yaml";
    else if (runnerOk) runnerDetail = `Ready · ${state.runner.snakemake}`;
    return [
      [runnerOk, "Local WINGS runner", runnerDetail],
      [readsOk, "Sequence inputs", readsOk ? `${state.reads.length} FASTQ file(s) selected` : "Select FASTQ files with one consistent extension"],
      [metadataOk, "Metadata structure", metadataOk ? `${state.metadataIds.length} sample rows detected` : (state.metadataError || "Select metadata.tsv")],
      [match.ok, "Sample matching", match.detail],
      [Boolean($("runName").value.trim()), "Run name", $("runName").value.trim() || "Enter a run name"]
    ];
  }

  function renderPreflight() {
    const rows = preflightRows();
    $("preflightList").innerHTML = rows.map(([ok, label, detail]) => `
      <li class="preflight-item">
        <span class="status-icon ${ok ? "status-ok" : "status-error"}" aria-hidden="true">${ok ? "✓" : "×"}</span>
        <div><strong>${label}</strong><div class="timeline-meta">${detail}</div></div>
        <span>${ok ? "Ready" : "Needs attention"}</span>
      </li>`).join("");

    const enabled = [
      $("optGenoflu").checked && "GenoFLU",
      $("optVadr").checked && "VADR",
      $("optPhylogeny").checked && "Phylogenetics",
      $("optExplorer").checked && "Surveillance Explorer"
    ].filter(Boolean);
    $("reviewBox").textContent = [
      `Run: ${$("runName").value.trim() || "—"}`,
      `Samples: ${state.reads.length}`,
      `Cores: ${$("cores").value}`,
      `Parallel tasks: ${$("maxParallelJobs").value}`,
      `Analysis: ${enabled.join(", ") || "core workflow only"}`
    ].join("\n");
    $("startRun").disabled = !rows.every((row) => row[0]);
  }

  async function uploadFile(runId, kind, file) {
    const url = `${localOrigin}/api/runs/${encodeURIComponent(runId)}/files?kind=${encodeURIComponent(kind)}&filename=${encodeURIComponent(file.name)}`;
    const response = await fetch(url, {method: "PUT", headers: {"Content-Type": "application/octet-stream"}, body: file});
    if (!response.ok) throw new Error((await response.text()) || `Upload failed: ${file.name}`);
  }

  async function startRun() {
    $("startRun").disabled = true;
    $("startRun").textContent = "Preparing local run…";
    try {
      const create = await fetch(`${localOrigin}/api/runs`, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
          name: $("runName").value.trim(),
          cores: Number($("cores").value || 1),
          max_parallel_jobs: Number($("maxParallelJobs").value || 1),
          options: {
            genoflu: $("optGenoflu").checked,
            vadr: $("optVadr").checked,
            phylogeny: $("optPhylogeny").checked,
            explorer: $("optExplorer").checked
          }
        })
      });
      if (!create.ok) throw new Error(await create.text());
      const created = await create.json();
      state.runId = created.run_id;

      for (let i = 0; i < state.reads.length; i += 1) {
        $("startRun").textContent = `Copying FASTQ ${i + 1}/${state.reads.length}…`;
        await uploadFile(state.runId, "reads", state.reads[i]);
      }
      $("startRun").textContent = "Copying metadata…";
      await uploadFile(state.runId, "metadata", state.metadata);

      const launch = await fetch(`${localOrigin}/api/runs/${encodeURIComponent(state.runId)}/start`, {method: "POST"});
      if (!launch.ok) throw new Error(await launch.text());
      openRun(state.runId);
      refreshRuns();
    } catch (error) {
      alert(`WINGS could not start the run.\n\n${error.message}`);
      $("startRun").disabled = false;
      $("startRun").textContent = "Run WINGS Pipeline";
    }
  }

  function timelineIcon(status) {
    if (status === "complete") return ["✓", "status-ok"];
    if (status === "running") return ["◉", "status-running"];
    if (status === "failed") return ["×", "status-error"];
    if (status === "warning") return ["!", "status-warning"];
    if (status === "partial") return ["◐", "status-warning"];
    if (status === "interrupted") return ["!", "status-warning"];
    return ["○", "status-waiting"];
  }

  function renderTimeline(stages, progress = {}) {
    const timeline = $("timeline");
    timeline.replaceChildren();
    for (const [key, label] of stageDefinitions) {
      const status = (stages && stages[key]) || "waiting";
      const [icon, cls] = timelineIcon(status);
      const item = document.createElement("li");
      item.className = `timeline-item${status === "running" ? " current" : ""}`;
      item.dataset.stage = key;
      const symbol = document.createElement("span");
      symbol.className = `status-icon ${cls}`;
      symbol.setAttribute("aria-hidden", "true");
      symbol.textContent = icon;
      const body = document.createElement("div");
      const heading = document.createElement("strong");
      heading.textContent = label;
      const meta = document.createElement("div");
      meta.className = "timeline-meta";
      const labels = {partial: "Partially complete", interrupted: "Interrupted", skipped: "Not required"};
      meta.textContent = labels[status] || status.charAt(0).toUpperCase() + status.slice(1);
      body.append(heading, meta);
      const detail = progress[key];
      if (detail) {
        const counts = document.createElement("div");
        counts.className = "timeline-meta";
        const count = detail.completed ?? 0;
        counts.textContent = Number.isInteger(detail.expected)
          ? `${count} of ${detail.expected} scheduled jobs completed`
          : `${count} jobs completed; total ${detail.totals_provisional ? "provisional" : "unavailable"}`;
        if (detail.active > 0) counts.textContent += ` · ${detail.active} running`;
        body.append(counts);
        if (key === "assembly" && Number.isInteger(detail.irma_completed)) {
          const irma = document.createElement("div");
          irma.className = "timeline-meta";
          irma.textContent = Number.isInteger(detail.irma_expected)
            ? `${detail.irma_completed} of ${detail.irma_expected} scheduled IRMA jobs completed`
            : `${detail.irma_completed} IRMA jobs completed in this attempt`;
          body.append(irma);
        }
        if (detail.failed_rules?.length) {
          const failed = document.createElement("div");
          failed.className = "timeline-meta";
          failed.textContent = `Failed task: ${detail.failed_rules.join(", ")}`;
          body.append(failed);
        }
        if (detail.cached_work_possible && status === "complete") {
          const verified = document.createElement("div");
          verified.className = "timeline-meta";
          verified.textContent = "Workflow completed successfully; counts may exclude reused outputs.";
          body.append(verified);
        }
      }
      item.append(symbol, body, document.createElement("span"));
      timeline.append(item);
    }
  }

  function elapsedText(started, finished) {
    if (!started) return "—";
    const end = finished ? new Date(finished).getTime() : Date.now();
    const seconds = Math.max(0, Math.round((end - new Date(started).getTime()) / 1000));
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    return h ? `${h}h ${m}m` : `${m}m`;
  }

  function milestoneDuration(seconds) {
    if (!Number.isFinite(seconds) || seconds < 0) return "—";
    const total = Math.floor(seconds);
    const h = Math.floor(total / 3600);
    const m = Math.floor((total % 3600) / 60);
    const s = total % 60;
    return h ? `${h}h ${m}m ${s}s` : m ? `${m}m ${s}s` : `${s}s`;
  }

  function renderIrmaProgress(samples = []) {
    const section = $("irmaProgress");
    const container = $("irmaProgressSamples");
    if (!section || !container) return;
    // Keep a user's expanded history open while status polling refreshes it.
    const expanded = new Set([...container.querySelectorAll("details[open]")]
      .map((node) => node.dataset.sampleId));
    container.replaceChildren();
    section.hidden = !samples.length;
    for (const sample of samples) {
      const card = document.createElement("article");
      card.className = "summary-box";
      card.style.marginBottom = "1rem";
      card.style.whiteSpace = "normal";
      card.style.overflowWrap = "anywhere";
      const heading = document.createElement("h4");
      heading.textContent = sample.sample_id;
      const milestones = sample.recent_milestones || [];
      const latest = milestones[milestones.length - 1];
      const message = document.createElement("p");
      message.textContent = latest
        ? `Last recorded milestone: ${latest.message}`
        : "No timestamped milestones have been recorded yet.";
      const modified = new Date(sample.last_modified);
      const freshness = document.createElement("p");
      freshness.className = "help";
      freshness.textContent = Number.isNaN(modified.getTime()) ? "Log update time unavailable."
        : `Log last changed: ${modified.toLocaleString()} · ${formatBytes(sample.log_size_bytes)}`;
      card.append(heading, message, freshness);
      if (milestones.length) {
        const details = document.createElement("details");
        details.dataset.sampleId = sample.sample_id;
        details.open = expanded.has(sample.sample_id);
        const summary = document.createElement("summary");
        summary.textContent = `Recorded milestones (${milestones.length})`;
        const note = document.createElement("p");
        note.className = "help";
        note.textContent = "Timestamps use the log's clock; its time zone is not recorded. Durations are gaps between consecutive messages. A dash means the interval is unknown.";
        const list = document.createElement("ol");
        for (const event of milestones) {
          const item = document.createElement("li");
          item.textContent = `${event.timestamp} · ${event.message} · ${milestoneDuration(event.seconds_since_previous)} since previous message`;
          list.append(item);
        }
        details.append(summary, note, list);
        if (sample.earlier_milestones_omitted) {
          const notice = document.createElement("p");
          notice.className = "help";
          notice.textContent = "Showing recent milestones. Earlier entries remain in the sample's IRMA log.";
          details.append(notice);
        }
        card.append(details);
      }
      container.append(card);
    }
  }

  async function pollStatus() {
    if (!state.runId || state.pollPending) return;
    state.pollPending = true;
    const runId = state.runId;
    const request = ++state.statusRequest;
    const isCurrent = () => runId === state.runId && request === state.statusRequest;
    let rendering = false;
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 10000);
    try {
      const response = await fetch(`${localOrigin}/api/runs/${encodeURIComponent(runId)}`, {
        cache: "no-store", signal: controller.signal
      });
      if (!isCurrent()) return;
      if (response.status === 404 || response.status === 400) {
        clearInterval(state.poller);
        setActivity(false);
        $("metricStatus").textContent = "unavailable";
        $("statusSubtitle").textContent = "This run could not be found. Choose another saved run or check that the runner is using the same run directory.";
        $("stopRun").disabled = true;
        $("resultsLink").hidden = true;
        return;
      }
      if (!response.ok) throw new Error("status unavailable");
      const run = await response.json();
      if (!isCurrent()) return;
      if (!run || typeof run !== "object" || typeof run.status !== "string") {
        throw new Error("The runner returned an invalid status response.");
      }
      rendering = true;
      $("statusTitle").textContent = run.name || "WINGS run";
      $("statusSubtitle").textContent =
        run.status === "running"
          ? "WINGS is flying through this run locally."
          : run.status === "complete"
            ? "WINGS has landed successfully."
            : ["failed", "stopped"].includes(run.status)
              ? `The launcher attempt ${run.status}. Processing started separately in Terminal is not tracked here. Completed outputs remain on disk.`
              : `Launcher attempt ${run.status}.`;
      const statusLabel = {
        running: "flying",
        complete: "landed",
        failed: "failed",
        stopped: "stopped",
      }[run.status] || run.status;

      $("metricStatus").textContent = statusLabel;
      setActivity(run.status === "running");
      $("metricSamples").textContent = run.sample_count ?? "—";
      $("metricElapsed").textContent = elapsedText(run.started_at, run.finished_at);
      $("metricRunId").textContent = run.run_id;
      $("runLog").textContent = run.log_tail || "Waiting for log output…";
      $("runLog").scrollTop = $("runLog").scrollHeight;
      renderTimeline(run.stages, run.stage_progress);
      renderIrmaProgress(run.irma_progress);
      renderFailures(run.failures);
      renderAttempts(run.attempts);
      $("resumeRun").hidden = !run.can_resume;
      $("resumeRun").disabled = state.resumePending;
      $("stopRun").disabled = run.status !== "running";
      const resultsReady = run.status === "complete";
      $("resultsLink").hidden = !resultsReady;

      if (resultsReady) {
        clearInterval(state.poller);
        $("resultsLink").href = `results.html?run=${encodeURIComponent(run.run_id)}`;
      } else {
        $("resultsLink").removeAttribute("href");
        if (["failed", "stopped"].includes(run.status)) {
          clearInterval(state.poller);
        }
      }
    } catch (error) {
      if (!isCurrent()) return;
      setActivity(false);
      $("stopRun").disabled = true;
      $("statusSubtitle").textContent = rendering
        ? `Run status was received, but the page could not display it: ${error.message}. Reload the page to load the current interface.`
        : error.name === "AbortError"
          ? "The status request timed out. Displayed status may be out of date. Retrying…"
          : `Unable to load run status: ${error.message}. Displayed status may be out of date. Retrying…`;
    } finally {
      clearTimeout(timeout);
      if (isCurrent()) state.pollPending = false;
    }
  }

  function renderFailures(failures = []) {
    let panel = $("runFailures");
    if (!panel) {
      panel = document.createElement("section");
      panel.id = "runFailures";
      panel.className = "summary-box";
      panel.setAttribute("aria-label", "Recorded launcher failures");
      panel.setAttribute("aria-live", "polite");
      $("runLog").before(panel);
    }
    panel.replaceChildren();
    panel.hidden = !Array.isArray(failures) || !failures.length;
    if (panel.hidden) return;
    const heading = document.createElement("h4");
    heading.textContent = "Recorded launcher failures";
    panel.append(heading);
    for (const failure of failures) {
      const item = document.createElement("p");
      item.textContent = `${failure.sample_id ? `Sample ${failure.sample_id}: ` : ""}${failure.message || `Task ${failure.rule || "unknown"} failed.`}`;
      panel.append(item);
      for (const [index, href] of (failure.log_urls || []).entries()) {
        // Accept only this run's log endpoint, never external URLs from data.
        const url = new URL(href, localOrigin);
        if (url.origin !== localOrigin || url.pathname !== `/api/runs/${encodeURIComponent(state.runId)}/failure-log`) continue;
        const link = document.createElement("a");
        link.href = url.href;
        link.target = "_blank";
        link.rel = "noopener";
        link.textContent = `Open failure log ${index + 1}`;
        const row = document.createElement("p");
        row.append(link);
        panel.append(row);
      }
    }
  }

  function renderAttempts(attempts = []) {
    let panel = $("runAttempts");
    if (!panel) {
      panel = document.createElement("details");
      panel.id = "runAttempts";
      $("runLog").before(panel);
    }
    panel.replaceChildren();
    panel.hidden = !attempts.length;
    if (panel.hidden) return;
    const heading = document.createElement("summary");
    heading.textContent = `Launcher attempts (${attempts.length})`;
    panel.append(heading);
    for (const [index, attempt] of attempts.entries()) {
      const row = document.createElement("p");
      row.textContent = `Attempt ${index + 1}: ${attempt.status} · ${attempt.started_at || "start time unavailable"} `;
      if (attempt.log_url) {
        const url = new URL(attempt.log_url, localOrigin);
        if (url.origin === localOrigin && url.pathname === `/api/runs/${encodeURIComponent(state.runId)}/attempt-log`) {
          const link = document.createElement("a");
          link.href = url.href;
          link.target = "_blank";
          link.rel = "noopener";
          link.textContent = "Open attempt log";
          row.append(link);
        }
      }
      panel.append(row);
    }
  }

  async function resumeRun() {
    if (!state.runId || state.resumePending) return;
    const runId = state.runId;
    state.statusRequest += 1;
    clearInterval(state.poller);
    state.resumePending = true;
    $("resumeRun").disabled = true;
    $("resumeRun").textContent = "Resuming…";
    try {
      const response = await fetch(`${localOrigin}/api/runs/${encodeURIComponent(runId)}/resume`, {method: "POST"});
      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.error || "The runner could not resume this run.");
      }
      if (runId === state.runId) {
        openRun(runId);
        refreshRuns();
      }
    } catch (error) {
      if (runId === state.runId) $("statusSubtitle").textContent = `Resume failed: ${error.message}`;
    } finally {
      state.resumePending = false;
      $("resumeRun").disabled = false;
      $("resumeRun").textContent = "Resume run";
    }
  }

  async function stopRun() {
    if (!state.runId || !confirm("Stop this WINGS run? Completed outputs will remain on disk.")) return;
    await fetch(`${localOrigin}/api/runs/${encodeURIComponent(state.runId)}/stop`, {method: "POST"});
    pollStatus();
  }

  function defaultName() {
    const d = new Date();
    const pad = (n) => String(n).padStart(2, "0");
    return `WINGS ${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}`;
  }

  $("runName").value = defaultName();
  document.querySelectorAll(".step-button").forEach((button) => button.addEventListener("click", () => setStep(Number(button.dataset.step))));
  $("backButton").addEventListener("click", () => setStep(state.step - 1));
  $("nextButton").addEventListener("click", () => setStep(state.step + 1));
  $("readsFiles").addEventListener("change", (event) => { state.reads = [...event.target.files]; renderReads(); renderMetadata(); });
  $("metadataFile").addEventListener("change", async (event) => {
    state.metadata = event.target.files[0] || null;
    state.metadataIds = [];
    state.metadataError = "";
    if (state.metadata) {
      try { state.metadataIds = parseMetadata(await state.metadata.text()); }
      catch (error) { state.metadataError = error.message; }
    }
    renderMetadata();
  });
  ["runName", "cores", "maxParallelJobs", "optGenoflu", "optVadr", "optPhylogeny", "optExplorer"].forEach((id) => $(id).addEventListener("change", () => { if (state.step === 4) renderPreflight(); }));
  $("startRun").addEventListener("click", startRun);
  $("stopRun").addEventListener("click", stopRun);
  // Keep updated JavaScript compatible with an older cached run page.
  if (!$("resumeRun")) {
    const button = document.createElement("button");
    button.id = "resumeRun";
    button.className = "btn btn-primary";
    button.type = "button";
    button.hidden = true;
    button.textContent = "Resume run";
    $("stopRun").before(button);
  }
  $("resumeRun").addEventListener("click", resumeRun);
  $("savedRunSelect").addEventListener("change", (event) => openRun(event.target.value));
  $("refreshRuns").addEventListener("click", refreshRuns);

  renderReads();
  renderMetadata();
  renderTimeline();
  setStep(0);
  checkRunner();
  if (localMode && initialParams.get("run")) openRun(initialParams.get("run"));
  refreshRuns();
  setInterval(checkRunner, 10000);
})();
