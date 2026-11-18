# Desktop preview validation — 2026-11-17

0.1.14: logo packaged and copied with the setup page; 4 setup-session and 3
packaging checks passed. Chromium preview over loopback HTTP loaded the logo
under the page CSP and fit a 375px viewport without horizontal overflow. File
URLs are blocked by this test environment; native Mac file-page acceptance is
still required. Source and runtime archives are identical to 0.1.13.


0.1.13: 24 targeted Porechop tests cover the split-path regression, actual child
argument handling with special characters, installed/OpenMP/custom rule branches,
parallel scratch isolation, version/counter checks, and failure/output handling.
Synthetic fixtures are used; real Porechop adapter inference, a Docker workflow,
and Mac launch were not executed here. The installed environment and runtime
image recipe are unchanged. The new source wrapper requires a service restart.

Mac acceptance: update the app, reopen the same workspace, and Resume the failed
run. Confirm the log starts with WINGS path-safe Porechop and reaches completion.
Inspect the retained provenance JSON and preserve the failed attempt log.


0.1.12: saved local endpoint/model defaults, custom ports, Docker-host mapping,
model override and immutable job snapshots are tested. Invalid URLs, settings
symlinks, malformed files and unrelated non-briefing jobs are covered. The check
uses only GET /api/tags, caps response size, does not follow redirects and uses
fixed errors for malformed/unreachable services. Existing briefing tests pass.

Shell settings tests verify quoting, validation, atomic replacement, mode 0600
and preservation on invalid input. Fake-Docker checks verify a matching running
WINGS service is required and that the read-only check runs via docker exec in
that controller. Browser fixture tests verify saved defaults, endpoint-change
invalidation, preservation of user model edits and current submission payloads.
The older fixture lacked the current context and Docker prerequisites; it now
supplies those explicitly and retains its previous storage/payload assertions.

Runtime recipe/digest and scientific inference code are unchanged. The workflow
source archive changes because the runner now reads Ollama settings and the
submission UI displays its defaults. One service restart is required. Native
AppleScript dialogs, a real Mac-host Ollama connection, real Docker execution
and actual model generation have not been run here. This check does not verify
GPU use, available memory or scientific accuracy of generated text.

Mac acceptance: save an address/model; check with Ollama stopped, started, and
with a deliberately missing model. Refresh the submission page and confirm the
saved model appears, then test a briefing on suitable example inputs. Change the
settings and confirm an existing job retains its original model/endpoint.

0.1.11: shell coordinator integration checks cover opening the progress page
before setup, live BLAST/tool steps, setup failure, cleanup, browser-opening
failure and completion. Only enum status and numeric timing values enter the
page; synthetic secret/error text is excluded. State-model tests cover quiet
processes, stale heartbeats/recovery, frozen completion time and incomplete
steps on failure. Existing launcher orchestration, credential guards and package
checks pass. No Docker or biological workflow was run.

Chromium rendering tests over a temporary localhost test server passed for live
updates, quiet output, lost heartbeat, failure, completion, the technical-log
link and a 390px viewport without horizontal overflow. The production page uses
local file script loading; this environment blocks file:// navigation, so that
specific transport, Safari and real Mac browser opening are not claimed tested.
A native AppleScript menu test simulates repeated settings actions and Cancel,
then Open/Quit. It is included for Mac CI and skipped on this Linux host; native
compilation and interactive settings acceptance still need a Mac.

The packaged source archive and runtime digest must remain exactly equal to
0.1.10. This update changes only launcher resources and packaging documentation.

Mac acceptance: launch setup from Finder; confirm the progress tab appears before
reference preparation and updates without opening a log. Minimize/close/reopen
it from Settings. Exercise a long quiet step and a failed download, then retry.
Save each key/email, choose Add later, cancel folder selection and stop the
service; each settings action should return to the launcher menu. Test Safari
and Chrome (including local-file restrictions on managed work computers).

