const {test, describe} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.resolve(__dirname, '..');
const ORDER = ['PB2','PB1','PA','HA','NP','NA','MP','NS'];

class Node {
  constructor(tag, text = '') {Object.assign(this, {tag, text, children:[], attrs:{}, events:{}, parent:null, hidden:false});}
  get textContent() {return this.text + this.children.map(node => node.textContent).join('');}
  set textContent(value) {this.text=String(value);this.children=[];}
  append(...nodes) {
    for (const node of nodes) {
      if (node.parent) node.parent.children.splice(node.parent.children.indexOf(node), 1);
      node.parent=this;this.children.push(node);
    }
  }
  querySelectorAll(tag) {return this.children.flatMap(node => [...(node.tag === tag ? [node] : []), ...node.querySelectorAll(tag)]);}
  querySelector(tag) {return this.querySelectorAll(tag)[0] || null;}
  setAttribute(name, value) {this.attrs[name]=String(value);}
  getAttribute(name) {return this.attrs[name] ?? null;}
  replaceWith(replacement) {
    const parent=this.parent, index=parent.children.indexOf(this);
    parent.children.splice(index, 1, replacement);replacement.parent=parent;this.parent=null;
  }
  addEventListener(name, handler, capture=false) {(this.events[name] ||= []).push({handler, capture});}
  dispatch(name, key) {
    const event={key, stopped:false, prevented:false, preventDefault(){this.prevented=true;},stopImmediatePropagation(){this.stopped=true;}};
    for (const capture of [true,false]) for (const listener of this.events[name] || []) {
      if (listener.capture === capture && !event.stopped) listener.handler(event);
    }
    return event;
  }
}

function fixture(source) {
  const table=new Node('table'), head=new Node('thead'), headerRow=new Node('tr'), body=new Node('tbody');
  for (const text of ['Segment','Top BLAST hit','Identity (%)','Query coverage (%)','E-value','Bit score','BLAST status']) headerRow.append(new Node('th',text));
  head.append(headerRow);table.append(head,body);
  const rows={};
  for (const segment of ['HA','NA','PB2','PB1','PA','NP','MP','NS']) {
    const skipped=segment === 'PB2', row=new Node('tr'), hit=new Node('td'), link=new Node('a',skipped?'SKIPPED_QC':'PX873818.1');
    link.setAttribute('href', skipped?'https://www.ncbi.nlm.nih.gov/nuccore?term=SKIPPED_QC':'https://www.ncbi.nlm.nih.gov/nuccore/PX873818.1');
    hit.append(link);
    row.append(new Node('td',segment), hit, new Node('td',skipped?'':'99.883'), new Node('td',skipped?'':'100.000'),
      new Node('td',skipped?'':'0.000'), new Node('td',skipped?'':'3136.000'), new Node('td',skipped?'SKIPPED_QC':'HIGH_CONFIDENCE'));
    rows[segment]=row;body.append(row);
  }
  const section=new Node('section');section.append(table);
  const document={readyState:'loading',addEventListener(){},createElement:tag=>new Node(tag),getElementById:id=>id==='blast-top-hits'?section:null};
  const context=vm.createContext({document});
  vm.runInContext(fs.readFileSync(path.join(root, source),'utf8'),context);
  return {api:context.WINGS_SAMPLE_PRESENTATION, table, body, rows, header:headerRow.children[0], headers:headerRow.children,
    order:()=>body.children.map(row=>row.children[0].textContent)};
}

