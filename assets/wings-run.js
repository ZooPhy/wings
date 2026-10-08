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
    poller: null
  };

  const $ = (id) => document.getElementById(id);
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
    $("statusActivity").classList.remove("running");
    $("runLog").textContent = "Waiting for log output…";
    $("stopRun").disabled = true;
    $("resultsLink").hidden = true;
    $("resultsLink").removeAttribute("href");
    renderTimeline();
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
          cores: Number($("cores").value || 4),
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
    return ["○", "status-waiting"];
  }

  function renderTimeline(stages) {
    $("timeline").innerHTML = stageDefinitions.map(([key, label]) => {
      const status = (stages && stages[key]) || "waiting";
      const [icon, cls] = timelineIcon(status);
      return `<li class="timeline-item ${status === "running" ? "current" : ""}">
        <span class="status-icon ${cls}" aria-hidden="true">${icon}</span>
        <div><strong>${label}</strong><div class="timeline-meta">${status.charAt(0).toUpperCase() + status.slice(1)}</div></div>
        <span></span>
      </li>`;
    }).join("");
  }

  function elapsedText(started, finished) {
    if (!started) return "—";
    const end = finished ? new Date(finished).getTime() : Date.now();
    const seconds = Math.max(0, Math.round((end - new Date(started).getTime()) / 1000));
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    return h ? `${h}h ${m}m` : `${m}m`;
  }

  async function pollStatus() {
    if (!state.runId) return;
    const runId = state.runId;
    try {
      const response = await fetch(`${localOrigin}/api/runs/${encodeURIComponent(runId)}`, {cache: "no-store"});
      if (runId !== state.runId) return;
      if (response.status === 404 || response.status === 400) {
        clearInterval(state.poller);
        $("statusActivity").classList.remove("running");
        $("metricStatus").textContent = "unavailable";
        $("statusSubtitle").textContent = "This run could not be found. Choose another saved run or check that the runner is using the same run directory.";
        $("stopRun").disabled = true;
        $("resultsLink").hidden = true;
        return;
      }
      if (!response.ok) throw new Error("status unavailable");
      const run = await response.json();
      if (runId !== state.runId) return;
      $("statusTitle").textContent = run.name || "WINGS run";
      $("statusSubtitle").textContent =
        run.status === "running"
          ? "WINGS is flying through this run locally."
          : run.status === "complete"
            ? "WINGS has landed successfully."
            : `Run ${run.status}.`;
      const statusLabel = {
        running: "flying",
        complete: "landed",
        failed: "failed",
        stopped: "stopped",
      }[run.status] || run.status;

      $("metricStatus").textContent = statusLabel;
      $("statusActivity").classList.toggle("running", run.status === "running");
      $("metricSamples").textContent = run.sample_count ?? "—";
      $("metricElapsed").textContent = elapsedText(run.started_at, run.finished_at);
      $("metricRunId").textContent = run.run_id;
      $("runLog").textContent = run.log_tail || "Waiting for log output…";
      $("runLog").scrollTop = $("runLog").scrollHeight;
      renderTimeline(run.stages);
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
      if (runId !== state.runId) return;
      $("statusActivity").classList.remove("running");
      $("stopRun").disabled = true;
      $("statusSubtitle").textContent = "Connection lost. Displayed status may be out of date. Reconnecting to the local runner…";
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
  ["runName", "cores", "optGenoflu", "optVadr", "optPhylogeny", "optExplorer"].forEach((id) => $(id).addEventListener("change", () => { if (state.step === 4) renderPreflight(); }));
  $("startRun").addEventListener("click", startRun);
  $("stopRun").addEventListener("click", stopRun);
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