0.1.10: desktop context-root tests verify Mac shortcuts, pasted home/shared paths,
CSV selection, missing shares and traversal/symlink boundaries. The browser
interaction test covers the new path field alongside existing navigation,
pagination, cancellation and selection. Fake-Docker launcher tests check
read-only Home/custom mounts, writable workspace, mount changes requiring a
restart, missing drives and filesystem-root symlink rejection. Real Docker
mounts, macOS folder permissions and the native Settings chooser still need
Mac acceptance. This update does not claim a real host-folder integration run.

0.1.9: dialog wording only. Verified the exact confirmation in the packaged
AppleScript and byte-identical workflow source/runtime versus 0.1.8. No new
biological analysis or native Mac execution was performed.

0.1.8: tests execute both actual prompt guards with no external tools on PATH;
saved values and Add later markers suppress repeat prompts. Six backend tests
cover missing email, non-Phylodynamics submission, live additions/updates,
independent eBird loading, unchanged existing environment snapshots, malformed
values and symlinks. Existing credential and submission tests remain passing.
A native AppleScript email-normalization test is supplied for macOS; it is
skipped here. The source changes require a one-time service restart. The runtime
recipe and scientific inference code are unchanged.

0.1.7: a native Mac log/screenshot now confirms successful BLAST creation with
1,593,359 sequences, VADR model verification/installation and service readiness.
The reference-retrieval dialog remained visible. Source inspection found the
interactive AppleScript synchronously waiting for the Cocoa helper before it
could open the browser. The new detached coordinator removes that dependency.
Offline subprocess checks cover a stalled status helper, a failed helper,
a failed backend and normal completion; a successful backend opens the browser
without waiting for the helper. Logs exclude the session URL/token. Package
checks verify the coordinator and identical workflow/runtime archives. macOS
native execution of the revised launcher has not been performed here.

0.1.6: the supplied Mac setup log confirms successful runtime-image construction,
source verification and reference download/checksum validation, followed by
`BLAST options error: File .../WINGS does not exist`. The earlier fix covered
the output path, but local -in still contained `WINGS Workspace`. The stricter
BLAST stub reproduces this failure with 0.1.5 and passes with the staged input
copy. It verifies input-byte identity, cleanup, post-build validation failure,
and publication behavior. The tiny real-BLAST test is retained for environments
with BLAST installed. Native Mac UI and a real full-database retry are not claimed.

0.1.5: includes the verified study-location grouping and saved-presentation
refresh, full-width map with six/all routes, separated reciprocal curves,
route highlighting, expanded dialog, zoom/pan/reset, and content-sized trees.
Chromium checks used synthetic data: 18 routes reduced to six without changing
entry counts; keyboard/Escape, focus, drag pan, narrow layouts and draw mode
passed. A three-tip tree used 146 px instead of the fixed 490 px; a 30-tip tree
retained scrolling. The existing full-event analysis validator and its 501,000
-event regression are bundled. No posterior data or biological analyses were
regenerated. Native macOS launch and Docker execution still require validation.

0.1.4: setup-state tests cover active work, quiet logs, success, failure and a
stopped process without a completion marker. Packaging checks that the native
Cocoa/JXA helper is included. A native smoke test is provided for macOS CI; it
cannot run on Linux. The BLAST stub now rejects a resolved output path with
spaces, reproducing the remaining path hazard in the old basename workaround.
The staged-build test checks publishing and cleanup; a failing verification
must leave no database or success manifest and retain the downloaded archive.
The workflow search regression also passes. The real BLAST test is skipped:
BLAST is unavailable locally and attempts to fetch a binary returned HTTP 403.

The user's latest log shows all 1,593,359 sequences were ingested, followed by a
memory-map error before successful completion. A path issue is the working
diagnosis, not a root cause confirmed against that full database here. This
release does not claim real BLAST success, a Mac GUI run, or full setup success.
The runtime hash remains unchanged; the source archive changes for the build fix.

