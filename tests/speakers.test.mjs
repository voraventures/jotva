import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFile, mkdtemp} from 'node:fs/promises';
import {createRequire} from 'node:module';
import {join,resolve} from 'node:path';
import {tmpdir} from 'node:os';
import vm from 'node:vm';
import {build} from 'esbuild';
import {transcriptText} from '../src/transcriptText.js';
const require=createRequire(import.meta.url);
const {JSDOM}=require(join(process.env.JOTVA_TEST_DEPS,'node_modules/jsdom'));

test('transcript copy/download retain names, timestamps and text',()=>{
 const data={_segments:[{speaker:'Maya',start:65,text:'First turn.'},{speaker:'Room 4',start:70,text:'Second turn.'},{text:'Unknown.',start:NaN}]};
 assert.equal(transcriptText(data),'[1:05] Maya: First turn.\n\n[1:10] Room 4: Second turn.\n\nSpeaker: Unknown.');
 assert.equal(transcriptText({text:'Legacy text'}),'Legacy text');
});

test('Meet adapter abstains without explicit speaking semantics',async()=>{
 const dom=new JSDOM('<div data-participant-id="p1" data-participant-name="Maya"></div><div data-participant-id="p2" data-participant-name="Room 4" data-is-speaking="true"></div>');
 const context={document:dom.window.document};vm.createContext(context);
 vm.runInContext(await readFile('extensions/meet/adapter.js','utf8'),context);
 assert.deepEqual(JSON.parse(JSON.stringify(context.JotvaMeetAdapter.read())),[{id:'p2',name:'Room 4'}]);
 dom.window.document.querySelector('[data-participant-id=p2]').setAttribute('data-participant-name','Renamed room');
 assert.equal(context.JotvaMeetAdapter.read()[0].name,'Renamed room');
 dom.window.document.querySelector('[data-participant-id=p2]').removeAttribute('data-is-speaking');
 assert.equal(context.JotvaMeetAdapter.read().length,0);
 dom.window.close();
});

test('extension scope and all six translations are complete',async()=>{
 const manifest=JSON.parse(await readFile('extensions/meet/manifest.json','utf8'));
 assert.equal(manifest.manifest_version,3);
 assert.deepEqual(manifest.permissions,['nativeMessaging','storage']);
 assert.deepEqual(manifest.host_permissions,['https://meet.google.com/*']);
 assert.equal(manifest.externally_connectable,undefined);
 const keys=object=>Object.entries(object).flatMap(([k,v])=>typeof v==='object'?keys(v).map(s=>k+'.'+s):k).sort();
 const en=JSON.parse(await readFile('src/locales/en/translation.json','utf8')).speakers;
 for(const lang of ['es','fr','pt','ko','zh'])assert.deepEqual(keys(JSON.parse(await readFile(`src/locales/${lang}/translation.json`,'utf8')).speakers),keys(en));
});

for(const state of ['speakers','speakers-failed']) test(`named transcript, timeline and setup DOM (${state})`,async()=>{
 const dom=new JSDOM('<div id="root"></div>',{url:`http://127.0.0.1:5198/tests/visual/frame.html?state=${state}`,pretendToBeVisual:true});
 for(const name of ['window','document','location','localStorage','HTMLElement','Node','Event','MouseEvent','KeyboardEvent','requestAnimationFrame','cancelAnimationFrame'])Object.defineProperty(globalThis,name,{configurable:true,value:dom.window[name]});
 Object.defineProperty(globalThis,'navigator',{configurable:true,value:dom.window.navigator});
 dom.window.HTMLElement.prototype.scrollTo=()=>{};dom.window.HTMLElement.prototype.scrollIntoView=()=>{};
 const output=join(await mkdtemp(join(tmpdir(),'jotva-speaker-dom-')),'preview.cjs');
 await build({entryPoints:[resolve('tests/visual/preview.jsx')],outfile:output,bundle:true,platform:'node',format:'cjs',loader:{'.css':'empty','.svg':'text','.woff2':'empty','.webm':'empty','.jpg':'empty','.png':'empty'},define:{'import.meta.env.DEV':'true'},logLevel:'silent'});
 globalThis.IS_REACT_ACT_ENVIRONMENT=false;
 const {act,previewRoot}=require(output);await new Promise(r=>setTimeout(r,80));globalThis.IS_REACT_ACT_ENVIRONMENT=true;
 const click=async label=>{const button=[...document.querySelectorAll('button')].find(b=>b.textContent.trim()===label);assert.ok(button,label);await act(async()=>button.click());};
 try {
  await click('Transcript');
  assert.equal(document.querySelector('.tr-speaker').textContent,state==='speakers'?'Maya Chen':'Speaker 1');
  assert.equal(document.querySelectorAll('.tr-turn').length,24);
  assert.equal(document.querySelectorAll('.transcript-actions button').length,2);
  assert.ok(document.querySelector('.speaker-notice').textContent.includes(state==='speakers'?'Click a name to correct it':'transcript is preserved'));
  await click('Timeline');assert.equal(document.querySelectorAll('.tl-speaker').length,24);
  assert.equal(document.querySelector('.tl-speaker').textContent,state==='speakers'?'Maya Chen':'Speaker 1');
  await click('Record');await click('Recording settings');
  assert.equal(document.querySelector('.speaker-toggle input').checked,false);
  assert.ok(document.querySelector('.speaker-settings').textContent.includes('not yet validated'));
  await act(async()=>document.querySelector('.speaker-toggle input').click());
  assert.equal(document.querySelector('.speaker-toggle input').checked,false,'failed save is not optimistic');
  assert.ok(document.querySelector('.speaker-settings [role=alert]'));
 } finally {await act(async()=>previewRoot.unmount());globalThis.IS_REACT_ACT_ENVIRONMENT=false;dom.window.close();}
});
