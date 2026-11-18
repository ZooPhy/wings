/* Local setup display. Runs in the browser; no network server or host runtime. */
(function () {
    'use strict';
    const steps = ['Check Docker Desktop', 'Install WINGS workflow', 'Prepare analysis runtime',
        'Prepare influenza references', 'Prepare analysis tools', 'Start WINGS'];
    const details = {
        docker: 'Checking that Docker Desktop is available.',
        workflow: 'Installing or reusing the bundled workflow.',
        runtimecheck: 'Checking the saved analysis runtime.',
        runtime: 'Downloading and building the analysis runtime. First setup can take a while.',
        verify: 'Checking the installed workflow files.',
        references: 'Checking reference data and preparing any missing files.',
        download: 'Downloading the influenza reference sequences.',
        extract: 'Unpacking the influenza reference sequences.',
        build: 'Building the BLAST reference database. This step can take several minutes.',
        verifydb: 'Verifying the new BLAST reference database.',
        installdb: 'Saving the verified reference database.',
        refsready: 'The reference database is ready. Continuing with analysis tools.',
        modelsdownload: 'Downloading and checking VADR influenza models.',
        modelscached: 'Reusing installed influenza models and checking analysis tools.',
        modelsready: 'Influenza models are ready. Checking assembly and annotation tools.',
        tools: 'Downloading assembly or annotation tools. First setup can take a while.',
        start: 'Starting the local WINGS service and checking that it responds.',
        opening: 'WINGS is running. Opening the analysis interface.'
    };
    const errors = {
        older: 'An earlier WINGS service is running. Finish its jobs, then use WINGS Settings → Stop WINGS service and reopen this version.',
        folders: 'Shared folders changed. Finish active jobs, then use WINGS Settings → Stop WINGS service and reopen WINGS.',
        missingfolder: 'A shared folder is unavailable. Reconnect the drive or remove the folder in WINGS Settings, then reopen WINGS.',
        checksum: 'A downloaded or installed file failed verification. Open the setup log for details, then reopen WINGS to retry.',
        disk: 'The disk is full. Free space on the workspace disk or in Docker Desktop, then reopen WINGS to retry.',
        generic: 'Setup stopped. Open the setup log for details, then reopen WINGS to retry. Your saved settings and runs are preserved.'
    };
    function duration(seconds) {
        seconds = Math.max(0, Math.floor(seconds));
        return Math.floor(seconds / 60) + 'm ' + (seconds % 60) + 's';
    }
    function view(state, now) {
        if (!state) return {title: 'Connecting to setup…', detail: 'Waiting for the setup status.',
            completed: 0, phase: 0, elapsed: '0m 0s', activity: '', stale: true, done: false, failure: false};
        const done = state.status !== 'running';
        const failure = done && state.status !== 'ready';
        const stale = !done && now - state.heartbeat > 15;
        const phase = Math.min(6, Math.max(1, Number(state.phase) || 1));
        const completed = state.status === 'ready' ? 6 : phase - 1;
        let title = 'Step ' + phase + ' of 6 · ' + steps[phase - 1];
        let detail = details[state.code] || 'Preparing WINGS.';
        let activity = 'Setup process is running · Updated ' + duration(now - state.heartbeat) + ' ago';
        const quiet = Math.max(0, now - state.lastOutput);
        if (quiet >= 60) activity += ' · No new output for ' + duration(quiet);
        if (stale) {
            title = 'Waiting for setup status';
            detail = 'No status update has arrived for ' + duration(now - state.heartbeat) +
                '. Setup may have been interrupted. Reopen WINGS to check; your data are preserved.';
            activity = 'Last known step: ' + steps[phase - 1];
        } else if (state.status === 'ready') {
            title = 'WINGS is ready';
            detail = state.browserOpened ? 'WINGS has opened in another browser tab or window. You can close this setup tab.' :
                'Setup finished, but the browser could not open WINGS. Reopen the WINGS app and choose Open WINGS.';
            activity = 'Setup complete';
        } else if (failure) {
            title = state.status === 'interrupted' ? 'Setup was interrupted' : 'Setup could not finish';
            detail = errors[state.error] || errors.generic;
            activity = 'Stopped at step ' + phase + ' of 6';
        }
        return {title, detail, activity, phase, completed, done, failure, stale,
            elapsed: duration((done ? state.heartbeat : now) - state.started)};
    }
    if (typeof module !== 'undefined') module.exports = {view, steps};
    if (typeof document === 'undefined') return;
    let state = null, loading = false, loaded = null;
    const $ = id => document.getElementById(id);
    function render() {
        const v = view(state, Date.now() / 1000);
        $('title').textContent = v.title;
        $('detail').textContent = v.detail;
        $('activity').textContent = v.activity;
        $('elapsed').textContent = 'Elapsed: ' + v.elapsed;
        $('count').textContent = v.completed + ' of 6 steps completed';
        $('bar').value = v.completed;
        $('status').className = v.failure ? 'failed' : v.stale ? 'stale' : v.done ? 'ready' : 'running';
        $('note').textContent = v.done ? 'Closing this page does not stop WINGS.' :
            'Steps take different amounts of time. Downloads and database building may be quiet for several minutes.';
        for (let i = 0; i < steps.length; i++) {
            const row = $('step-' + i), marker = row.querySelector('.marker');
            const complete = i < v.completed;
            const active = !v.done && i === v.phase - 1;
            row.className = complete ? 'complete' : (active ? (v.stale ? 'paused' : 'active') : '');
            marker.textContent = complete ? '✓' : String(i + 1);
            row.querySelector('.state').textContent = complete ? 'Complete' : active ? (v.stale ? 'Waiting' : 'In progress') :
                v.failure && i === v.phase - 1 ? 'Stopped' : 'Pending';
            if (active) row.setAttribute('aria-current', 'step'); else row.removeAttribute('aria-current');
        }
    }
    window.WINGSSetup = {update(value) { state = value; render(); }};
    function refresh() {
        if (loading || (state && state.status !== 'running')) return;
        loading = true;
        const script = document.createElement('script');
        script.src = './state.js?t=' + Date.now();
        // Local script loads work on file://; fetch(file://) does not.
        const finish = () => { loading = false; script.remove(); clearTimeout(timeout); };
        const timeout = setTimeout(finish, 5000);
        script.onload = finish; script.onerror = finish;
        document.head.appendChild(script);
        loaded = script;
    }
    $('refresh').addEventListener('click', () => { if (loaded) loaded.remove(); loading = false; refresh(); });
    // Build this relative link from the coordinator-generated filename only.
    // No log content or authenticated WINGS address is embedded in this page.
    const folder = location.pathname.split('/').slice(-2, -1)[0] || '';
    if (/^setup-[A-Za-z0-9-]+\.log\.status$/.test(folder)) {
        $('log').href = '../' + folder.slice(0, -7);
    } else $('log').hidden = true;
    render(); refresh();
    setInterval(refresh, 2000);
    setInterval(render, 1000);
}());