0.1.3: verified that a hyphenated, mixed-case key is accepted unchanged by the
backend. Added a native AppleScript test using the exact dialog normalization
handler for ordinary hyphens, surrounding spaces/newlines/nonbreaking spaces,
case preservation and invalid internal whitespace. This test runs in the Mac
CI job; it is skipped in this Linux environment. The screenshot does not prove
which character caused the original rejection. No real access key was requested
or used for testing. This update does not change the workflow source or runtime.

0.1.2: optional eBird key lifecycle and context environment tests pass. Added
BLAST setup/search tests for space-containing paths. The executable BLAST test
is included in container CI and is skipped locally because BLAST is unavailable.
The supplied JPEG was converted to a multi-resolution ICNS while preserving the
full artwork and aspect ratio; its 256 px rendering was visually checked.

The user's 0.1.1 log confirms successful Docker image construction, source
verification and reference-archive download/checksum validation on their Mac.
That run then failed at BLAST database creation. The 0.1.2 fix still requires
a real BLAST run on that installation; the controller image is unchanged.

0.1.1 regression: reproduced the missing `docker-credential-desktop` error with
a Finder-style minimal PATH, both for a direct CLI path and a symlinked CLI in
a custom application folder. Both cases fail before the PATH fix and pass after
it. Tests also confirm that Docker's credential configuration remains unchanged.

This is a source/package validation record, not approval for a production release.

| Check | Result |
| --- | --- |
| Desktop orchestration, packaging, storage, gateway, key input and setup state | 24 tests passed; 2 native macOS tests skipped locally |
| Existing runner storage regression tests | 21 tests passed |
| Optional desktop credential lifecycle and environment snapshots | 6 tests passed |
| Context setup and live runner regressions | 50 tests passed |
| BLAST setup/search with paths containing spaces | 3 tests passed; real BLAST test skipped locally |
| Fast/BEAST submission adapter | 9 tests passed |
| Recovered scientific backend suite | 96 tests run: 88 passed, 8 skipped for unavailable optional/external dependencies |
| Navigation, navigation loaders, Fast/BEAST selector, movie and shared-results JavaScript tests | All 5 test files passed |
| Explorer generated assets versus canonical source | Passed |
| Bash syntax, Python compilation and YAML parsing | Passed |
| Bundled source archive hash, manifest closure and executable ZIP permissions | Checked during packaging |

The shell orchestration tests use a fake Docker executable. The HTTP tests run
real loopback servers with synthetic payloads, including a multi-megabyte upload.
They check authentication, host/origin restrictions, session handling and byte
preservation. Tests do not start real analyses or download reference sequences.

The scientific inference engines were retained from the restored source.
Desktop changes add a conditional storage boundary and optional per-job eBird
credential loading; native credential behavior is unchanged when
`WINGS_DESKTOP_WORKSPACE` is unset. The folder-picker harness loads the guard
dependency. BLAST setup and its workflow command now avoid space-containing
database-name arguments and honor the requested database version.

Not run in this Linux build environment:

- Docker build and actual container startup; Docker is unavailable here.
- Full workflow and external-tool validation, including Java/BEAST and IRMA/VADR.
- Live reference downloads or a real dataset.
- Snakemake dependency dry-runs; Snakemake is unavailable here. The prepared
  container CI includes the existing synthetic Fast/BEAST DAG check.
- macOS AppleScript compilation, LaunchServices, native progress and Gatekeeper.
- Developer ID signing, notarization and DMG generation.
- Manual clean-install and upgrade tests on Intel/Apple Silicon Macs.

`desktop-ci.yml` and `build-macos.sh` prepare those next checks; they have not
been run by GitHub or on a Mac as part of this delivery. The ZIP is unsigned.
The public release should remain blocked until container tests, clean-Mac
acceptance and signed distribution checks pass.
