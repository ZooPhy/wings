const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../scripts/report/surveillance-explorer.js'), 'utf8');
const moduleSource = source.split('/* WINGS_EVIDENCE_SYNTHESIS_BEGIN */')[1].split('/* WINGS_EVIDENCE_SYNTHESIS_END */')[0];
const context = vm.createContext({});
vm.runInContext(moduleSource, context);
const {summarize, mount} = context.WINGS_EVIDENCE_SYNTHESIS;
const row = overrides => ({comparison:'ecology_vs_host', segment:'HA', status:'READY', n_samples:10, delta_r2:.2, fdr_q:.01, ...overrides});
const payload = rows => ({samples:[{sample_id:'example', segments_pass:8}], genomic_ecological_concordance:{models:rows, readiness:{minimum_unique_samples:8}}});
const ecology = result => result.findings.find(f => f.id === 'ecology_vs_host');

test('missing input and malformed collections remain unavailable, never negative', () => {
  for (const input of [undefined, null, {}, {samples:{}, genomic_ecological_concordance:{models:[null]}}]) {
    const result = summarize(input);
    assert.equal(ecology(result).status, 'unavailable');
    assert.match(result.headline, /does not yet contain enough/);
  }
});
test('requires valid sample counts, q values, fit and unique segments', () => {
  for (const overrides of [{n_samples:3}, {n_samples:'10'}, {fdr_q:null}, {fdr_q:NaN}, {fdr_q:-1}, {fdr_q:2}, {delta_r2:null}, {delta_r2:-.1}, {status:'FAILED'}, {display_status:'DESCRIPTIVE'}, {segment:'X'}]) {
    assert.equal(ecology(summarize(payload([row(overrides)]))).status, 'unavailable');
  }
  assert.equal(ecology(summarize(payload([row({}),row({})]))).status, 'unavailable');
});
test('zero q is valid; threshold is strict; null results are not absence claims', () => {
  const result=summarize(payload([row({fdr_q:0})]));
  assert.equal(ecology(result).status, 'association');
  assert.match(result.headline,/clearest signal/);
  assert.match(result.knowledge.action,/follow-up sampling/);
  for (const overrides of [{fdr_q:.05}, {fdr_q:.8}, {delta_r2:0}]) {
    const finding = ecology(summarize(payload([row(overrides)])));
    assert.equal(finding.status, 'inconclusive');
    assert.match(finding.text, /does not establish absence/);
  }
});
test('mixed segments preserve evidence and exclusions without claiming consensus', () => {
  const finding = ecology(summarize(payload([row({}),row({segment:'NA',fdr_q:.8}),row({segment:'PB2',status:'NOT_ESTIMABLE'})])));
  assert.match(finding.text, /1 of 2/);
  assert.match(finding.text, /1 comparisons withheld/);
  assert.equal(finding.evidence.excluded[0].index, 2);
});
test('migration needs documented distinct settings and honors stricter minima', () => {
  const input = payload([row({comparison:'migration_vs_ecology'})]);
  const finding = () => summarize(input).findings.find(f => f.id === 'migration_vs_ecology');
  assert.equal(finding().status, 'unavailable');
  input.genomic_ecological_concordance.readiness.distinct_migration_contexts = 8;
  assert.equal(finding().status, 'association');
  input.genomic_ecological_concordance.readiness.minimum_unique_samples = 12;
  assert.equal(finding().status, 'unavailable');
});
test('QC unknowns and US detection context cannot imply linkage for foreign samples', () => {
  const input = {samples:[{country:'New Zealand',segments_pass:8},{segments_pass:3},{segments_pass:null}],outbreak_context:{status:'READY',records:[{}],sha256:'example'}};
  const result = summarize(input);
  assert.match(result.findings[0].text, /1 have all eight.*1 have fewer.*1 lack/);
  assert.match(result.findings.at(-1).text, /has not matched/);
  assert.match(result.limitations.join(' '), /US wild birds/);
  assert.match(result.headline, /does not yet contain enough/);
});
test('knowledge layer prioritizes meaning and action over analytical inventory', () => {
  const result=summarize(payload([]));
  assert.match(result.headline,/complete genomes.*not yet enough comparative evidence/);
  assert.match(result.knowledge.genomes,/strong genomic foundation/);
  assert.match(result.knowledge.explanation,/not contain enough eligible comparisons/);
  assert.match(result.knowledge.action,/Add enough comparable samples/);
});
test('deterministic serializable output does not mutate input', () => {
  const input = payload([row({})]);
  const before = JSON.stringify(input);
  assert.equal(JSON.stringify(summarize(input)),JSON.stringify(summarize(input)));
  assert.equal(JSON.stringify(input),before);
  assert.equal(JSON.parse(JSON.stringify(summarize(input))).rules_version, '1.0.0');
});
test('renderer uses text nodes, stays concise, and mounts before explorer controls', () => {
  class Node {
    constructor(tag) { this.tag=tag; this.children=[]; this.listeners={}; }
    append(...nodes) {this.children.push(...nodes);}
    setAttribute() {}
    addEventListener(name, callback) {this.listeners[name]=callback;}
    set innerHTML(_) {throw Error('Unsafe HTML');}
  }
  context.document = {createElement:tag=>new Node(tag),getElementById:()=>null};
  const input=payload([row({diagnostic:'<img src=x onerror=alert(1)>'})]);
  const panel=new Node('section');
  mount({payload:input,root:{}},panel);
  const all=[];
  function walk(node){all.push(node);node.children.forEach(walk);}
  walk(panel);
  assert.ok(all.some(n=>n.tag==='p' && n.textContent==='KNOWLEDGE FOR ACTION'));
  assert.ok(all.some(n=>n.tag==='h3' && n.textContent==='What public health can do next'));
  assert.ok(!all.some(n=>n.textContent==='Why WINGS reached this conclusion'));
  assert.ok(!all.some(n=>n.tag==='details'));
  assert.ok(source.indexOf('WINGS_EVIDENCE_SYNTHESIS.mount(explorer, app)') < source.indexOf('app.append(toolbar)'));
  assert.match(source,/app\.append\(toolbar\);\s*if \(subtitle\) app\.append\(subtitle\);/);
});

