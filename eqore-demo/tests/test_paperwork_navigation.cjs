// Run with node tests/test_paperwork_navigation.cjs. Exercise the actual rail
// handlers, including mouse focus, explicit collapse and touch pointerleave.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const rootEvents={},documentEvents={},railEvents={};
const classes=new Set(),attributes={},label={textContent:''};
let hoverCapable=true,pointerInside=false,renderCount=0;
const shell={classList:{toggle(name,on){if(on)classes.add(name);else classes.delete(name);}}};
const sidebar={
  addEventListener(type,handler){railEvents[type]=handler;},
  matches(selector){return selector===':hover'&&pointerInside;},
  contains(element){return Boolean(element?.inSidebar);},
};
const toggle={
  inSidebar:true,dataset:{action:'toggle-nav'},
  setAttribute(key,value){attributes[key]=value;},
  querySelector(){return label;},
  closest(selector){return selector==='#workspace-navigation'?sidebar:this;},
  matches(){return false;},
};
const outside={closest(){return null;},matches(){return false;}};
const scrim={hidden:true};
const main={focus(){railEvents.focusout({relatedTarget:outside});}};
const elements={'.shell':shell,'.rail-toggle':toggle,'.nav-scrim':scrim,'#workspace-navigation':sidebar,'#main':main};
const root={
  addEventListener(type,handler){rootEvents[type]=handler;},
  querySelector(selector){return elements[selector]||null;},querySelectorAll(){return [];},
  set innerHTML(value){renderCount++;},
};
const context={
  console,URLSearchParams,URL,Date,Intl,setTimeout,clearTimeout,
  location:{search:''},sessionStorage:{getItem(){return null;}},
  document:{getElementById(){return root;},addEventListener(type,handler){documentEvents[type]=handler;}},
  matchMedia(){return {matches:hoverCapable};},requestAnimationFrame(fn){fn();},
};
vm.createContext(context);
const source=fs.readFileSync(path.join(__dirname,'../web/paperwork.js'),'utf8');
vm.runInContext(source.replace('  start();','  globalThis.testRail={ui,navigation,attachNavigation,navigationExpanded};'),context);
const state=context.testRail;
const check=(expanded,message)=>{
  assert.equal(state.navigationExpanded(),expanded,message);
  assert.equal(classes.has('nav-expanded'),expanded,message+' CSS state');
  assert.equal(attributes['aria-expanded'],String(expanded),message+' ARIA state');
  assert.equal(attributes['aria-label'],`${expanded?'Collapse':'Expand'} navigation`,message+' control label');
};
const key=(key,target=toggle)=>documentEvents.keydown({key,target});
const pointer=(type,target=toggle)=>documentEvents.pointerdown({pointerType:type,target});
const enter=(type='mouse')=>{pointerInside=true;railEvents.pointerenter({pointerType:type});};
const leave=(type='mouse')=>{pointerInside=false;railEvents.pointerleave({pointerType:type});};
const click=target=>rootEvents.click({target:target||toggle});

(async()=>{
  state.attachNavigation();check(false,'rail starts collapsed');
  enter();check(true,'mouse enter opens rail');
  pointer('mouse');railEvents.focusin({target:toggle});
  leave();check(false,'mouse focus does not hold rail open after pointer leaves');
  enter();await click();check(false,'Collapse wins while pointer remains over rail');
  state.attachNavigation();check(false,'unrelated render does not undo explicit collapse');
  leave();enter();check(true,'next pointer visit opens rail again');
  key('Escape');check(false,'Escape closes hovered rail');
  leave();

  key('Tab',outside);railEvents.focusin({target:toggle});
  check(true,'keyboard focus exposes navigation labels');
  railEvents.focusout({relatedTarget:{inSidebar:true}});check(true,'tabbing within rail keeps it open');
  railEvents.focusout({relatedTarget:outside});check(false,'leaving rail by keyboard collapses it');
  key('Tab',outside);railEvents.focusin({target:toggle});
  await click();check(false,'keyboard Collapse closes rail without removing focus');
  key('Tab');check(true,'next Tab exposes labels for the next control');
  pointer('mouse');leave();check(false,'pointer interaction clears old keyboard expansion');

  hoverCapable=false;
  pointer('touch');enter('touch');check(false,'touch does not trigger hover expansion');
  await click();check(true,'touch toggle opens menu');assert.equal(scrim.hidden,false);
  leave('touch');check(true,'finger lift does not close the touch menu');
  await click();check(false,'touch toggle closes menu');assert.equal(scrim.hidden,true);
  await click();
  await click({dataset:{action:'close-nav'},closest(){return this;}});
  check(false,'touch scrim closes menu');assert.equal(scrim.hidden,true);
  await click();key('Escape');check(false,'Escape closes explicitly opened menu');
  hoverCapable=true;
  enter();check(true,'mouse hover works after closing a touch menu');
  await click();await click();check(true,'second explicit toggle reopens menu');
  leave();check(false,'desktop explicit opening still collapses when pointer leaves');

  assert.equal(renderCount,0,'expansion updates do not rerender or reset page scroll');
  assert(source.includes('aria-label="Site coordination" title="Crew, deliveries and procurement"'));
  assert(!source.includes('Other coordination'));
  assert(!source.includes('Other project coordination'));
  assert(source.includes('<h3>Site coordination</h3>'));
  const css=fs.readFileSync(path.join(__dirname,'../web/paperwork.css'),'utf8');
  assert(!css.includes('.sidebar:focus-within'));
  assert(!css.includes('.sidebar:hover'));
  console.log('PASS: hover/collapse, pointer-vs-keyboard focus, Escape, touch toggle/scrim/finger-lift, ARIA state and scroll preservation.');
})().catch(error=>{console.error(error);process.exitCode=1;});
