# WINGS questions and answers

[Back to README](../README.md) · [Command-line guide](command-line-guide.md) · [Report/reference guide](report-reference.md)

This Q&A covers the current workflow and the supplied **WINGS Desktop developer preview 0.1.12**. Desktop, native-runner and cluster instructions are identified separately because their installation and storage mechanisms differ.

**Jump to:** [Setup and settings](#desktop-setup-and-settings) · [Folders and storage](#folders-and-storage) · [Phylodynamics](#phylodynamics) · [Context and reports](#context-and-report-interpretation) · [Ollama](#ollama-and-briefings) · [Troubleshooting](#troubleshooting-and-recovery)

## Desktop setup and settings

### Do I need Python, Conda or Snakemake on my Mac?

Not for WINGS Desktop. Install Docker Desktop separately, then use WINGS.app. The app prepares the workflow runtime and its dependencies. First setup and the first use of some analysis modules require downloads.

The native runner and command-line workflow still need a compatible environment. Follow the [command-line guide](command-line-guide.md) for those routes; do not run its installation commands inside the desktop app's managed release directory.

### Is WINGS a single executable or a single container?

The Mac app provides one launch point. It manages a controller container, the workflow's IRMA/VADR containers, rule-specific Conda environments inside the controller, and persistent data in the selected workspace. References and models are prepared separately. It is not a self-contained offline executable.

The supplied app is an unsigned developer preview, not a signed/notarized public installer. Automated tests and successful setup on one machine are not complete installer or scientific validation.

### How do I know setup is progressing?

The browser setup page shows six steps:

1. Check Docker Desktop.
2. Install WINGS workflow.
3. Prepare analysis runtime.
4. Prepare influenza references.
5. Prepare analysis tools.
6. Start WINGS.

It displays the current substep, elapsed time and status updates. The bar measures completed steps, not a prediction of remaining time. A BLAST database build can take a while without producing another output line. A quiet-output notice is different from a missing heartbeat, which produces a waiting warning.

Use **Settings → View setup progress** to return to the page. Closing the progress tab does not cancel setup. On failure, the page identifies the step and offers the technical log; reopening WINGS retries setup after the cause is addressed.

### Can I add my NCBI email or eBird key later?

Yes. Choose **Add later** during setup. WINGS remembers that choice for the workspace and allows setup to continue. Add the value later through Settings.

An NCBI contact email is required when submitting Phylodynamics reference retrieval. An eBird Status & Trends key is needed for uncached abundance products. Other analyses and already-cached abundance products do not acquire those requirements merely because the fields are blank.

### Which eBird key do I need? Does a hyphen work?

The abundance-download setting expects an **eBird Status & Trends access key**, which is separate from a general eBird API token. Obtain it through the [Status & Trends access request](https://ebird.org/st/request).

Hyphens and letter case are preserved. Surrounding clipboard whitespace is trimmed; internal spaces or unsupported characters are rejected. Saving a key does not verify permission to download every product; the service checks access when a download is attempted.

The observation-data context is a separate route: it uses an authorized eBird Basic Dataset (EBD) download and matching sampling-event data. Entering an abundance key does not import those files.

### Why does WINGS ask for credentials again?

Current desktop versions store values and **Add later** choices per workspace. Reopening the same workspace should not repeat first-run prompts. A newly selected workspace has separate settings.

If the same workspace still prompts every time, confirm that the updated app is being opened and that the workspace is writable. Earlier preview versions had a prompt-guard defect. Keep the workspace when replacing the app; deleting it is not a credential repair.

### Does changing a setting close WINGS?

Saving, skipping or cancelling a settings dialog returns to the launcher menu. It should not close the launcher unexpectedly.

Choosing **Open WINGS** is different: it hands setup and service work to the background coordinator and opens the browser. The launcher can then exit and its Dock icon can disappear. The Docker service continues. Reopen WINGS.app whenever you need Settings.

### Does closing the browser stop an analysis?

No. Keep Docker Desktop running and the Mac awake while jobs execute. Finish or stop jobs in the browser before using **Settings → Stop WINGS service**. That action stops the controller; already-started sibling analysis containers may need to finish or be stopped in Docker Desktop.

### What does “an earlier WINGS version is running” mean?

The launcher found a service using a different bundled source version or configuration. It does not silently replace an active service. Finish or stop its jobs, use **Settings → Stop WINGS service**, quit the launcher, then open the new app.

For the 0.1.12 update, one restart is required because the runner changed. Saved credentials and reference caches are reused. Later changes to Ollama defaults need a browser refresh for new jobs; changes to shared folders need a service restart.

## Folders and storage

### Can I choose folders outside the default list?

For **input/context data**, yes. The desktop picker includes accessible Home, Desktop, Documents, Downloads, the workspace and external drives. Paste an absolute Mac path or `~/…` and choose **Go**. For another location, use **Settings → Share a folder with WINGS**, select it with the native Mac chooser, then restart the service after active jobs finish.

Docker Desktop and macOS must allow access. A mounted drive must be connected. Hidden child folders are not listed in the browser. The current share parser does not accept every possible filesystem name, including names with commas, colons or line breaks; ordinary spaces are supported.

### Does choosing a folder upload or copy its files?

The context folder picker selects a path on the computer running WINGS. It does not itself upload, copy or prepare the data. **Prepare context** is a separate action. Shared input folders are read-only in the controller; the workspace is writable for prepared data and outputs.

Read uploads through the browser's ordinary file picker are a separate operation and are stored with the job.

### Why is output storage restricted to the workspace?

The desktop app keeps writable run storage inside its managed workspace. Input folder sharing does not turn every shared location into an output directory. Choose a suitable parent location when creating the workspace; the native runner has separate configurable run/cache paths if you need a source-based deployment.

Removing an input share removes container access after restart; it does not delete that folder's files.

### Where are my runs, caches and settings?

Desktop runs are under **WINGS Workspace/runs/**, alongside `cache/`, `releases/` and `logs/`. Use **Settings → Open workspace**. Workspace settings are independent of a source checkout such as `~/wings`.

The native runner defaults to `~/.wings/runs`. A run directory contains `<run-id>/state.json`. To reopen a different native run collection:

```bash
python scripts/wings_local_runner.py --runs-dir /path/to/wings/runs
```

Select the directory containing the run folders. Changing a storage setting does not move existing runs. Refresh the saved-run list after starting the runner with the correct location.

## Phylodynamics

### Must I also select Phylogenetics?

No. **Phylogenetics** produces sample-only segment trees. **Phylodynamics** constructs its own reference-based tree inputs and includes Surveillance Explorer. It is a separate optional analysis.

The current submission preset is for **H5 HA**. That scope is narrower than the general influenza A sequencing workflow. Enabling a module does not make an ineligible sample usable for that analysis.

### Where do I choose BEAST?

Enable **Phylodynamics** in job submission to reveal **Fast / BEAST (MCMC)**. Fast is selected by default. This choice schedules the analysis for the new job.

Fast/BEAST buttons in a completed report only switch between results already present. They do not launch MCMC. If submission shows only the older **Phylodynamics (Fast)** checkbox, update the complete app/backend; adding a viewer asset alone does not add BEAST execution.

### What is the difference between Fast and BEAST?

| Method | Dates and topology | Geographic reconstruction |
| --- | --- | --- |
| Fast | One fixed dated maximum-likelihood tree. | Conditional Bayesian location probabilities and complete sampled geographic histories, with numerical and Monte Carlo checks. |
| BEAST | Posterior dates from BEAST MCMC on the fixed rooted topology. | Conditional geographic mapping over accepted dated draws, after convergence, precision and provenance checks. |

The BEAST route propagates dating uncertainty. It is a modular analysis, not joint BEAST phylogeography, and neither current route samples topology uncertainty. Fast does not provide date uncertainty by drawing more geographic histories.

See [Bayesian dating](bayesian-dating.md) and [posterior geography](posterior-phylogeography.md) for the model and diagnostic requirements.

### Which result is shown by default?

The standard primary reference set is **HA · Location/time balanced · Set 1**, designated before examining results. **Posterior summary** is the default presentation. If the primary analysis is unavailable, WINGS does not silently substitute whichever alternative looks preferable.

Other reference sets appear under **Advanced → Reference sampling**. They remain separate sensitivity analyses rather than being pooled into one posterior.

### Does “posterior summary” mean the median?

It depends on the quantity:

| Quantity | Summary |
| --- | --- |
| Ancestor location color | The most probable location: the posterior mode. Locations are categories and do not have a meaningful numeric median. |
| Location-probability bars | The probability distribution over locations for that ancestor. |
| Fast node date | The fixed date from the dated tree. |
| BEAST node date | The posterior median date. |
| Map/chord jump count | The posterior mean number of inferred changes, through the selected date and within the displayed scope. |

Individually most probable node locations do not constitute one sampled trajectory. A map arrow can therefore be supported by sampled histories even when the modal states at nearby displayed nodes are the same.

### Why can a node color disagree with its highest probability bar?

In **Posterior summary**, it should match the highest-probability displayed location. Grouped probabilities are summed before choosing the displayed regional mode.

In **One posterior draw**, the color is the state sampled in that reconstruction. A location with less than the highest probability can legitimately be sampled. The probability bars still summarize all draws, so they need not match that draw's color. If a mismatch remains in Posterior summary after refreshing the viewer, report it as a rendering/data issue.

### Is a “posterior draw” the same thing as a “jump”?

No. A posterior draw is one complete sampled geographic history, including ancestral states and changes along branches. It can have zero, one or many **Markov jumps**. The draw number selects a reconstruction, not a particular change event and not a performance rank.

In Fast mode these are conditional geographic draws on the fixed dated tree, not independent BEAST tree samples. The selected draw drives the map, tree and chord diagram; panels labeled as posterior summaries continue to aggregate draws.

### What does a map arrow mean?

An arrow shows the direction of inferred changes between location states. In the summary view, routes aggregate posterior jump counts; in the sampled view, they come from the selected history. These are not observed bird flights, established transmission links, or simple counts of differently colored tree nodes.

Regional marker positions are display anchors. Selecting a focus location limits attention to its connected routes. Initially, the map displays the six strongest routes to reduce overlap. **Show all**, route highlighting, and the expanded map reveal additional connections; display filtering does not change the underlying inference.

### Are the circles along a branch Markov jumps? Is the tree bifurcating?

Circles identify retained ancestral nodes. After reference-only tips and branches are removed from the study view, an ancestor can have only one displayed descendant and appear along a horizontal branch. Multiple circles along that branch do not by themselves imply additional branching or multiple jumps.

In a sampled history, geographic jumps are changes in branch-state color along time. In the summary view, node colors show marginal probabilities rather than a complete branch history. The displayed study subtree can contain unary nodes; its appearance alone does not establish that the complete fitted tree has a polytomy.

### How is the focus chosen if my samples are not from Kentucky?

WINGS uses the study samples' recorded locations. On initial selection, the location with the most study samples is the default, with alphabetical tie-breaking. Study locations appear first in the selector. A valid existing user selection can be retained as the view changes.

Kentucky has no special default. In a regional overview, study locations stay separate while other locations are grouped. A label such as “U.S. South (excluding Kentucky)” is appropriate only when that exclusion is actually part of the current study-aware grouping.

Use the finest supported location recorded in the analysis metadata; missing state information should not be replaced by a guessed state. Correct input metadata and rerun affected inference if the scientific location assignments are wrong. A presentation refresh alone cannot repair an incorrect fitted model.

### Does geographic grouping change the analysis?

No. Regional grouping is a display operation. Probabilities and between-group counts are aggregated from the original location states. Changes within a group do not appear as between-group arrows. Expanding a region reveals represented states/countries; it does not refit the CTMC or add geographic precision to the inputs.

### Is the location/time-balanced reference set always better?

No sampling design is automatically best for every scientific question. Balanced sampling reduces domination by heavily represented locations or collection periods. Random comparison sets sample the eligible pool under a different design. Both retain the workflow's reserved close references.

The primary balanced set is chosen in advance for consistency. Sensitivity is examined by comparing separately fitted reference sets and their uncertainty, diagnostics and inferred entries—not by choosing the result with the smallest entry count or strongest-looking route.

**Set 1, Set 2 and Set 3** identify different reference selections. They are not model-quality ranks, MCMC chains or individual posterior draws. The viewer's advanced comparisons do not automatically select a “winning” analysis.

### What does the CTMC estimate? Why can directions have different counts?

The current geographic model uses a symmetric equal-rate CTMC with its configured rate prior. Conditioning on the tree and observed tip locations can still produce unequal counts in opposite directions. Those directional counts do not imply a fitted asymmetric matrix with a separate rate for every ordered location pair.

Rate-prior changes are analysis changes, not viewer controls. Record alternative priors as separate runs and compare them with the same diagnostic requirements; do not edit a completed result's settings to make a route appear stronger.

### What is included in entry and jump counts?

The viewer counts the WINGS study ancestry from its common ancestor to its study tips. Reference-only branches and the ancestral stem above that common ancestor are excluded. Zero-event histories remain in posterior denominators.

A missing or rejected analysis is not a zero-entry estimate. Unrepresented places and incomplete metadata limit what the model can distinguish. Numerical/convergence checks do not establish that the inferred geography is biologically true.

### What does the pale yellow date band mean?

When present, it marks the study ancestor's 95% highest posterior density interval. Fast's fixed dates do not acquire a date interval merely because the geographic histories vary. Consult the result's method and diagnostics to determine which uncertainties are represented.

### Is the demo showing real Phylodynamics for its sequencing samples?

No. Its Phylodynamics view is labeled a **simulated illustration** with synthetic identifiers. Real saved results must match the analyzed study samples in the destination report. The attachment tool rejects illustrative data when attaching results to a real run.

## Context and report interpretation

### Does eBird reporting frequency measure abundance or infection prevalence?

Neither. EBD reporting frequency uses complete-checklist reporting with an explicit sampling-event denominator. Modeled Status & Trends abundance is a different product, and neither measures influenza infection prevalence.

Use observations and sampling-event files from a matching release and geographic/date scope. Shared checklist context must not be added repeatedly across samples. Missing access or data is recorded as unavailable, not zero. See the [report/reference guide](report-reference.md#optional-ebird-reporting-context).

### Does a public genotype frequency describe population prevalence?

No. WINGS frequencies count the eligible sequenced study samples; public frequencies count the eligible public records, typically SRA runs. These denominators and sampling processes differ. Filters, collection/release coverage, missing genotype calls and submission bias affect comparisons.

### Does a nearby APHIS detection demonstrate transmission?

No. Space/time overlap supplies surveillance context. APHIS detections can lack sequence or accession links and do not establish a transmission chain with WINGS samples. Modeled seasonal abundance, migration estimates, weather and detections should retain their distinct units and time windows.

### Does opening an old report update it?

No. HTML reports and `.wings` bundles contain saved presentation and evidence. Updating the source/app changes subsequently generated reports; older files retain their embedded assets until refreshed or rebuilt.

Preserve the original bundle and use the appropriate [report maintenance procedure](report-reference.md#phylodynamics-report-maintenance). Changing colors, layout or focus defaults should not rewrite scientific JSON or rerun inference. Changing biological inputs, references or model settings is a new analysis operation.

## Ollama and briefings

### How do I configure and check Ollama in the app?

Install and start Ollama separately, then install a model that fits your computer. In **Settings → Configure Ollama**, enter the local address—normally `http://localhost:11434`—and its exact installed model name. Use **Save and check**, or **Settings → Check Ollama connection** after the updated WINGS service is ready.

Refresh the browser page before creating a new job. The job's model field starts with the saved default and can be explicitly overridden. Briefing generation remains opt-in. Existing jobs keep their recorded endpoint and model.

### What does the connection check test?

It requests the model list from inside the WINGS controller, verifying the same host/container path needed for analysis. It distinguishes an unreachable/invalid service from a missing model and lists installed names when appropriate.

It does not download a model, generate a briefing, measure model quality, or prove enough RAM is available. Configuration can be saved before setup, but checking requires a running updated service. A briefing-disabled job does not need working Ollama settings.

### Why can Ollama work on my Mac but fail from WINGS?

The analysis runs in Docker. The desktop integration maps Mac loopback addresses to `host.docker.internal` and bypasses HTTP proxies for the local destinations. Check that Ollama is running, the configured port is correct, and Docker Desktop can reach the host service. WINGS does not modify Ollama's bind address or the Mac firewall.

Desktop Settings accepts local HTTP endpoints, not an arbitrary remote service. Native advanced endpoint configuration is documented separately in [local model interpretation](local-llm-interpretation.md).

### What information does the model receive?

Structured result summaries, sample identifiers and metadata, available contextual evidence, and any explicitly supplied briefing context. WINGS does not send raw reads, consensus sequences or tree files to the briefing endpoint.

Using a locally served model keeps inference local. A cloud-backed model accessed through a local Ollama service is a different data-handling choice. Reports may embed the prompts, responses, evidence and diagnostics; inspect them before sharing.

### Is the generated briefing automatically reliable?

No. Staged generation and an additional model review support traceability but do not replace scientific review. The **Knowledge for action** panel summarizes the whole run; it does not change with individual sample selection and does not conduct new association tests. Missing evidence should remain explicit. Failed generation is shown as unavailable with diagnostics.

## Troubleshooting and recovery

### Why does the native runner reject Intel Python on Apple Silicon?

The native route expects a consistent ARM64 installation. Activate the intended environment by its full path and check it:

```bash
/path/to/arm64/environment/bin/python -c \
  "import platform, sys; print(sys.executable); print(platform.machine())"
```

It should report `arm64` for that route. Exporting `CONDA_SUBDIR=osx-arm64` does not convert an already-created Intel Python environment. The desktop preview deliberately uses Linux AMD64 inside Docker, which is separate from this native-runner check.

### What if the native runner says “Address already in use”?

A service already owns the requested port. Identify it and open the existing WINGS service if it is the intended one. Otherwise finish its jobs and stop that service before starting another. Do not terminate an unidentified process just to clear the port. Desktop mode uses its own local port rather than requiring the old native runner's port 8765.

### What if a Phylodynamics source file is missing after `git pull`?

“Already up to date” only means the checkout matches its configured upstream branch. It does not prove that separately developed backend files were committed there. Use a complete matching release/source snapshot and verify its dependencies. Do not create empty placeholder YAML or rule files: the workflow needs the full backend and matching generated assets.

A terminal repair script's missing NumPy/SciPy/PyYAML error refers to the Python running that script. Install its declared dependencies in that environment, or use the complete desktop package. Installing a package in a different Conda environment will not repair that interpreter.

### What if BLAST setup fails in a workspace whose name contains spaces?

The current setup stages local BLAST input and output in a space-free temporary directory, verifies the new database with `blastdbcmd`, and installs verified database files into the cache. Use the updated complete package and retry. Both temporary storage and the destination need enough free space. Do not bypass reference checksum or database verification to clear the error.

### What if abundance was unavailable before I added a key?

In desktop Settings, save the key, refresh the page and prepare context again if preparation previously reported missing access. New attempts read the saved key; active processes retain their existing environment.

For the native runner, export `EBIRDST_ACCESS_KEY` in the environment that launches it and restart when no jobs are active. Setting it in another terminal does not update an existing native server.

An unavailable phenology JSON can still be a completed workflow output. Ordinary resume need not rebuild it. With the run stopped, use its saved configuration to rerun `ebirdst_phenology` and dependent reports, preserving other outputs and the raster cache. See the [phenology recovery instructions](report-reference.md#ebird-status--trends-phenology-access-key-required-for-downloads).

### What if Porechop reports “Counter build belongs to another conda environment”?

For the affected stopped run, back up and edit its execution configuration to use the installed backend:

```yaml
porechop_counter_build: ""
```

For new native runs, update local `config.yaml`. For an existing browser run, use its `execution_config.yaml`; changing only the repository's config may not change the saved job. Check the generated value if retry regenerates it. Keep machine-specific Counter paths out of shared configuration.

### May I remove a Snakemake lock?

First verify that no active run or worker is using that working directory. Outputs in different directories do not necessarily mean different Snakemake working directories. Finish or stop the conflicting run and confirm its workers have exited. Only then use `--unlock` with the affected run's Snakefile and saved configuration if a stale lock remains.

### What should I share when reporting a setup problem?

Use **Settings → Export installation diagnostics**, and include the failed step and relevant error lines. The diagnostic export omits credentials, reads and run configurations. Setup logs are separate and can contain local paths; review them before sharing. Preserve the workspace so the failure can be investigated without discarding completed work.