test('renderer prefers a validated embedded local interpretation', () => {
  class Node {
    constructor(tag) { this.tag=tag; this.children=[]; }
    append(...nodes) {this.children.push(...nodes);}
    setAttribute() {}
    addEventListener() {}
  }
  const record={schema_version:'wings.public-health-interpretation.v1',status:'GENERATED',model:'gpt-oss:20b',evidence_sha256:'abcdef1234567890',narrative:{
    headline:'Host and season form the clearest combined pattern.',
    what_we_know:[{title:'Connected pattern',text:'The supported comparisons align.'},{title:'Detection context',text:'Records overlap the study period.'}],
    public_health_meaning:{text:'Sampling should preserve host and seasonal contrasts.'},
    recommended_actions:[{text:'Collect comparable samples across both host groups.'}]
  }};
  context.document={createElement:tag=>new Node(tag),getElementById:id=>id==='llm-record'?{textContent:JSON.stringify(record)}:null};
  const panel=new Node('section');
  mount({payload:payload([]),root:{dataset:{wseInterpretationId:'llm-record'}}},panel);
  const all=[]; (function walk(node){all.push(node);node.children.forEach(walk);})(panel);
  assert.ok(all.some(n=>n.tag==='h2' && n.textContent===record.narrative.headline));
  assert.ok(all.some(n=>n.tag==='h3' && n.textContent==='Connected pattern'));
  assert.ok(all.some(n=>n.tag==='li' && n.textContent.includes('Collect comparable')));
  assert.ok(all.some(n=>n.tag==='small' && n.textContent.includes('gpt-oss:20b')));
  assert.ok(all.some(n=>n.tag==='h3' && n.textContent==='Observed findings'));
  assert.ok(all.some(n=>n.tag==='h3' && n.textContent==='Public Health Implications'));
  assert.ok(all.some(n=>n.tag==='h3' && n.textContent==='Suggested follow-up'));
  assert.ok(all.some(n=>n.tag==='small' && n.textContent.includes('scientific review pending')));
});

