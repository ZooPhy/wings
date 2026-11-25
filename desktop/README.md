# WINGS Desktop — developer preview 0.1.14


## Unreleased: case-sensitive Linux dependency storage

The launcher now uses two persistent Docker-managed volumes per workspace for
Linux Conda environments and extracted package caches. A Mac bind mount can
collapse names such as `2621A` and `2621a` from `ncurses`. Both destinations are
checked for writability and distinct upper/lowercase filenames before setup
continues. Environment prefixes remain stable at `/opt/wings-conda-envs`; package
extraction uses `/opt/wings-conda-pkgs`. Resumed runs and seasonal bird-data
preparation use these same destinations instead of saved Mac cache paths.

This change requires a **rebuilt desktop app and runtime**. Finish or stop active
jobs, use **Settings → Stop WINGS service**, quit the launcher, replace WINGS.app,
and reopen the same workspace. Previously installed Mac-hosted Conda environments
are left intact and are not copied into the Linux volumes. Dependencies will be
created again; allow time and Docker disk space for downloads and extraction.
Reads, results, reference data, run history, and credentials remain in the workspace.
Review the resumed job plan because environment/source changes can rerun jobs.

Volumes are named `wings-conda-envs-v3-<workspace-id>` and
`wings-conda-pkgs-v3-<workspace-id>`. They survive app updates and service/container
replacement. Resetting Docker Desktop or deleting these volumes removes the
rebuildable dependencies, so workspace backups alone do not contain them. There
is no automatic cache deletion, volume pruning, or movement of existing data.
The app validates volume labels and rejects unexpected drivers/options.

The automated launcher tests simulate Docker. Before publishing a preview,
verify on a default case-insensitive Mac filesystem that real package extraction,
analysis, service restart, and resume all succeed. Test both a new workspace and
one containing a failed legacy environment. Keep end-to-end validation pending
until those checks pass.

For credentials already skipped during setup, the existing native menu is
**Settings → NCBI & eBird access → Add or update NCBI email / eBird access key**.
Refresh the browser after saving. The eBird Status and Trends access key is distinct
from the general eBird API key. Improving browser discoverability and preventing
progression past invalid metadata remain separate UI work.

## Previous preview changes

Version 0.1.14 adds the WINGS logo to the installation/setup progress page.
The supplied logo is bundled locally and copied alongside each new progress
page, so displaying it needs no internet connection. It retains its proportions
and includes alternate text.

This is a launcher presentation update. The workflow source archive and runtime
are byte-identical to 0.1.13, including its Porechop path-handling fix. Quit the
launcher, replace WINGS.app, and reopen it. An already-running 0.1.13 service can
stay running. The logo appears on newly created setup progress pages; previously
saved pages retain their existing presentation. If upgrading from before 0.1.13,
follow the stop-service and resume instructions below to apply that workflow fix.

Version 0.1.13 fixes the reported Porechop_ABI failure when the workspace,
installed tool or read paths contain spaces. The installed counter is launched
with an argument list instead of splitting a command string. Each sample gets
a separate space-free temporary directory. Installed Conda files are not patched,
reads are not relocated, and adapter-discovery/trimming options are retained.
A per-output provenance JSON records the tool/counter/wrapper hashes, arguments
and outcome. Failed scratch directories are retained for diagnosis.

**Update and resume:** wait for other jobs to finish or stop them in the browser.
Use Settings → Stop WINGS service, then Quit. Replace WINGS.app with this version
and reopen it using the same workspace. Open the failed run and choose Resume.
Keep its saved execution configuration and inputs. Snakemake determines which
outputs can be reused; changed rule code can cause affected trimming jobs to rerun.

Do not rename WINGS Workspace or delete the Conda cache to work around this error.
The Docker runtime recipe is unchanged; the existing image and reference caches
can be reused. This update changes bundled workflow source and needs a service
restart. Existing setup progress, key/email settings, folder sharing and Ollama
settings are retained.

Targeted tests reproduce the split-path error and exercise the repaired wrapper
with executable, input and config paths containing spaces, quotes and semicolons;
concurrent jobs; failure propagation; missing output; and existing output protection.
They use synthetic tool fixtures and real subprocesses, not a real biological run.
Mac/Docker/Porechop acceptance remains to be performed on the affected machine.

