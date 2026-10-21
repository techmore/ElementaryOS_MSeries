import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import vm from 'node:vm';
const source = await readFile(new URL('../docs/build-status.js', import.meta.url), 'utf8');
const elements = new Map();
const element = () => ({textContent: '', disabled: false, children: [], addEventListener() {}, replaceChildren() {this.children=[];}, append(x) {this.children.push(x);}});
const run = {id: 1, run_number: 2, head_sha: '12345678', created_at: new Date().toISOString(), html_url: 'https://github.com/techmore/ElementaryOS_MSeries/actions/runs/1', status: 'in_progress'};
let fail = false;
const requested = [];
const context = vm.createContext({
  document: {hidden: false, getElementById(id) {if (!elements.has(id)) elements.set(id, element()); return elements.get(id);}, createElement: element},
  AbortSignal, Date, setInterval() {},
  async fetch(url) {requested.push(url); if (fail) throw new Error('Offline'); return {ok: true, json: async () => url.includes('/jobs?') ? {jobs:[{steps:[{name:'Build image', status:'in_progress'}]}]} : {workflow_runs:[run]}};}
});
vm.runInContext(source.replace(/refresh\(\);\s*$/, ''), context);
const decide = (build, validation) => context.decision(build, validation)[0];
assert.match(decide(run), /No poke needed/);
assert.match(decide({...run, status:'completed', conclusion:'success'}), /image build finished/);
assert.match(decide({...run, status:'completed', conclusion:'failure'}), /build stopped/);
assert.match(decide({...run, status:'waiting'}), /needs attention/);
assert.match(decide({...run, status:'queued', created_at:new Date(Date.now()-16*60000).toISOString()}), /runner wait/);
assert.match(decide(run, {status:'completed', conclusion:'failure'}), /checks need attention/);
assert.match(decide(null), /no build started/);
await context.refresh();
assert.deepEqual(requested.filter(url => url.includes('/workflows/')), [
  'https://api.github.com/repos/techmore/ElementaryOS_MSeries/actions/workflows/daily-9.0.yml/runs?branch=dev&per_page=1',
  'https://api.github.com/repos/techmore/ElementaryOS_MSeries/actions/workflows/validate-mseries.yml/runs?branch=dev&per_page=1',
  'https://api.github.com/repos/techmore/ElementaryOS_MSeries/actions/workflows/382174750/runs?branch=dev&per_page=1'
], 'Build, validation and Pages status must follow the published development branch');
assert.match(elements.get('signal').textContent, /No poke needed/);
assert.equal(elements.get('steps').children[0].textContent, 'Build image — in progress');
assert.equal(elements.get('refresh').disabled, false);
fail = true;
await context.refresh();
assert.equal(elements.get('signal').textContent, 'Live status unavailable');
assert.match(elements.get('advice').textContent, /stale/);
assert.equal(elements.get('refresh').disabled, false);
console.log('Dashboard status, stage rendering, and offline handling passed');