for (const source of ['scripts/report/sample-report-presentation.js','scripts/report/sample-navigation.js']) describe(source, () => {
  test('initial segment order uses the eight-segment sequence and preserves existing rows', () => {
    const h=fixture(source);h.rows.PA.hidden=true;
    h.api.mountBlastTable(h.table);
    assert.deepEqual(h.order(), ORDER);
    assert.equal(h.body.children[2],h.rows.PA);assert.equal(h.rows.PA.hidden,true);
    assert.equal(h.headers.length,7);
    assert.equal(h.header.getAttribute('aria-sort'),'ascending');
  });
  test('skipped hits become plain text while accession links and status values remain exact', () => {
    const h=fixture(source), hit=h.rows.HA.children[1].children[0], href=hit.getAttribute('href');
    h.api.mountBlastTable(h.table);
    assert.equal(h.rows.PB2.children[1].querySelector('a'),null);
    assert.equal(h.rows.PB2.children[1].textContent,'SKIPPED_QC');
    assert.equal(h.rows.PB2.children[6].textContent,'SKIPPED_QC');
    assert.equal(h.rows.HA.children[1].querySelector('a'),hit);
    assert.equal(hit.getAttribute('href'),href);
  });
  test('numeric display removes zeros without rounding and retains the recorded value', () => {
    const h=fixture(source);h.api.mountBlastTable(h.table);
    const cells=h.rows.HA.children;
    assert.deepEqual(cells.slice(2,6).map(cell=>cell.textContent),['99.883','100','0','3136']);
    assert.equal(cells[2].getAttribute('data-wings-recorded-value'),null);
    assert.equal(cells[3].getAttribute('data-wings-recorded-value'),'100.000');
    assert.equal(cells[4].getAttribute('data-wings-recorded-value'),'0.000');
    assert.equal(h.rows.PB2.children[2].textContent,'');
  });
  test('segment clicks override the older alphabetical sorter and toggle semantic direction', () => {
    const h=fixture(source);let legacyCalls=0;
    h.header.addEventListener('click',()=>legacyCalls++);
    h.api.mountBlastTable(h.table);
    const event=h.header.dispatch('click');
    assert.equal(event.prevented,true);assert.equal(legacyCalls,0);
    assert.deepEqual(h.order(),[...ORDER].reverse());
    assert.equal(h.header.getAttribute('aria-sort'),'descending');
    h.header.dispatch('click');assert.deepEqual(h.order(),ORDER);
  });
  test('keyboard sorting uses the same order and other column listeners are retained', () => {
    const h=fixture(source);let otherCalls=0;
    h.headers[2].addEventListener('click',()=>otherCalls++);
    h.api.mountBlastTable(h.table);
    h.header.dispatch('keydown','Enter');assert.deepEqual(h.order(),[...ORDER].reverse());
    h.header.dispatch('keydown',' ');assert.deepEqual(h.order(),ORDER);
    h.header.dispatch('keydown','ArrowDown');assert.deepEqual(h.order(),ORDER);
    h.headers[2].dispatch('click');assert.equal(otherCalls,1);
  });
  test('startup transforms the BLAST section once', () => {
    const h=fixture(source);h.api.initialize();
    assert.deepEqual(h.order(),ORDER);
    const api=h.api.mountBlastTable(h.table);h.api.initialize();
    assert.equal(h.api.mountBlastTable(h.table),api);
    assert.equal(h.header.events.click.length,1);
  });
  test('unknown segments remain last and unrelated tables remain untouched', () => {
    const h=fixture(source), unknown=new Node('tr');unknown.append(new Node('td','OTHER'));h.body.append(unknown);
    const api=h.api.mountBlastTable(h.table);api.sortSegments(true);
    assert.equal(h.body.children.at(-1),unknown);
    const other=new Node('table');assert.equal(h.api.mountBlastTable(other),null);
  });
  test('zero trimming handles precision, grouped numbers, missing values and scientific notation', () => {
    const h=fixture(source);
    for (const [recorded,display] of [['100.000','100'],['99.721','99.721'],['99.720','99.72'],['2,494.000','2,494'],
      ['0.00100','0.001'],['3.000e-20','3e-20'],['1e-30','1e-30'],['0','0'],['',''],['Not available','Not available']]) {
      assert.equal(h.api.trimMetricZeros(recorded),display);
    }
  });
});