Version 0.1.12 adds **Settings → Configure Ollama** and **Settings → Check Ollama
connection**. Enter the server address on this Mac (normally
`http://localhost:11434`) and the exact installed model name. Choose **Save** or
**Save and check**. Configuration can be saved before initial setup; checking
requires the updated WINGS service to be running. Settings return to the launcher
menu afterward. Ollama and models are installed separately; WINGS does not pull
models or generate text during a connection check.

The check runs inside the WINGS controller and calls only Ollama's `/api/tags`.
It distinguishes an unreachable/invalid service from a missing selected model,
and lists installed names when the selected model is missing. This verifies
availability, not model quality, available RAM or successful briefing generation.
The briefing option remains off by default for each job.

The address accepts local HTTP endpoints (`localhost`, `127.0.0.1`, `[::1]`, or
`host.docker.internal`), a custom port, and an optional `/api/chat` suffix. WINGS
maps the Mac loopback addresses to Docker Desktop's `host.docker.internal`.
Configured HTTP proxies are bypassed for those local destinations in analysis
processes. WINGS does not change Ollama's bind address or Mac firewall settings.
If the check fails while Ollama is running, verify Docker Desktop host access
and the Ollama port. Real Mac/container connectivity still needs acceptance.

Settings are stored per workspace with owner-only permissions. Refresh the
WINGS browser page after changes: its model field picks up the saved default,
while a model explicitly chosen for a job can override it. The runner reads
current settings for new jobs, records the endpoint/model in that job's config,
and checks the recorded endpoint when resuming. Existing jobs keep their saved
settings. Invalid Ollama configuration does not block jobs without a briefing.

**Update:** finish active jobs, use **Settings → Stop WINGS service**, choose
Quit, replace WINGS.app and reopen it. This update changes the runner and needs
one service restart. Its Docker runtime recipe is unchanged, so the runtime
image, reference caches and credentials are retained. Later Ollama setting
changes take effect for new jobs without another service restart.