test('empty recommendations omit the follow-up section without substituting advice', () => {
  class Node {
    constructor(tag) { this.tag=tag; this.children=[]; }
    append(...nodes) {this.children.push(...nodes);}
    setAttribute() {}
    addEventListener() {}
  }
  const record={schema_version:'wings.public-health-interpretation.v1',status:'GENERATED',model:'local',evidence_sha256:'abc',narrative:{
    headline:'A limited observation.',what_we_know:[{title:'Observation',text:'Source-rendered finding.'}],
    public_health_meaning:{text:'Interpretation to review.'},recommended_actions:[]
  }};
  context.document={createElement:tag=>new Node(tag),getElementById:()=>({textContent:JSON.stringify(record)})};
  const panel=new Node('section');
  mount({payload:payload([]),root:{dataset:{wseInterpretationId:'record'}}},panel);
  const all=[];(function walk(node){all.push(node);node.children.forEach(walk);})(panel);
  assert.ok(!all.some(n=>n.className==='wse-evidence-action'));
  assert.ok(!all.some(n=>n.tag==='li'));
  assert.ok(all.some(n=>n.tag==='h2' && n.textContent==='A limited observation.'));
});

test('implications lead the report and observations render source bullets as text', () => {
  class Node {
    constructor(tag) { this.tag=tag; this.children=[]; }
    append(...nodes) { this.children.push(...nodes); }
    setAttribute() {}
    set innerHTML(_) { throw Error('Unsafe HTML'); }
  }
  const record={schema_version:'wings.public-health-interpretation.v1',status:'GENERATED',model:'local',evidence_sha256:'abc',narrative:{
    headline:'Shared host records merit joint review.',
    public_health_meaning:{text:'Legacy paragraph.',items:[
      {title:'Review together',text:'Use the linked records for a joint review.'},
      {title:'Check timing',text:'Align records by collection period.'}
    ]},
    what_we_know:[{title:'Host groups',text:'Long source paragraph retained in JSON.',bullets:[
      'Two recorded hosts share a selected group.', '<img src=x onerror=alert(1)>'
    ]}],recommended_actions:[]
  }};
  context.document={createElement:tag=>new Node(tag),getElementById:()=>({textContent:JSON.stringify(record)})};
  const panel=new Node('section');
  mount({payload:payload([]),root:{dataset:{wseInterpretationId:'record'}}},panel);
  const box=panel.children[0];
  const meaning=box.children.find(n=>n.className==='wse-evidence-meaning');
  const story=box.children.find(n=>n.className==='wse-evidence-story');
  assert.ok(box.children.indexOf(meaning)<box.children.indexOf(story));
  assert.equal(meaning.children[0].textContent,'Public Health Implications');
  assert.equal(meaning.children[1].tag,'ul');
  assert.equal(meaning.children[1].children.length,2);
  assert.equal(story.children[0].children[1].tag,'ul');
  assert.equal(story.children[0].children[1].children.length,2);
  assert.equal(story.children[0].children[1].children[1].textContent,'<img src=x onerror=alert(1)>');
  assert.ok(!story.children[0].children.some(n=>n.tag==='p'));
  assert.ok(!box.children.some(n=>n.className==='wse-evidence-action'));
  record.narrative.grounding = {mode:'analysis_selection', presentation_version:'public-health-implications-v2'};
  record.narrative.public_health_meaning.note = 'Early findings: each comparison used 10 of the 30 samples.';
  const analysisPanel = new Node('section');
  mount({payload:payload([]),root:{dataset:{wseInterpretationId:'record'}}},analysisPanel);
  const analysisBox = analysisPanel.children[0];
  assert.ok(!analysisBox.children.some(n=>n.tag==='details' || n.tag==='summary'));
  assert.ok(!analysisBox.children.some(n=>n.className==='wse-evidence-story' || n.tag==='small'));
  const briefMeaning = analysisBox.children.find(n=>n.className==='wse-evidence-meaning');
  assert.equal(briefMeaning.children.find(n=>n.className==='wse-evidence-scope').textContent, record.narrative.public_health_meaning.note);
  record.narrative.grounding = {mode:'staged_briefing'};
  record.generation_mode = 'staged';
  const stagedPanel = new Node('section');
  mount({payload:payload([]),root:{dataset:{wseInterpretationId:'record'}}},stagedPanel);
  assert.ok(!stagedPanel.children[0].children.some(n=>n.tag==='details' || n.className==='wse-evidence-story'));
  record.status = 'ERROR';
  const failedPanel = new Node('section');
  mount({payload:payload([]),root:{dataset:{wseInterpretationId:'record'}}},failedPanel);
  assert.equal(failedPanel.children[0].children[0].textContent,'Public Health Implications');
  assert.match(failedPanel.children[0].children[1].textContent,/not available yet/);

});
