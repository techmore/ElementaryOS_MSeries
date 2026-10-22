const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {auditMatches} = require('../docs/capabilities.js');
const data = JSON.parse(fs.readFileSync(path.join(__dirname, '../docs/capabilities.json'), 'utf8'));
const makeIndex = entry => ({...entry, search: [entry.title, entry.provided, entry.verification, entry.limitation, entry.next_step].join(' ')});
const entries = data.entries.map(makeIndex);
const ids = filters => entries.filter(entry => auditMatches(entry, filters)).map(entry => entry.id);

assert.equal(ids({}).length, entries.length);
assert(ids({query: 'SCREENSHOT originals'}).includes('screenshot-retention'));
assert(ids({query: '  xart  guard  '}).includes('touch-id'));
assert.equal(ids({query: 'no-such-capability-xyz'}).length, 0);
assert(ids({area: 'Hardware', stage: 'Blocked'}).includes('touch-id'));
assert(!ids({area: 'Apps', stage: 'Blocked'}).includes('touch-id'));
assert(!ids({stage: 'Recorded outcome'}).includes('kernel-wip3'));
assert(!ids({kind: 'Fix', origin: 'Custom implementation'}).includes('iphone-transport'));
assert(ids({priority: 'P1', query: 'ChatGPT'}).includes('english-f5'));
// Search text is treated literally; it cannot become a regex or markup instruction.
assert(!auditMatches({search: 'plain text'}, {query: '.*'}));
assert(!auditMatches({search: 'plain text'}, {query: '<script>'}));
assert.equal(ids({}).length, entries.length, 'clearing selections restores all entries');
console.log('Capability search: literal words, intersecting filters, acceptance stages and clear state passed');