References: [Ollama model-list API](https://docs.ollama.com/api/tags),
[Ollama server configuration](https://docs.ollama.com/faq), and
[Docker Desktop host networking](https://docs.docker.com/desktop/features/networking/networking-how-tos/).

Version 0.1.11 opens a simple **setup progress page** in your usual browser before
expensive preparation begins. Six steps show completed, active and pending work:
Docker, workflow, runtime, influenza references, analysis tools and WINGS startup.
The bar counts completed steps; it is not a download percentage or time estimate.
Current substeps identify BLAST building/verification and model/tool downloads.
Elapsed time, live status updates and a quiet-output notice remain visible during
long operations. A missing heartbeat changes the page to a waiting warning rather
than continuing to claim setup is running. Errors keep the current step visible;
known disk, checksum, shared-folder and version conflicts include an action.

The progress page opens automatically and updates about every two seconds. Keep
Docker Desktop running. Closing the progress tab does not cancel preparation.
Use **Settings → View setup progress** to reopen it; choosing Open WINGS during
an existing setup reopens the same progress page. After success, WINGS opens in
another browser tab or window and the setup page shows completion. The technical
log is an optional link, not the primary status display. A browser that blocks
local files will need its administrator-approved local-file access policy.

Settings now return to the launcher menu after saving an email/key, choosing
Add later, sharing a folder, cancelling a settings dialog, or other actions.
The launcher stays available until you choose Quit or Open WINGS. Open WINGS
hands setup to the independent coordinator as before; closing that launcher does
not stop setup or running analyses.

**Update from 0.1.10:** choose Quit in the launcher, replace WINGS.app, then reopen
it. This is a launcher-only update: bundled workflow and runtime archives are
byte-identical to 0.1.10. The running service, saved settings, reference cache and
analyses can remain in place. The new progress page applies to subsequent launches.
No dependency installation is required on the Mac. The page contains fixed status
messages and timestamps only; emails, access keys and authenticated URLs are never
written into its status data. The native Cocoa setup helper has been removed from
the launch path. Real Mac/browser acceptance is still required; see VALIDATION.md.

Version 0.1.10 makes the context folder picker browse Mac input folders. Home,
Downloads, Documents, Desktop, WINGS Workspace and external drives appear when
accessible. A path field accepts an absolute Mac path or `~/...`. Additional
locations can be added or removed with **Settings → Share a folder with WINGS**,
which opens the native Mac folder chooser. Folder names containing spaces work.
After changing shares, finish active jobs and restart the WINGS service.

The Mac Home folder, `/Volumes` when present, and explicitly added input folders
are mounted read-only at their original paths. Docker Desktop must be allowed
to access them; macOS permissions can still deny individual folders. Browsing
returns directory names, not file contents. Selecting a path does not copy data.
The workspace remains writable for results and prepared context; the storage
picker continues to use workspace output paths. Hidden child folders remain
excluded from the browser. Share a specific folder in Settings if it is outside
the advertised roots. Removing a share removes container access after restart,
without deleting its files.

Upgrade: finish active jobs, use **Settings → Stop WINGS service**, replace the
app, then reopen it. This version needs a service restart to apply its new mounts
and picker code. The runtime image, saved credentials and reference caches are
reused. The Docker recipe and scientific analyses are unchanged.

Version 0.1.9 shortens the saved-email confirmation to: "Contact email saved.
Refresh the WINGS browser page. New jobs will use it; existing jobs keep their
settings." The workflow source and runtime remain identical to 0.1.8. Replace
the launcher and reopen it; the running 0.1.8 service can be reused.

Version 0.1.8 adds **Add later** to NCBI reference-retrieval setup and
**Settings → Add or update NCBI email**. Skipping is remembered per workspace.
WINGS setup and analyses that do not need this contact email can continue.
Phylodynamics submission explains how to add the email when it is missing.
After saving it in Settings, refresh the browser page; new attempts read the
saved file without restarting the service. Existing jobs keep their snapshots.

Both credential prompt guards now use the shell's built-in file checks instead
of a hard-coded external `test` path. Previously, a missing executable could
cause the app to ask again even when credentials or an Add later marker existed.
The eBird key and NCBI email are stored independently. Choosing Add later in
Settings does not erase an existing saved value. The launcher icon disappearing
after browser opening is intentional: the service continues in Docker, and you
can reopen WINGS for Settings.

This update changes the bundled runner. Finish active jobs, open WINGS Settings
and choose **Stop WINGS service**, quit WINGS, replace the app, and reopen it.
Saved credentials, reference files and workspaces are retained. The runtime
image is unchanged. The source update does not require rebuilding verified
reference databases.

Version 0.1.7 fixes the launcher handoff after the contact-email prompt. A
separate coordinator owns setup, completion tracking and browser opening.
The interactive AppleScript returns immediately, instead of waiting inside
the process that displayed the last dialog. Browser opening no longer waits
for the Cocoa status process; a stuck status helper is retired after success.
If the status process exits early, the setup log opens while setup continues.

The workflow source archive and runtime are byte-identical to 0.1.6, so an
already-running 0.1.6 service can be reused without stopping it. Quit or Force
Quit only the stuck WINGS launcher, replace WINGS.app, then reopen WINGS.
Keep Docker Desktop running. There is no database rebuild for this update.
The observed 0.1.6 log confirms successful BLAST creation, VADR installation,
and service readiness. Native Mac launcher acceptance is still required.

Version 0.1.6 fixes the confirmed BLAST input-path failure in workspaces whose
names contain spaces. The setup log showed that makeblastdb interpreted the
input path only through `.../WINGS`, despite shell quoting. Local database builds
now copy the FASTA into the same space-free temporary directory as the output.
This adds one temporary FASTA copy, cleaned up on success or failure. Archive
checksum verification and post-build database verification remain required.
The downloaded archive, workspace and runtime image are reused on retry.
The regression now rejects whitespace in both resolved input and output paths
and verifies the staged input bytes. Real BLAST and Mac acceptance remain open.

Version 0.1.5 incorporates the latest Phylodynamics changes:

- Focus locations and regional groups follow the actual study sample metadata.
  Kentucky has no special-case default. Study locations appear first.
- A full-width map sits above the dated tree. Six strongest directed routes are
  displayed initially; Show all reveals every connected route for the date.
  This display filter does not change posterior counts or other results.
- Opposite-direction routes curve apart. Route highlighting, smaller outlined
  arrowheads, Expand map, zoom, pan and reset help inspect crowded areas.
- Short trees fit their content; larger trees retain a scrolling viewport.
- Analysis validation retains every posterior draw and event, including datasets
  beyond the legacy movie player's event limit. Browser playback limits remain.

To update, finish any active jobs, use **Settings → Stop WINGS service**, quit
WINGS, replace WINGS.app in Applications, and reopen it. The existing workspace,
credentials and caches are reused. The runtime recipe is unchanged. The updated
viewer is included in newly generated reports; saved older reports and bundles
keep their embedded presentation until refreshed. The separately supplied
presentation-refresh patches can refresh those without rerunning inference.

Version 0.1.4 adds a visible native setup window to the downloaded preview:
current stage, elapsed time, log inactivity notice, **Open log**, and **Open
workspace**. It stays visible on failure; successful setup opens the browser.
The window can be minimized during setup. It uses built-in macOS Cocoa/JXA,
without host Python or Node. If the window cannot open, the launcher opens the
setup log and explicitly reports the display failure.

The reported BLAST failure occurred after sequence ingestion. The previous
basename-only workaround still allowed makeblastdb to resolve an absolute output
path containing spaces internally. This update builds into a unique space-free
`/tmp` directory, runs `blastdbcmd -info`, and copies verified files into the
persistent cache. A failure before verification does not replace installed
database files or publish a new manifest. Temporary build files are cleaned on
normal exit and errors. Both the temporary disk and destination cache need room
for the database during installation. Actual BLAST and native-window behavior
still require a Mac/container check; local regression checks use simulated BLAST.

The runtime image recipe is unchanged, so the previously built Docker image is
reused. Saved credentials and the downloaded reference archive are retained.
This update changes bundled workflow source. If an older service is running,
finish its jobs and use **Settings → Stop WINGS service** before opening this
version. A failed setup with no running service can simply be retried.

Version 0.1.3 preserves hyphens and letter case in access keys, and trims only
surrounding clipboard whitespace (including line breaks and nonbreaking spaces).
Validation uses character codes rather than text comparisons. An internal space
or non-ASCII character still produces a clear error with **Add later** available
directly from that dialog. The workflow source, runtime image, logo, caches and
stored key format are unchanged from 0.1.2; replacing the app does not require
restarting an already-running 0.1.2 service.

Version 0.1.2 adds optional eBird Status and Trends access-key setup with **Add
later**, plus **Settings → Add or update eBird access key**. The supplied WINGS
logo replaces the placeholder app icon. It also introduced a BLAST path workaround (completed in 0.1.4), and explicitly applies
the recorded BLAST database format version. The controller image from 0.1.1 is
reused, and an already-downloaded reference archive is copied into the shared
cache and checksum-verified before reuse.

The optional key is for seasonal abundance downloads, not the separate general
eBird API. Request it at https://ebird.org/st/request (also linked in Settings).
Skipping does not prevent WINGS startup; cached rasters remain usable. New
uncached abundance data require the key. The eBird observation-data import is
separate and still uses an EBD/sampling-event download.

Keys are entered in a masked dialog and saved with user-only file permissions
inside the workspace. They are not placed in shell arguments, run configuration,
diagnostic exports, or Docker container settings. This version reads the saved
key for each new preparation or analysis attempt. Adding, replacing or removing
it does not change the environment of existing jobs. After adding a key, prepare
context again if an earlier preparation reported missing access. The key is
validated by eBird when a download is attempted, not when it is saved.

Version 0.1.1 fixes Docker credential-helper lookup when opening WINGS from
Finder. The launcher adds Docker's executable/helper directories to its own
PATH, including the resolved target of a symlinked Docker CLI. Docker login
settings and saved credentials are preserved. It also removes redundant
Dockerfile platform warnings; builds still explicitly target Linux AMD64.

To update after a setup failure, quit WINGS, replace WINGS.app,
then reopen it. The saved workspace is reused automatically. No terminal or
Docker credential-configuration changes are needed.

This package adds a Mac launcher for the WINGS workflow. It removes the need to
install Python, Conda, NumPy, SciPy, Java, or Snakemake on the host Mac. Docker
Desktop remains a separate prerequisite. This is a development build, not a
signed or notarized production release.

## Use the preview

1. Extract the ZIP. Drag **WINGS.app** into Applications.
2. Install Docker Desktop for your Mac if it is not already installed. Open it
   and finish its first-run setup. Use the Apple Silicon Docker Desktop installer
   on an Apple Silicon Mac; the analysis runtime currently uses Linux AMD64
   emulation on that platform.
3. Open WINGS. Choose the parent folder for a new **WINGS Workspace**. Prefer a
   local disk with substantial free space; sequence reads, BLAST references,
   Docker images and environments can occupy many gigabytes. A 50 GB free-space
   planning allowance is reasonable for a small evaluation, not a guaranteed
   requirement or capacity estimate for real runs.
4. Save your optional eBird abundance key or choose **Add later**. Enter a contact
   email for NCBI reference retrieval or choose **Add later**. WINGS prepares the runtime,
   downloads the pinned BLAST reference archive and VADR models, pulls the IRMA
   and VADR images, and opens the existing submission interface in your browser.
5. Select Phylodynamics to reveal the **Fast / BEAST (MCMC)** choice. Fast is the
   default. The separate Phylogenetics checkbox is not required for Phylodynamics.
   The existing BEAST convergence/precision gates remain in force.

First setup can take a substantial time. Later launches reuse the runtime and
reference data. The first analysis can still download its module-specific Conda
environments, inside Docker. This preview is not an offline installer.

Startup image checks and downloads run through the native Mac Docker CLI, using
the same local Docker context and credential helpers as the launcher. They use
`docker image inspect --platform linux/amd64`, which requires Docker API 1.49 or
newer (see [Docker image inspect](https://docs.docker.com/reference/cli/docker/image/inspect/)).
An ARM64-only image does not satisfy the desktop runtime's AMD64 requirement.
IRMA remains version 1.3.5: setup uses CDC's Docker Hub AMD64 manifest
`sha256:96357063a678fd5887598b093a53373ae286a2eb0155520feae8b72904bcdda8`
and retains the workflow's `ghcr.io/cdcgov/irma:v1.3.5` local alias. The matching
v1.3.5 index is
`sha256:cda47ea17971ee02195160fccbc76b4b97a8a0115c3f0c322b00d195b29e4785`.
An existing AMD64 image with one of those official repository digests can be
reused without a registry request. VADR remains `staphb/vadr:1.7`. Setup stops
before starting the service if a required image cannot be prepared.

The controller bundles Docker CLI 28.3.3 for both AMD64 and ARM64, pinned to the
official image index
`sha256:0135662b510037ea581d99c2e5929c5e01185139c0b86986a418bd4da0b98a44`.
The native host CLI queries the Docker engine architecture; the launcher passes
that selection into the controller for analysis jobs. The scientific runtime,
Conda environments and default analysis image platform remain Linux AMD64.
Setup tests the selected CLI through the controller's Python before serving the
browser interface. A failing CLI therefore stops setup instead of surfacing as
an unexplained Resume rejection. The separate Jupyter kernel timeout is not
resolved by this change. Validate startup and report rendering on a Mac before
publishing a build.

An unsigned app may be blocked by macOS. A normal public release needs Developer
ID signing and Apple notarization. Do not disable Gatekeeper globally. This
preview's code is supplied for inspection; on a development Mac, use Apple's
documented Privacy & Security approval flow only if you trust the build.

The ZIP contains a shell-backed `.app` preview that invokes built-in AppleScript.
The included Mac build script compiles a native AppleScript applet and creates a
DMG. Both versions open the same browser setup-progress page. Setup details
remain available in the workspace's `logs/setup-*.log`. Reopening after completion
opens WINGS.
The coordinator writes the technical-log link directly into the status HTML so
it works even when browser JavaScript does not initialize. It points to the
actual log beside the status directory, not back to the progress page.

## Data and updates

- Your chosen workspace contains `runs`, `cache`, `releases`, and `logs`.
- The browser's storage picker is restricted to that persistent workspace in
  desktop mode. File uploads use the ordinary Mac browser file picker.
- Use the context picker for Mac Home or external-drive inputs. For other
  locations, use Settings → Share a folder with WINGS, then restart the service.
- Closing WINGS or the browser leaves running analyses running. Keep Docker
  Desktop and the Mac awake while analyses run.
- Finish or stop jobs in the browser before using **Settings → Stop WINGS
  service**. This stops the controller; already-started sibling analysis
  containers may need to finish or be stopped in Docker Desktop.
- Replacing WINGS.app does not erase the workspace. An existing running version
  is never silently replaced. Finish its jobs and stop its service first.
- No automatic uninstall, pruning, cache deletion, or source-repository mutation
  is performed. This app uses its bundled source, not your existing `~/wings`.

The app saves an NCBI email and a local session token with user-only permissions.
The Docker controller can access the selected workspace and the Docker daemon;
it is not a security sandbox for untrusted workflows. It publishes only a random
localhost port, checks session cookies and request origins, and does not require
the old runner on port 8765 to be stopped.

## What is inside

One launcher manages the workflow. This version uses **one controller container
plus the existing IRMA/VADR containers**, and runs the remaining existing Conda
rule environments inside the controller. It is not a rewrite of every analysis
into a separate OCI image, and it is not a single self-contained executable
containing every reference database.

The source snapshot includes the restored Phylodynamics backend, the integrated
Explorer, Fast/BEAST submission support, and regenerated canonical UI assets.
It is assembled from the supplied WINGS source and previously delivered patches;
it is not claimed to be an official upstream release. Source integrity is checked
before launch. No user reads, real analysis outputs, local credentials, or local
config.yaml are bundled. The root config.yaml is generated from the example.

Default runtime architecture is Linux AMD64 on both Intel and Apple Silicon
Macs. This avoids mixing Intel Conda with native ARM Python. Emulation can be
slower; native ARM tool support remains future work. macOS 13+ is the app bundle's
minimum, but Docker Desktop's own supported macOS versions also apply.

The optional local Ollama briefing integration now uses the configured Mac
endpoint from inside the container. Use Settings → Check Ollama connection
before enabling a briefing. Real inference through this Mac/container path
has not been executed here; check availability on your Mac first.

## Validation and release work still required

Locally checked: launcher syntax; setup/reopen/stop behavior using a fake Docker
CLI; path quoting and workspace mounts; source archive checksums and missing-file
handling; loopback gateway authentication, origin checks and uploads; storage
boundaries; existing scientific unit tests and UI tests. See `VALIDATION.md`.

Not executed here: Docker image build, real first-run reference downloads, a
real workflow through the container, AppleScript compilation, macOS app launch,
codesigning or notarization. **Treat this as a developer preview until those
checks pass.** No biological results were generated to validate this installer.

The runtime recipe uses versioned base-image tags and constrained package
versions; it is not yet an immutable lockfile or a published digest-pinned image.
The image saves `conda-explicit.txt` for auditing. Before a public release, build
and test the image in CI, pin its digest and the resolved package specification,
then publish it so ordinary users download a tested image instead of building it.

## Developer build

`desktop/package.py` takes a complete clean WINGS source tree and creates the
portable preview app bundle. The ZIP already includes a source snapshot at
`WINGS.app/Contents/Resources/source.tar.gz`; extract it into a fresh folder for
review. Do not extract it over an existing working repository without reviewing
the changes. Add the `desktop` directory to that source tree to develop further.

```bash
python desktop/package.py --source . --output /tmp/wings-preview
bash desktop/build-macos.sh /tmp/wings-preview/WINGS.app /tmp/wings-native
```

The first command needs developer Python; **end users launching the app do not**.
The second needs macOS's built-in `osacompile`, `codesign` and `hdiutil` tools.
It produces a compiled app and unsigned DMG unless signing is configured.

For a signed, notarized candidate, set `WINGS_SIGN_IDENTITY` to a Developer ID
Application identity installed in your keychain and `WINGS_NOTARY_PROFILE` to a
preconfigured `notarytool` keychain profile before running the build script. No
credentials should be added to the repository or ZIP. The script signs the app,
submits the DMG for notarization, and staples the returned ticket.

Copy `desktop/desktop-ci.yml` to `.github/workflows/desktop.yml` after adding the
complete backend to the repository. It builds the Linux controller and tests the
actual Fast/BEAST workflow dependencies, then compiles the app and DMG on macOS.
These jobs must pass before release; the workflow file alone is not evidence
that they have run.

Manual acceptance on a clean Intel and Apple Silicon Mac:

1. Install with no host Python/Conda and with paths containing spaces.
2. Complete Docker/reference setup; verify failed downloads retry cleanly.
3. Run synthetic/small validated data through assembly and Fast Phylodynamics.
4. Exercise BEAST with the existing convergence gates; no result should be
   published when diagnostics fail.
5. Verify persistence after closing/reopening, interrupted-run recovery, and
   an app upgrade. Check data and resource paths are host-visible.
6. Check Mac resource limits, network-restricted environments, native script
   progress/cancellation, Gatekeeper, and signed/notarized distribution.

## Troubleshooting

**Docker unavailable:** start Docker Desktop; use its local Linux engine. Remote
Docker contexts are rejected because they cannot mount this Mac's workspace.

**Setup failed:** open the log offered by the app, correct the cause, and reopen.
No run data are removed. Setup uses a lock to avoid concurrent installations.

**Need diagnostic details:** Settings → Export installation diagnostics
creates a file with OS/architecture, Docker versions and image/source identity.
It excludes sequence data, email, tokens and run configurations. Setup logs are
separate and may contain local paths; inspect those before sharing.

**Runtime memory failure:** adjust Docker Desktop's memory/disk allocation to
fit the selected tools and dataset, and reduce concurrent workflow jobs.

**Missing Python package on the Mac:** the app never invokes host Python. A
Python error from a terminal-based patch installer is separate from this app.
