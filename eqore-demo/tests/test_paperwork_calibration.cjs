// Run from eqore-demo: node tests/test_paperwork_calibration.cjs
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),{spawnSync}=require('node:child_process');
const path=require('node:path');
const home=path.resolve(__dirname,'..');
const fixture=spawnSync('python3',['-c',`
import json
import paperwork as p
s=p.seed()
a=p.view(s,'pm_jordan','summit_precision')
s=p.apply(s,'pm_jordan',{'type':'track_requirement','project_id':'summit_precision','requirement_id':'interconnection_application','due_at':'2026-12-01T19:30:00+00:00'})
b=p.view(s,'pm_jordan','summit_precision')
s=p.apply(s,'pm_jordan',{'type':'set_requirement_review','project_id':'summit_precision','requirement_id':'interconnection_application','review_due_at':'2026-12-15T19:30:00+00:00'})
c=p.view(s,'pm_jordan','summit_precision')
print(json.dumps([a,b,c]))
`],{cwd:home,encoding:'utf8',env:{...process.env,PYTHONDONTWRITEBYTECODE:'1'}});
assert.equal(fixture.status,0,fixture.stderr);const [before,tracked,reviewed]=JSON.parse(fixture.stdout);
const events={},scroll={scrollTop:0,scrollLeft:0,dataset:{},setAttribute(){},closest(){return null;}};
const root={innerHTML:'',addEventListener(type,fn){events[type]=fn;},querySelector(){return null;},querySelectorAll(s){return s==='.scroll'?[scroll]:[];}};
const sent=[];let response=tracked;
const context={console,Date,Intl,URL,URLSearchParams,setTimeout,clearTimeout,location:{search:'',hostname:'localhost'},sessionStorage:{getItem(){return 'test';}},document:{getElementById(){return root;},addEventListener(){}},requestAnimationFrame(fn){fn();},FormData:class {constructor(form){return new Map(Object.entries(form.values||{}));}},fetch:async(url,options)=>{sent.push({url,body:options.body?JSON.parse(options.body):null});return {ok:true,json:async()=>response};}};
vm.createContext(context);
const source=fs.readFileSync(path.join(home,'web/paperwork.js'),'utf8').replace('  start();','  globalThis.testUI={ui,render,visit,goBack,isoInput,inputDateTime};');
vm.runInContext(source,context);const t=context.testUI;
const set=data=>Object.assign(t.ui,{data,projectId:data.selected_project.id,modal:null,notice:null,busy:false,coverageFilter:'all'});
const click=(action,id)=>events.click({target:{dataset:{action,id},closest(){return this;}}});
const submit=(id,values)=>events.submit({preventDefault(){},target:{id,values,classList:{contains(){return false;}}}});
(async()=>{
 set(before);t.ui.view='project';t.render();assert(root.innerHTML.includes('Document coverage'));
 await click('compliance');assert.equal(t.ui.view,'compliance');assert.equal((root.innerHTML.match(/class="coverage-card"/g)||[]).length,20);assert(root.innerHTML.includes('Completion evidence'));assert(root.innerHTML.includes('Not tracked'));assert(root.innerHTML.includes('Later phase'));assert(!root.innerHTML.includes('[object Object]'));
 await click('coverage-filter','later');assert((root.innerHTML.match(/class="coverage-card"/g)||[]).length>0);assert(!root.innerHTML.includes('Update due'));
 t.ui.view='references';t.render();assert(root.innerHTML.includes('Century-Tywood'));assert(root.innerHTML.includes('250 kW / 760 kWh'));assert(root.innerHTML.includes('Gotion Edge 760'));assert(root.innerHTML.includes('12 files reviewed'));assert(root.innerHTML.includes('Items to confirm'));assert(!root.innerHTML.includes('[object Object]'));assert(!root.innerHTML.includes('file:///'));
 await click('compliance');await click('track-requirement','interconnection_application');assert(root.innerHTML.includes('type="datetime-local" name="due_at" required'));assert(!root.innerHTML.includes('name="due_at" required value='));
 await submit('track-requirement-form',{due_at:''});assert.equal(sent.length,0);assert(t.ui.notice.error);assert.equal(t.ui.modal.type,'track-requirement');
 await submit('track-requirement-form',{due_at:'2026-12-01T14:30'});assert.equal(sent.length,1);assert.equal(sent[0].body.action.type,'track_requirement');assert.equal(sent[0].body.action.due_at,new Date('2026-12-01T14:30').toISOString());assert.equal(t.ui.view,'document');assert.equal(t.ui.docId,'C_interconnection_application');assert.equal(t.ui.modal,null);await t.goBack();assert.equal(t.ui.view,'compliance');assert.equal(t.ui.coverageFilter,'all');
 set(reviewed);t.ui.view='compliance';t.render();assert(root.innerHTML.includes('Open tracked document'));await click('review-requirement','interconnection_application');assert(root.innerHTML.includes('value="'+t.inputDateTime('2026-12-15T19:30:00+00:00')+'"'));
 response=reviewed;const count=sent.length;await submit('requirement-review-form',{review_due_at:'2026-12-15T14:30',changed_at:'2026-11-06T10:00',change_reason:''});assert.equal(sent.length,count);assert(t.ui.notice.error);
 await submit('requirement-review-form',{review_due_at:'2026-12-15T14:30',changed_at:'2026-11-06T10:00',change_reason:'Equipment revision changed'});assert.equal(sent.at(-1).body.action.type,'set_requirement_review');assert.equal(sent.at(-1).body.action.change_reason,'Equipment revision changed');assert.equal(sent.at(-1).body.action.changed_at,new Date('2026-11-06T10:00').toISOString());
 set(reviewed);t.ui.view='queue';await click('open-compliance','summit_precision|interconnection_application');assert.equal(t.ui.view,'compliance');assert.equal(t.ui.coverageFilter,'attention');
 const archive=JSON.parse(JSON.stringify(reviewed));archive.selected_project.status='archived';set(archive);t.ui.view='compliance';t.ui.coverageFilter='all';t.render();assert(!root.innerHTML.includes('data-action="track-requirement"'));assert(!root.innerHTML.includes('data-action="review-requirement"'));await click('track-requirement','interconnection_application');assert.equal(t.ui.modal,null);
 console.log('PASS: 20 source-based coverage rows, references and sources, attention/later views, no guessed deadlines, ISO date conversion, tracking/opening, review metadata, Back restoration, follow-up routing and read-only archives.');
})().catch(error=>{console.error(error);process.exitCode=1;});
