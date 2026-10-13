'use strict';
const api = 'https://api.github.com/repos/techmore/ElementaryOS_MSeries';
const byId = id => document.getElementById(id);
const pretty = value => (value || 'unknown').replaceAll('_', ' ');
let busy = false;
async function read(path) {
  const response = await fetch(api + path, {headers: {Accept: 'application/vnd.github+json'}, signal: AbortSignal.timeout(20000)});
  if (!response.ok) throw new Error(response.status === 403 || response.status === 429 ? 'GitHub request limit reached' : `GitHub returned ${response.status}`);
  return response.json();
}
function renderRun(kind, run) {
  byId(kind + '-state').textContent = run ? pretty(run.conclusion || run.status) : 'No runs yet';
  byId(kind + '-detail').textContent = run ? `Run #${run.run_number} · ${(run.head_sha || '').slice(0, 7)} · ${new Date(run.created_at).toLocaleString()}` : 'Start a manual workflow on GitHub.';
  if (run) byId(kind + '-link').href = run.html_url;
}
function decision(build, validation, now = Date.now()) {
  if (validation?.status === 'completed' && validation.conclusion !== 'success') return ['Poke Codex · checks need attention', 'Open the validation result and ask Codex to investigate.'];
  if (!build) return ['Poke Codex · no build started', 'Ask Codex to launch the experimental arm64 workflow.'];
  if (build.status === 'completed') return build.conclusion === 'success' ? ['Poke Codex · image build finished', 'Next: inspect the installer and checksum, then plan hardware verification.'] : ['Poke Codex · build stopped', `Result: ${pretty(build.conclusion)}. Ask Codex to inspect the build logs.`];
  if (['action_required', 'waiting'].includes(build.status)) return ['Poke Codex · build needs attention', 'GitHub is waiting for approval or another required action.'];
  if (build.status === 'queued' && now - Date.parse(build.created_at) > 15 * 60000) return ['Poke Codex · runner wait', 'The build has waited over 15 minutes. Ask Codex to check runner availability.'];
  return ['No poke needed · build active', 'The arm64 image is building or waiting briefly for a runner. Leave this page open.'];
}
async function refresh() {
  if (busy) return;
  busy = true;
  byId('refresh').disabled = true;
  try {
    const results = await Promise.all([
      read('/actions/workflows/daily-9.0.yml/runs?branch=main&per_page=1'),
      read('/actions/workflows/validate-mseries.yml/runs?branch=main&per_page=1'),
      read('/actions/workflows/382174750/runs?branch=main&per_page=1')
    ]);
    const [build, validation, pages] = results.map(result => result.workflow_runs[0]);
    renderRun('build', build); renderRun('validation', validation); renderRun('pages', pages);
    const [signal, advice] = decision(build, validation);
    byId('signal').textContent = signal; byId('advice').textContent = advice;
    byId('updated').textContent = `Checked ${new Date().toLocaleTimeString()} · next refresh in 5 minutes`;
    byId('connection').textContent = 'Connected to public GitHub status. This page cannot wake an AI automatically.';
    byId('steps').replaceChildren();
    if (build) {
      try {
        const jobs = await read(`/actions/runs/${build.id}/jobs?per_page=100`);
        for (const job of jobs.jobs) for (const step of job.steps || []) {
          const li = document.createElement('li');
          li.textContent = `${step.name} — ${pretty(step.conclusion || step.status)}`;
          byId('steps').append(li);
        }
      } catch (error) {
        const li = document.createElement('li'); li.textContent = `${error.message}; open GitHub for stages.`; byId('steps').append(li);
      }
    }
  } catch (error) {
    byId('signal').textContent = 'Live status unavailable';
    byId('advice').textContent = 'Use the GitHub links below. Any previous results shown here may be stale.';
    byId('connection').textContent = `${error.message}. Automatic refresh will retry.`;
  } finally { busy = false; byId('refresh').disabled = false; }
}
byId('refresh').addEventListener('click', refresh);
setInterval(() => { if (!document.hidden) refresh(); }, 5 * 60000);
refresh();
