(() => {
  'use strict';
  const app = document.getElementById('app');
  const ui = {
    data:null, view:'portfolio', caseId:null, messageId:null, vendorId:null, phaseId:null, tab:'change', busy:false, notice:null, job:null, cluster:false, pages:{
    }
    , calendarFilter:'upcoming', vendorFilter:'all', vendorQuery:'', dialog:null,
    portfolioFilter:'all', mapRegion:'MA', resourceTab:'teams', subcontractId:null, weekOffset:0, updates:null
  }
  ;
  const arr = x => Array.isArray(x) ? x : x && typeof x === 'object' ? Object.values(x) : [];
  const esc = x => String(x ?? '').replace(/[&<>"']/g, c => ({
    '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'
  }
  [c]));
  const displayName = x => String(x ?? '').replace(/\s*\((?:fictional|synthetic)\)/gi, '').replace(/\s+demo team\b/gi, ' team').trim();
  const human = x => String(x ?? '').replace(/_/g, ' ');
  const state = () => ui.data?.state || {
  }
  ;
  const project = () => state().project || {
  }
  ;
  const ops = () => ui.data?.operations || {
  }
  ;
  const resources = () => ui.data?.workspace?.resources || {};
  const people = () => arr(state().stakeholders);
  const person = id => people().find(x => x.id === id);
  const personName = id => displayName(person(id)?.name || id || 'Unassigned');
  const taskName = id => arr(state().tasks).find(x => x.id === id)?.title || id;
  const contractorRequests = () => arr(ui.data?.workspace?.contractor_requests).filter(r=>!r.case_id&&!['completed','closed','resolved','rejected'].includes(r.status));
  const cases = () => arr(ops().cases).slice().sort((a,b) => (Number(b.priority)||0) - (Number(a.priority)||0));
  const messages = () => arr(ops().messages).slice().reverse().sort((a,b) => String(b.received_at).localeCompare(String(a.received_at)));
  const vendors = () => arr(ops().vendors || ui.data?.vendors).map(v => ({...v, name: displayName(v.name)}));
  const selectedCase = () => cases().find(x => x.id === ui.caseId);
  const closed = x => ['completed','closed','resolved','cancelled'].includes(x.status);
  const money = x => x !== null && x !== undefined && Number.isFinite(Number(x)) ? new Intl.NumberFormat('en-US',{
    style:'currency',currency:'USD',maximumFractionDigits:0
  }
  ).format(Number(x)) : 'Not recorded';
  const timezone = () => ui.data?.workspace?.timezone || project().timezone || project().time_zone || 'America/New_York';
  function dt(value,time=false) {
    if(!value)return 'Not recorded';
    const d=new Date(String(value).length===10?`${value}T12:00:00-05:00`:value);
    if(Number.isNaN(d.getTime()))return String(value);
    return new Intl.DateTimeFormat('en-US',{
      month:'short',day:'numeric',...(time?{
        hour:'numeric',minute:'2-digit'
      }
      :{
      }
      ),timeZone:timezone()
    }
    ).format(d);
  }
  function dayKey(value){
    if(!value)return '';
    try{
      return new Intl.DateTimeFormat('en-CA',{
        year:'numeric',month:'2-digit',day:'2-digit',timeZone:timezone()
      }
      ).format(new Date(value));
    }
    catch{
      return '';
    }
  }
  function readable(x){
    if(x==null)return 'Not recorded';
    if(typeof x==='string'||typeof x==='number')return String(x);
    if(Array.isArray(x))return x.map(readable).join(' · ');
    return Object.entries(x).map(([k,v])=>`${human(k)}: ${readable(v)}`).join(' · ');
  }
  const symbols={
    portfolio:'<path d="M3 5l6-2 6 2 6-2v16l-6 2-6-2-6 2V5Zm6-2v16m6-14v16"/>',site:'<path d="M3 21V9l7-5v5l7-5v8h4v9H3Zm4-4h2m4 0h2m3 0h1"/>',calendar:'<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M7 3v4m10-4v4M3 11h18"/>',inbox:'<path d="M3 4h18v16H3V4Zm0 10h5l2 3h4l2-3h5"/>',vendor:'<circle cx="9" cy="7" r="3"/><path d="M3 21v-4a6 6 0 0 1 12 0v4m1-16a3 3 0 0 1 0 6m2 3a5 5 0 0 1 3 4v3"/>',arrow:'<path d="M4 12h16m-6-6 6 6-6 6"/>',back:'<path d="M20 12H4m6-6-6 6 6 6"/>',refresh:'<path d="M20 4v6h-6M4 20v-6h6m-5-5a8 8 0 0 1 14-3m0 9a8 8 0 0 1-14 3"/>',spark:'<path d="m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5L12 3Z"/>',chevron:'<path d="m9 5 7 7-7 7"/>',check:'<path d="m4 12 5 5L20 6"/>',clock:'<circle cx="12" cy="12" r="9"/><path d="M12 6v6l4 3"/>',paper:'<path d="M7 3h8l4 4v14H5V3h2Zm8 0v5h4M8 12h8m-8 4h6"/>',settings:'<path d="M4 6h16M4 12h16M4 18h16M8 3v6m8 0v6M9 15v6"/>',plus:'<path d="M12 4v16M4 12h16"/>'
  }
  ;
  const icon = n => `<svg class="icon" viewBox="0 0 24 24" aria-hidden="true">${symbols[n]||symbols.paper}</svg>`;
  const priority = x => Number(x)>=90 ? 'Urgent' : Number(x)>=70 ? 'High' : Number(x)>0 ? 'Medium' : 'No active case';
  const tone = s => /urgent|high|rejected|blocked|expired|failed/i.test(s) ? 'hot' : /confirmed|completed|approved|accepted|booked/i.test(s) ? 'green' : /pending|waiting|review|offered|clarification|awaiting/i.test(s) ? 'amber' : '';
  const pill = (s,t) => `<span class="pill ${esc(t||tone(String(s)))}">${esc(human(s||'Not recorded'))}</span>`;
  const btn = (text,action,id='',type='',disabled=false) => `<button type="button" class="btn ${type}" data-action="${esc(action)}"${id!==''?` data-id="${esc(id)}"`:''}${disabled||ui.busy?' disabled':''}>${esc(text)}</button>`;
  const link = (text,view) => `<button type="button" class="text-link" data-action="nav" data-id="${view}">${esc(text)} →</button>`;
  const empty = (title,detail='') => `<div class="empty"><h3>${esc(title)}</h3>${detail?`<p>${esc(detail)}</p>`:''}</div>`;
  const panelHead = (title,right='') => `<div class="panel-head"><h2>${esc(title)}</h2>${right}</div>`;
  const crumb = title => `<div class="breadcrumb"><button data-action="nav" data-id="portfolio">Portfolio</button><span>/</span><button data-action="nav" data-id="site">${esc(project().name)}</button>${title?`<span>/</span><span>${esc(title)}</span>`:''}</div>`;
  function heading(title,subtitle='',actions='',kicker=''){
    return `<div class="page-head"><div>${kicker?`<div class="eyebrow">${esc(kicker)}</div>`:''}<h1>${esc(title)}</h1>${subtitle?`<p>${esc(subtitle)}</p>`:''}</div><div class="head-actions">${actions}</div></div>`;
  }
  function pager(key,total,size=5){
    const pages=Math.max(1,Math.ceil(total/size));
    ui.pages[key]=Math.min(ui.pages[key]||0,pages-1);
    return `<div class="pager"><span>${total?`${ui.pages[key]*size+1}–${Math.min(total,(ui.pages[key]+1)*size)} of ${total}`:'0 records'}</span><div>${btn('←','page',`${key}:-1`,'quiet',ui.pages[key]===0)}${btn('→','page',`${key}:1`,'quiet',ui.pages[key]>=pages-1)}</div></div>`;
  }
  function pageRows(rows,key,size=5){
    const p=Math.min(ui.pages[key]||0,Math.max(0,Math.ceil(rows.length/size)-1));
    ui.pages[key]=p;
    return rows.slice(p*size,(p+1)*size);
  }
  function shell(content){
    const nav=[['portfolio','Portfolio'],['site','Site overview'],['calendar','Calendar'],['subcontractors','Subcontractors'],['procurement','Procurement'],['readiness','Readiness'],['inbox','Inbox'],['vendor','Vendors']];
    const current=ui.view==='vendors'||ui.view==='vendor-profile'?'vendor':ui.view;
    return `<div class="shell"><aside class="rail"><button class="brand" data-action="nav" data-id="portfolio" aria-label="EQORE portfolio"><span class="brand-mark">e</span><strong>EQORE</strong></button><nav aria-label="Workspace navigation">${nav.map(([k,label])=>`<button data-action="nav" data-id="${k==='vendor'?'vendors':k}" aria-label="${label}" title="${label}" class="rail-link ${current===k?'selected':''}" ${current===k?'aria-current="page"':''}>${icon(k==='subcontractors'?'vendor':k==='readiness'?'check':k==='procurement'?'paper':k)}<span>${label}</span></button>`).join('')}</nav><a class="contractor-link" href="/contractor.html" target="_blank" rel="noopener">${icon('arrow')}<span>Contractor portal ↗</span></a></aside><div class="workspace"><header class="topbar"><div class="top-location">${icon('portfolio')}<span>${ui.view==='portfolio'?'Deployment portfolio':esc(project().name||'Workspace')}</span>${ui.view!=='portfolio'?`<span class="muted">· ${esc(String(project().site||project().location||'').split(' · ')[0])}</span>`:''}</div><div class="top-right"><span id="updates-slot" aria-live="polite">${updateIndicator()}</span><button class="about-link" data-action="nav" data-id="about">About</button><span class="runtime"><i class="${ui.data.runtime?.available&&ui.data.runtime?.authenticated?'on':''}"></i>${ui.data.runtime?.available&&ui.data.runtime?.authenticated?'ChatGPT connected':'ChatGPT unavailable'}</span><button class="icon-button" data-action="refresh" aria-label="Refresh current records" ${ui.busy?'disabled':''}>${icon('refresh')}</button><div class="avatar" title="Deployment PM">PM</div></div></header><main id="main" class="main ${ui.view==='site'?'site-main':''}">${notices()}${content}</main><footer class="footer"><span>Deployment workspace</span><span>Project clock: ${esc(dt(project().now,true))} · ${esc(timezone())}</span></footer></div></div>${ui.dialog?dialog():''}`;
  }
  function updateIndicator() {
    return ui.updates?`<button class="updates-button" data-action="refresh" title="Refresh current project without changing your selection">New project updates · Refresh</button>`:'';
  }
  async function checkUpdates() {
    if(!ui.data||ui.busy||document.hidden)return;
    const selector=project().demo_project_id;
    if(!selector)return;
    try {
      const update=await api('/api/updates?project_id='+encodeURIComponent(selector));
      if(selector!==project().demo_project_id)return;
      const revision=ui.data.workspace?.portfolio_revision;
      if(revision!=null&&update.portfolio_revision!==revision) {
        ui.updates=update;
        const slot=document.getElementById('updates-slot');
        if(slot)slot.innerHTML=updateIndicator();
      }
    } catch { /* Background connectivity checks must not interrupt an active form. */ }
  }
  function notices(){
    return `${ui.data?.session_version===-1?`<div class="notice"><span>Another PM selected a different site. Reopen this site to make changes.</span>${btn('Reopen this site','project',project().demo_project_id,'quiet small-button')}</div>`:''}${ui.notice?`<div class="notice ${ui.notice.error?'error':''}" role="${ui.notice.error?'alert':'status'}"><span>${esc(ui.notice.text)}</span><button data-action="dismiss" aria-label="Dismiss notice">×</button></div>`:''}${ui.job?`<div class="notice" role="status"><span class="spinner"></span><span>${esc(ui.job)} · fresh ChatGPT inference</span></div>`:''}`;
  }
  function projectSummary(p){
    const x=p.operation_summary||{
    }
    ;
    const ranked=arr(x.cases).filter(c=>!closed(c)).sort((a,b)=>(b.priority||0)-(a.priority||0));
    return {
      count:x.open_count??ranked.length,priority:x.top_priority??ranked[0]?.priority??0,title:x.top_title||ranked[0]?.title||p.current_phase_titles?.join(' · ')||p.phase,why:ranked[0]?.why||'',pending:x.pending_inquiry_count||0
    }
    ;
  }
  function readinessLabel(r) {
    if(!r || r.total_count == null)return 'Readiness not assessed';
    return `${r.accepted_count ?? 0}/${r.total_count} checks accepted`;
  }
  function projectGeography(p) {
    return p.geography || p.resource_summary?.geography || p.resources?.geography || {};
  }
  function projectReadiness(p) {
    return p.readiness || p.resource_summary?.readiness || p.resources?.readiness;
  }
  function mapPoint(geo) {
    if(geo.lat==null||geo.lng==null||!Number.isFinite(Number(geo.lat))||!Number.isFinite(Number(geo.lng)))return null;
    // Albers equal-area projection aligned to the bundled US outline. Locations
    // are city-level reference coordinates, not surveyed project boundaries.
    const raw = (lat,lng) => {
      const rad = Math.PI / 180;
      const n = (Math.sin(29.5*rad)+Math.sin(45.5*rad))/2;
      const c = Math.cos(29.5*rad)**2 + 2*n*Math.sin(29.5*rad);
      const rho = Math.sqrt(c-2*n*Math.sin(lat*rad))/n;
      const theta = n*(lng+96)*rad;
      return [rho*Math.sin(theta),rho*Math.cos(theta)];
    };
    const a=raw(42.746,-73.264),b=raw(42.05,-73.508),v=raw(Number(geo.lat),Number(geo.lng));
    const scale=((b[0]-a[0])*(-.3)+(b[1]-a[1])*8.5)/((b[0]-a[0])**2+(b[1]-a[1])**2);
    return [530+(v[0]-a[0])*scale,92.4+(v[1]-a[1])*scale];
  }
  function regionalMap(projects) {
    const regional=ui.mapRegion==='MA';
    const positioned=projects.map(p=>({p,geo:projectGeography(p),point:mapPoint(projectGeography(p))})).filter(x=>x.point);
    return `<div class="regional-map"><svg class="portfolio-map" viewBox="${regional?'518 73 62 43':'0 0 600 340'}" aria-label="${regional?'Massachusetts':'United States'} project locations"><image href="/map.svg" x="0" y="0" width="600" height="340"/>${regional?'<text class="map-area-label" x="522" y="80">MASSACHUSETTS</text><text class="map-water-label" x="565" y="109">ATLANTIC</text>':''}${positioned.map(({p,geo,point},i)=>{
      const sum=projectSummary(p),color=sum.priority>=90?'urgent':sum.priority>=70?'attention':'tracking';
      return `<g class="site-marker ${color}" role="button" tabindex="0" data-action="project" data-id="${esc(p.id)}" aria-label="Open ${esc(p.name)}, ${esc(priority(sum.priority))}"><title>${esc(p.name)} · ${esc(geo.city||p.site)} · ${esc(sum.title)}</title><circle class="marker-halo" cx="${point[0]}" cy="${point[1]}" r="${regional?1.5:4.5}"/><circle class="marker-core" cx="${point[0]}" cy="${point[1]}" r="${regional?.75:2.3}"/>${regional?`<text class="marker-label" text-anchor="${geo.city==='Lowell'?'end':'start'}" x="${point[0]+(geo.city==='Lowell'?-1.8:1.8)}" y="${point[1]-.9}">${esc(geo.city||p.name)}</text><text class="marker-index" x="${point[0]}" y="${point[1]+.28}">${i+1}</text>`:''}</g>`;
    }).join('')}</svg>${!positioned.length?'<div class="map-unavailable">Project coordinates have not been recorded. Choose a site from the list.</div>':''}</div><div class="map-caption"><span><i class="priority-dot hot"></i> Urgent <i class="priority-dot amber"></i> High <i class="priority-dot green"></i> Other</span><span>City-level locations · click a dot to open its project</span></div>`;
  }
  function portfolio(){
    const all=arr(ui.data.projects).slice().sort((a,b)=>projectSummary(b).priority-projectSummary(a).priority);
    const matches=p=>ui.portfolioFilter==='all'||(ui.portfolioFilter==='urgent'?projectSummary(p).priority>=90:ui.portfolioFilter==='high'?projectSummary(p).priority>=70&&projectSummary(p).priority<90:projectSummary(p).priority<70);
    const projects=all.filter(matches);
    const count=all.reduce((n,p)=>n+projectSummary(p).count,0);
    const waiting=all.filter(p=>(projectReadiness(p)?.waiting_count||0)>0).length;
    const filters=[['all','All sites'],['urgent','Urgent'],['high','High priority'],['other','Other']];
    return `${heading('Where do you need to intervene?','Priority, readiness and the next decision across your active projects.',pill(`${all.length} active sites`),'DEPLOYMENT PORTFOLIO')}<div class="portfolio-metrics"><div><strong>${all.length}</strong><span>sites in delivery</span></div><div><strong>${count}</strong><span>open decision cases</span></div><div><strong>${all.reduce((n,p)=>n+projectSummary(p).pending,0)}</strong><span>vendor replies pending</span></div><div><strong>${waiting}</strong><span>sites with open readiness checks</span></div></div><div class="portfolio-grid fill"><section class="panel map-panel">${panelHead(ui.mapRegion==='MA'?'Massachusetts sites':'United States',`<div class="segmented">${[['US','US overview'],['MA','Regional detail']].map(([id,label])=>`<button data-action="map-region" data-id="${id}" class="${ui.mapRegion===id?'active':''}">${label}</button>`).join('')}</div>`)}${regionalMap(projects)}</section><section class="panel priority-sites">${panelHead('Sites by priority',pill(`${projects.length} shown`))}<div class="portfolio-filters segmented">${filters.map(([id,label])=>`<button data-action="portfolio-filter" data-id="${id}" class="${ui.portfolioFilter===id?'active':''}">${label}</button>`).join('')}</div><div class="panel-scroll">${projects.map((p,i)=>{
      const sum=projectSummary(p),r=projectReadiness(p);
      return `<button class="project-row" data-action="project" data-id="${esc(p.id)}"><div class="row-top"><span class="project-index">${String(i+1).padStart(2,'0')}</span>${pill(priority(sum.priority))}</div><h2>${esc(p.name)}</h2><p class="muted small">${esc(String(p.site).split(' · ')[0])} · ${p.system?.power_kw??'—'} kW</p><p class="project-reason">${esc(sum.title)}</p><div class="project-readiness"><span>${esc(readinessLabel(r))}</span>${r?.total_count?`<span class="readiness-meter"><i style="width:${Math.max(0,Math.min(100,100*(r.accepted_count||0)/r.total_count))}%"></i></span>`:''}</div><div class="row-meta"><span>${sum.count} open cases · ${p.metrics?.active_bottlenecks??0} blockers</span><span class="open-site">Open site ${icon('arrow')}</span></div></button>`;
    }).join('')||empty('No sites match this priority','Choose another priority to see the current portfolio.')}</div></section></div>`;
  }
  function finance(){
    return ui.data.dashboard?.finance||{
    }
    ;
  }
  function budgetTiles(){
    const f=finance();
    return `<div class="budget-tiles">${[['Budget',f.baseline_total,'Signed baseline'],['Committed',f.committed_total,'Authorized exposure'],['Actual expense',f.actual_total,`Posted as of ${dt(f.actual_as_of)}`],['Pending changes',f.proposed_change,'Awaiting a decision']].map(([label,value,note])=>`<button data-action="nav" data-id="budget" class="budget-tile"><span>${label}</span><strong>${esc(money(value))}</strong><small>${esc(note)}</small></button>`).join('')}</div>`;
  }
  function phasesRibbon(){
    return `<div class="phase-ribbon" aria-label="Post-signing project phases">${arr(ui.data.phases?.phases).map((p,i)=>`<button data-action="phase" data-id="${esc(p.id)}" class="phase-step ${esc(p.status)}" title="${esc(p.title)}: ${esc(p.status_reason)}"><span>${p.status==='completed'?'✓':String(i+1).padStart(2,'0')}</span><strong>${esc(p.title.replace(' · entry','').replace(' & ',' / '))}</strong><small>${esc(human(p.status))}</small></button>`).join('')}</div>`;
  }
  function caseRow(c,i,compact=false){
    if(c.contractor_request)return `<button class="case-row ${compact?'compact':''}" data-action="message" data-id="${esc(c.message_id)}"><span class="rank">${i+1}</span><div class="case-copy"><div class="row-top"><h3>${esc(c.title||c.task_title||'Contractor request')}</h3>${pill(priority(c.priority))}</div><p class="clamp2">${esc(c.message?.text||c.message?.raw_text||c.review_reason||'A contractor submitted a request that needs scope and impact review.')}</p><div class="row-meta"><span class="contractor-report-type">${esc(human(c.type||'Contractor report'))}</span><span>${esc(displayName(c.actor_name||personName(c.actor_id)))}</span><span>Review original →</span></div></div></button>`;
    const p=c.current_proposal;
    return `<button class="case-row ${compact?'compact':''}" data-action="case" data-id="${esc(c.id)}"><span class="rank">${i+1}</span><div class="case-copy"><div class="row-top"><h3>${esc(c.title)}</h3>${pill(priority(c.priority))}</div><p class="clamp2">${esc(c.why||c.request)}</p><div class="row-meta"><span>${esc(human(c.status))}</span><span>${p?money(p.cost_delta):arr(c.options).filter(x=>x.status==='available'||x.quote_id).length+' vendor offers'}</span><span class="action-text">Review decision →</span></div></div></button>`;
  }
  function engineRow(b,i){
    return `<button class="case-row compact" data-action="constraint" data-id="${esc(b.id)}"><span class="rank subdued">${i+1}</span><div class="case-copy"><div class="row-top"><h3>${esc(b.title)}</h3>${pill(b.priority_label)}</div><p class="clamp2">${esc(b.detail||b.next_step)}</p><div class="row-meta"><span>${esc(personName(b.resolver_id))}</span><span>Review next action →</span></div></div></button>`;
  }
  function calendarRows(){
    if(Array.isArray(ui.data?.workspace?.calendar))return ui.data.workspace.calendar.map(e=>({
      ...e,detail:e.confirmation||e.detail,status:e.kind==='response_deadline'?'deadline':e.status
    }
    ));
    if(Array.isArray(ops().calendar))return ops().calendar;
    const rows=[];
    for(const t of arr(state().tasks)){
      if(t.status==='completed'||!t.planned_start)continue;
      const b=arr(state().bookings).filter(x=>x.task_id===t.id&&!['superseded','cancelled'].includes(x.status));
      rows.push({
        id:'task:'+t.id,title:t.title,start:t.planned_start,status:b.length&&b.every(x=>x.status==='confirmed')?'confirmed':'planned',owner_id:t.owner_id,task_id:t.id,detail:t.description
      }
      );
    }
    for(const r of arr(state().requests)){
      if(r.due_at&&['pending','sent','open','acknowledged'].includes(r.status))rows.push({
        id:'request:'+r.id,title:r.request||r.purpose||'Response due',start:r.due_at,status:'deadline',owner_id:r.recipient_id,detail:'Response deadline; not a confirmed appointment.'
      }
      );
    }
    for(const c of cases()){
      for(const o of arr(c.options)){
        if(o.earliest_start&&o.quote_id)rows.push({
          id:'offer:'+o.quote_id,title:`${o.vendor_name}: ${c.title}`,start:o.earliest_start,status:o.status==='expired'?'expired':'offered',case_id:c.id,detail:'Vendor availability offer; not a booking.'
        }
        );
      }
      for(const b of arr(ops().bookings).filter(x=>x.case_id===c.id))rows.push({
        id:'booking:'+b.id,title:b.title||`${c.title} · vendor work`,start:b.start||b.planned_start,status:b.status||'awaiting_confirmation',case_id:c.id,detail:'Accepted plan and counterpart confirmation are separate.'
      }
      );
    }
    return rows.sort((a,b)=>String(a.start).localeCompare(String(b.start)));
  }
  function upcomingRows(){
    const now=new Date(project().now),today=dayKey(project().now),weekday=new Intl.DateTimeFormat('en-US',{
      weekday:'short',timeZone:timezone()
    }
    ).format(now),daysToEnd=7-['Mon','Tue','Wed','Thu','Fri','Sat','Sun'].indexOf(weekday),end=new Date(now.getTime()+daysToEnd*86400000);
    return calendarRows().filter(e=>dayKey(e.start||e.at)>=today&&new Date(e.start||e.at)<end&&!['completed','cancelled','expired','superseded'].includes(e.status));
  }
  function timeRow(e){
    return `<button class="time-row" data-action="calendar-event" data-id="${esc(e.id)}"><span class="time-chip"><strong>${esc(dt(e.start||e.at))}</strong><small>${esc(dt(e.start||e.at,true).split(', ').slice(1).join(', '))}</small></span><span class="time-copy"><strong>${esc(e.title)}</strong><small>${esc(human(e.status))}${e.owner_id?' · '+esc(personName(e.owner_id)):e.owner?' · '+esc(person(e.owner)?.name||vendors().find(v=>v.id===e.owner)?.name||e.owner):''}</small></span>${icon('chevron')}</button>`;
  }
  function messageSummary(m){
    return m.summary?.text||m.reading_summary?.text||(typeof m.reading_summary==='string'?m.reading_summary:null);
  }
  function messageRow(m){
    return `<button class="message-row ${ui.messageId===m.id?'selected':''}" data-action="message" data-id="${esc(m.id)}"><span class="sender-avatar">${esc((m.sender_name||personName(m.issuer_id||m.sender_id)).slice(0,1))}</span><span class="message-copy"><span class="row-top"><strong>${esc(displayName(m.sender_name||personName(m.issuer_id||m.sender_id)))}</strong><small>${esc(dt(m.received_at))}</small></span><b>${esc(m.subject||'Stakeholder update')}</b><small class="clamp2">${esc(messageSummary(m)||m.text||m.raw_text)}</small></span></button>`;
  }
  function site(){
    const p=project(),cs=[...cases().filter(c=>!closed(c)),...contractorRequests().map(r=>({...r,contractor_request:true}))].sort((a,b)=>(b.priority||0)-(a.priority||0)),bs=arr(ui.data.dashboard?.bottlenecks).filter(b=>b.status!=='upcoming');
    const selected=ui.tab==='constraints';
    const rows=selected?bs:cs;
    const key=selected?'constraints':'sitecases';
    const cal=upcomingRows().slice(0,2);
    return `${crumb()}${heading(p.name,`${String(p.site||p.location||'').split(' · ')[0]} · ${p.system?.power_kw??'—'} kW / ${p.system?.capacity_kwh??'—'} kWh · Target ${dt(p.target_handoff||p.target_date)}`,btn('Project details','nav','details','quiet'))}${budgetTiles()}${phasesRibbon()}${siteResourceLinks()}<div class="site-grid fill"><section class="panel decision-queue">${panelHead('Your priority queue',pill(`${cs.length} open cases`))}<div class="tabs compact-tabs"><button data-action="queue-tab" data-id="cases" class="${!selected?'active':''}">Decisions & follow-ups <span>${cs.length}</span></button><button data-action="queue-tab" data-id="constraints" class="${selected?'active':''}">Project bottlenecks <span>${bs.length}</span></button></div><div class="panel-scroll">${pageRows(rows,key,3).map((c,i)=>selected?engineRow(c,(ui.pages[key]||0)*3+i):caseRow(c,(ui.pages[key]||0)*3+i,true)).join('')||empty('No open decision cases','Project prerequisites and confirmations remain visible in the bottlenecks tab.')}</div>${pager(key,rows.length,3)}</section><div class="site-side"><section class="panel">${panelHead('Today & this week',link('Calendar','calendar'))}<div class="mini-scroll">${cal.map(timeRow).join('')||empty('No upcoming checkpoints','Open the calendar to view the whole project.')}</div></section><section class="panel">${panelHead('Latest stakeholder updates',link('Inbox','inbox'))}<div class="mini-scroll">${messages().slice(0,2).map(messageRow).join('')||empty('No reports received','Add a field update in the inbox.')}</div></section></div></div>`;
  }
  function siteResourceLinks() {
    const r=resources(),m=r.metrics||{};
    return `<nav class="site-resource-links" aria-label="Project delivery details"><button data-action="nav" data-id="subcontractors">${icon('vendor')}<span><strong>Subcontractors</strong><small>${m.subcontractor_count??arr(r.subcontracts).length} project partners</small></span>${icon('chevron')}</button><button data-action="nav" data-id="procurement">${icon('paper')}<span><strong>Procurement</strong><small>Delivery ${dt(r.procurement?.delivery?.eta)}</small></span>${icon('chevron')}</button><button data-action="nav" data-id="readiness">${icon('check')}<span><strong>Readiness</strong><small>${esc(readinessLabel(r.readiness))}</small></span>${icon('chevron')}</button></nav>`;
  }
  function evidenceButtons(ids) {
    return arr(ids).map(id=>btn(id,'evidence-record',id,'quiet small-button')).join('');
  }
  function subcontractors() {
    const r=resources(),teams=arr(r.subcontracts),selected=teams.find(x=>x.id===ui.subcontractId)||teams[0];
    return `${crumb('Subcontractors')}${heading('Subcontractors & work packages','External delivery partners assigned to this project. Availability offers remain separate from bookings.',btn('Back to site','nav','site','quiet'))}<div class="tabs resource-tabs"><button data-action="resource-tab" data-id="teams" class="${ui.resourceTab==='teams'?'active':''}">Partners & scope</button><button data-action="resource-tab" data-id="schedule" class="${ui.resourceTab==='schedule'?'active':''}">Booking calendar</button></div>${ui.resourceTab==='schedule'?subcontractCalendar():`<div class="resource-grid fill"><section class="panel">${panelHead('Project partners',pill(`${teams.length} partners`))}<div class="panel-scroll">${pageRows(teams,'subcontractors',6).map(t=>`<button class="subcontract-row ${selected?.id===t.id?'selected':''}" data-action="subcontractor" data-id="${esc(t.id)}"><strong>${esc(displayName(t.organization||t.name))}</strong><span>${esc(t.role||'External subcontractor')}</span><small>${arr(t.tasks).length?`${t.completed_count??0}/${t.task_count??arr(t.tasks).length} work packages completed`:'Availability offer only · no assignment'}</small>${pill(t.status)}</button>`).join('')||empty('No subcontractors recorded','Record a responsible external partner before confirming delivery work.')}</div>${pager('subcontractors',teams.length,6)}</section><section class="panel"><div class="panel-scroll panel-body">${selected?subcontractDetail(selected):empty('Select a project partner')}</div></section></div>`}`;
  }
  function subcontractDetail(t) {
    const offers=arr(t.offers),tasks=arr(t.tasks);
    return `<div class="row-top"><div><span class="eyebrow">PROJECT SUBCONTRACTOR</span><h2>${esc(displayName(t.organization||t.name))}</h2><p class="muted small">${esc(displayName(t.name))} · ${esc(t.role)}</p></div>${pill(t.status)}</div><h3 class="section-title">Assigned scope & bookings</h3>${tasks.map(task=>`<article class="work-package"><div class="row-top"><strong>${esc(task.title)}</strong>${pill(task.status)}</div><p>${esc(dt(task.start,true))} → ${esc(dt(task.end,true))}</p><div class="small muted">${esc(task.duration_hours??'—')} hours · ${esc(task.confirmation||'Booking confirmation not recorded')}</div>${arr(task.required_gates).length?`<div class="gate-chips">${arr(task.required_gates).map(g=>pill(`${g.label||human(g.id)}: ${g.status||'not recorded'}`)).join('')}</div>`:''}${arr(task.evidence_ids).length?`<details class="technical-detail"><summary>Source evidence</summary>${evidenceButtons(task.evidence_ids)}</details>`:''}</article>`).join('')||'<p class="muted">No committed work package for this partner.</p>'}${offers.length?`<h3 class="section-title">Availability offers · not booked</h3>${offers.map(o=>`<article class="work-package offered"><div class="row-top"><strong>${esc(dt(o.earliest_start,true))}</strong>${pill(o.status||'offered')}</div><p>${money(o.total_price)} · ${esc(o.duration_hours??'—')} hours</p><small>Valid until ${esc(dt(o.expires_at,true))}. Scope and PM approval still apply.</small>${!o.eligible?`<p class="excluded">Not currently eligible: ${esc(arr(o.exclusion_reasons).join(' · ')||'Revalidation is required.')}</p>`:''}${o.case_id?btn('Review linked decision','case',o.case_id,'quiet small-button'):''}</article>`).join('')}`:''}${t.performance?`<h3 class="section-title">Recorded performance</h3><p class="small">${esc(performance(t.performance))}</p>`:''}${t.qualifications?`<details class="technical-detail"><summary>Qualifications and cost allocation</summary><p>${esc(readable(t.qualifications))}</p>${resourceCosts(t.cost_lines)}</details>`:''}`;
  }
  function addDay(date,amount) {
    const value=new Date(`${date}T12:00:00Z`);value.setUTCDate(value.getUTCDate()+amount);return value.toISOString().slice(0,10);
  }
  function resourceCalendarRows() {
    return arr(resources().calendar).map(e=>({...e,detail:e.confirmation||e.detail}));
  }
  function subcontractCalendar() {
    const records=resourceCalendarRows(),teams=arr(resources().subcontracts);
    const now=dayKey(project().now),start=addDay(now,ui.weekOffset*7),days=Array.from({length:7},(_,i)=>addDay(start,i));
    const rows=teams.filter(t=>records.some(e=>e.owner_id===t.owner_id||e.owner_id===t.id));
    return `<section class="panel fill subcontract-calendar">${panelHead(`${dt(days[0])} – ${dt(days[6])}`,`<div class="week-actions">${btn('←','week','-1','quiet small-button')}${btn('Project week','week','reset','quiet small-button')}${btn('→','week','1','quiet small-button')}</div>`)}<div class="calendar-legend resource-legend">${['confirmed','planned','offered','completed'].map(x=>pill(x)).join('')}<span>Project timezone: ${esc(timezone())}. This view does not imply availability on other projects.</span></div><div class="panel-scroll"><div class="subcontract-gantt"><div class="gantt-heading">External partner</div>${days.map(d=>`<div class="gantt-heading ${d===now?'today':''}">${esc(new Intl.DateTimeFormat('en-US',{weekday:'short',timeZone:'UTC'}).format(new Date(d+'T12:00:00Z')))}<strong>${esc(dt(d))}</strong></div>`).join('')}${rows.map(t=>`<div class="gantt-owner"><strong>${esc(displayName(t.organization||t.name))}</strong><small>${esc(t.role)}</small></div>${days.map(d=>{const entries=records.filter(e=>(e.owner_id===t.owner_id||e.owner_id===t.id)&&dayKey(e.start)<=d&&dayKey(e.end||e.start)>=d);return `<div class="gantt-day ${d===now?'today':''}">${entries.map(e=>`<button class="booking-chip ${esc(tone(e.status))}" data-action="resource-event" data-id="${esc(e.id)}"><strong>${esc(e.title)}</strong><small>${esc(human(e.status))}</small></button>`).join('')}</div>`;}).join('')}`).join('')}</div>${!rows.length?empty('No subcontractor work windows recorded','Assigned packages and scoped availability offers appear here when recorded.'):''}</div><div class="panel-bottom"><span class="fineprint">An empty day means no booking is recorded here, not that the subcontractor is available.</span>${btn('All project checkpoints','nav','calendar','quiet small-button')}</div></section>`;
  }
  function resourceCosts(lines) {
    return arr(lines).length?`<table class="compare-table"><thead><tr><th>Allocation</th><th>Baseline</th><th>Committed</th><th>Actual</th></tr></thead><tbody>${arr(lines).map(l=>`<tr><th>${esc(l.label||l.category||l.id)}${l.allocation?`<small>${esc(l.allocation==='shared'?'Shared allocation · not a separate payable amount':'Exclusively attributed allocation')}</small>`:''}</th><td>${money(l.baseline)}</td><td>${money(l.committed)}</td><td>${money(l.actual)}</td></tr>`).join('')}</tbody></table>`:'';
  }
  function procurement() {
    const p=resources().procurement||{},d=p.delivery||{},o=p.order||{},sh=p.shutdown||{};
    return `${crumb('Procurement')}${heading('Procurement & site access','Track equipment, physical receipt and the customer window alongside the current plan.',btn('Back to site','nav','site','quiet'))}<div class="procurement-grid fill"><section class="panel"><div class="panel-scroll panel-body"><span class="eyebrow">EQUIPMENT & DELIVERY</span><h2>${esc(p.system?.power_kw??project().system?.power_kw??'—')} kW / ${esc(p.system?.capacity_kwh??project().system?.capacity_kwh??'—')} kWh system</h2><div class="pair"><span>Equipment order</span>${pill(o.status)}</div><div class="pair"><span>Latest delivery estimate</span><strong>${esc(dt(d.eta,true))}</strong></div><div class="pair"><span>Physical receipt</span>${pill(d.receipt_status)}</div><div class="pair"><span>Planned unloading</span><strong>${esc(dt(d.unload_start,true))}</strong></div>${d.detail?`<div class="reason-box ${d.conflict?'delivery-conflict':''}"><span class="eyebrow">${d.conflict?'SCHEDULE CONFLICT':'DELIVERY CONTEXT'}</span><p>${esc(d.detail)}</p></div>`:''}<h3 class="section-title">Source records</h3>${evidenceButtons([...arr(o.evidence_ids),...arr(d.eta_evidence_ids),...arr(d.receipt_evidence_ids)])||'<p class="muted small">No order or physical-receipt record linked.</p>'}<h3 class="section-title">Information still needed</h3><ul class="body-list">${arr(p.unknowns).map(x=>`<li>${esc(readable(x))}</li>`).join('')||'<li>No additional procurement unknowns are listed.</li>'}</ul></div></section><section class="panel"><div class="panel-scroll panel-body"><span class="eyebrow">CUSTOMER ACCESS</span><h2>Shutdown & work windows</h2><div class="pair"><span>Customer authorization</span>${pill(sh.status)}</div><div class="pair"><span>Planned tie-in</span><strong>${esc(dt(sh.planned_start,true))}</strong></div>${sh.detail?`<p class="fineprint">${esc(sh.detail)}</p>`:''}${arr(sh.windows).map(w=>`<div class="work-package"><strong>${esc(dt(w.start,true))} – ${esc(dt(w.end,true))}</strong><p class="small muted">${esc(w.status||'Recorded window; confirm scope and authority before use.')}</p></div>`).join('')||'<p class="muted">No customer work window is recorded.</p>'}${evidenceButtons(sh.evidence_ids)}<h3 class="section-title">Related cost allocations</h3>${resourceCosts(p.cost_lines)||'<p class="muted">No procurement cost allocation is recorded.</p>'}${btn('Full budget & expenses','nav','budget','quiet small-button')}</div></section></div>`;
  }
  function readiness() {
    const r=resources().readiness||{},checks=arr(r.checks);
    return `${crumb('Readiness')}${heading('Project readiness',readinessLabel(r)+' · evidence-backed prerequisites, not a dispatch authorization.',btn('Back to site','nav','site','quiet'))}<div class="readiness-overview"><div><strong>${r.accepted_count??0}</strong><span>accepted checks</span></div><div><strong>${r.waiting_count??0}</strong><span>checks still open</span></div><p>Next milestone: <strong class="milestone-name">${esc(r.next_milestone?.label||'Not recorded')}</strong> · ${esc(dt(r.next_milestone?.planned_start))}. Later-stage checks can remain open without blocking the current stage.</p></div><section class="panel fill">${panelHead('Readiness checks',btn('Project evidence','nav','evidence','quiet small-button'))}<div class="panel-scroll"><div class="readiness-check-grid">${checks.map(c=>`<article class="readiness-check"><span class="eyebrow">${esc(human(c.stage||'Project'))}</span><div class="row-top"><h3>${esc(c.label)}</h3>${pill(c.status,c.status==='accepted'?'green':c.status==='waiting'?'amber':'')}</div><p>${esc(c.detail||c.criteria)}</p>${c.criteria&&c.criteria!==c.detail?`<small class="muted">Required: ${esc(c.criteria)}</small>`:''}<div class="readiness-owner">${icon('vendor')} ${esc(personName(c.owner_id))}</div>${arr(c.task_ids).length?`<small class="muted">${esc(arr(c.task_ids).map(taskName).join(' · '))}</small>`:''}${arr(c.evidence_ids).length?`<details class="technical-detail"><summary>Acceptance evidence</summary>${evidenceButtons(c.evidence_ids)}</details>`:''}</article>`).join('')||empty('Readiness has not been assessed','Project evidence and acceptance gates will populate this view.')}</div></div></section>`;
  }
  function source(m,full=false){
    if(!m)return empty('No original message linked','This case may be derived from project evidence.');
    const attachments=arr(m.attachments),summary=messageSummary(m),request=arr(ui.data?.workspace?.contractor_requests).find(r=>r.message_id===m.id);
    return `<div class="source-head"><span class="sender-avatar">${esc((m.sender_name||personName(m.issuer_id)).slice(0,1))}</span><div><strong>${esc(displayName(m.sender_name||personName(m.issuer_id||m.sender_id)))}</strong><small>${esc(person(m.issuer_id||m.sender_id)?.role||m.sender_role||'Stakeholder')} · ${esc(dt(m.received_at,true))}</small></div>${pill('Original')}</div><h3 class="source-subject">${esc(m.subject||'Stakeholder report')}</h3>${request?`<div class="contractor-status">${pill(request.status)}<span>${esc(request.task_title||taskName(request.task_id))}</span><small>Contractor submission · changes require review and authorized scope.</small></div>`:''}<blockquote class="source-text ${full?'':'short'}">${esc(m.text||m.raw_text||'')}</blockquote>${attachments.length?`<div class="attachments">${attachments.map(a=>`<button class="attachment" data-action="attachment" data-id="${esc(a.id)}"><img src="/api/attachments/${encodeURIComponent(a.id)}${project().demo_project_id?'?project_id='+encodeURIComponent(project().demo_project_id):''}" alt="${esc(a.name||a.filename||'Stakeholder attachment')}" loading="lazy"><span>${esc(a.name||a.filename||'Field image')}</span></button>`).join('')}</div>`:''}<div class="summary-box"><div class="row-top"><strong>${icon('spark')} PM reading summary</strong>${summary?pill('Live LLM','teal'):''}</div>${summary?`<p>${esc(summary)}</p>${arr(m.summary?.uncertainties||m.reading_summary?.uncertainties).length?`<p class="small muted">Uncertain: ${esc(arr(m.summary?.uncertainties||m.reading_summary?.uncertainties).join(' · '))}</p>`:''}`:'<p class="muted">A reading summary has not been generated for this report.</p>'}<div class="summary-actions">${btn(summary?'Refresh with ChatGPT':'Summarize & triage with ChatGPT','summarize',m.id,'quiet small-button',!(ui.data.runtime?.available&&ui.data.runtime?.authenticated))}</div></div>${full?`<p class="fineprint">Original text and attachments are preserved. Summary text helps you read; reported claims and validated project evidence remain separate.</p>`:`<button class="text-link" data-action="message" data-id="${esc(m.id)}">Read full report in inbox →</button>`}`;
  }
  function caseTabs(){
    return `<div class="tabs"><button class="${ui.tab==='change'?'active':''}" data-action="case-tab" data-id="change">Proposed change</button><button class="${ui.tab==='vendors'?'active':''}" data-action="case-tab" data-id="vendors">Vendor options</button><button class="${ui.tab==='people'?'active':''}" data-action="case-tab" data-id="people">People & authority</button><button class="${ui.tab==='evidence'?'active':''}" data-action="case-tab" data-id="evidence">Evidence</button></div>`;
  }
  function decision(){
    const c=selectedCase();
    if(!c)return `${crumb('Decision')}${empty('This case is no longer in this project','Return to the site to see current cases.')}${btn('Back to site','nav','site')}`;
    const p=c.current_proposal,linked=messages().filter(m=>arr(c.source_message_ids).includes(m.id)||m.case_id===c.id);
    const content=ui.tab==='vendors'?vendorOptions(c):ui.tab==='people'?casePeople(c):ui.tab==='evidence'?caseEvidence(c):caseChange(c);
    const pending=p&&['draft','proposed','pending','pending_approval','awaiting_approval'].includes(p.status);
    const over=p&&p.required_approver_id&&p.required_approver_id!=='pm';
    return `${crumb('Decision')}${heading(c.title,c.why,`${pill(priority(c.priority))}${pill(c.status)}`)}<div class="decision-grid fill"><section class="panel source-panel">${panelHead('What triggered this',linked.length>1?pill(`${linked.length} linked reports`):'')}<div class="panel-scroll panel-body">${source(linked.find(m=>m.id===ui.messageId)||linked.find(m=>m.id===arr(c.source_message_ids)[0])||linked[0])}${linked.length>1?`<div class="linked-reports">${linked.map(m=>btn(m.subject||dt(m.received_at),'case-message',m.id,'quiet small-button')).join('')}</div>`:''}</div></section><section class="panel decision-detail">${caseTabs()}<div class="panel-scroll panel-body">${content}</div></section></div><div class="actionbar"><div class="actionbar-note">${p?`<strong>${pending?'Review exact scope, cost and dates':esc(human(p.status))}</strong><small>${over&&!['approved','committed'].includes(p.status)?`Approval belongs to ${esc(personName(p.required_approver_id))}; PM authority is insufficient.`:'Approval updates the internal plan. Vendor booking and institutional acceptance remain separate.'}</small>`:'<strong>Compare available, qualified vendors</strong><small>An availability inquiry does not book work.</small>'}</div><div class="actionbar-buttons">${btn('Request clarification','clarify',c.id,'quiet')}${pending?`${over?'':btn('Reject option','reject',c.id,'quiet')}${over?btn(c.status==='awaiting_approval'?'Commercial approval requested':'Request commercial approval','request-approval',c.id,'primary',c.status==='awaiting_approval'):btn(`Approve change · ${money(p.cost_delta)}`,'approve',c.id,'primary')}`:p?.status==='approved'?btn('Commit authorized change','commit-approved',c.id,'primary'):!p?btn('Compare vendor options','case-tab','vendors','primary'):btn('Review vendor options','case-tab','vendors','quiet')}</div></div>`;
  }
  function caseChange(c){
    const p=c.current_proposal,bookings=arr(ops().bookings).filter(b=>b.case_id===c.id&&b.status!=='superseded');
    if(!p)return `<h3>Requested help</h3><p class="scope-copy">${esc(c.request)}</p><div class="reason-box"><span class="eyebrow">WHY THIS ACTION</span><p>${esc(c.why)}</p></div><div class="empty bordered"><h3>No exact change package yet</h3><p>Choose an eligible vendor offer to prepare a cost and schedule comparison for approval.</p>${btn('Compare vendor options','case-tab','vendors','primary')}</div>`;
    const committed=p.status==='committed';
    const table=`<table class="compare-table"><thead><tr><th>What changes</th><th>Before change</th><th>${committed?'Approved plan':'Proposed plan'}</th></tr></thead><tbody><tr><th>Committed cost</th><td>${money(p.budget_before)}</td><td><strong>${money(p.budget_after)}</strong><small>+${money(p.cost_delta)} incremental</small></td></tr>${arr(p.schedule_changes).map(r=>`<tr><th>${esc(r.title||taskName(r.task_id))}</th><td>${esc(dt(r.before,true))}</td><td><strong>${esc(dt(r.after,true))}</strong>${r.before_resource!==r.after_resource?`<small>Resource: ${esc(vendors().find(v=>'vendor:'+v.id===r.after_resource)?.name||human(r.after_resource))}</small>`:''}</td></tr>`).join('')}${p.work_package?`<tr><th>Additional vendor work</th><td>Not in original scope</td><td><strong>${esc(dt(p.work_package.start||p.work_package.planned_start,true))}</strong><small>${esc(p.work_package.duration_hours??'—')} h · ${esc(vendors().find(v=>v.id===p.vendor_id)?.name||p.vendor_id)}</small></td></tr>`:''}</tbody></table>`;
    return `<div class="proposal-meta compact-meta">${pill(p.status)}<strong>${esc(vendors().find(v=>v.id===p.vendor_id)?.name||p.vendor_id)}</strong><span>${esc(p.id)}</span></div>${p.stale_reason?`<div class="notice error">${esc(p.stale_reason)}</div>`:''}${p.required_approver_id==='commercial'&&p.status==='pending'?`<div class="demo-response"><div><strong>Commercial response preview</strong><small>Load a sample response from ${esc(personName('commercial'))}; PM authority stays unchanged.</small></div><div>${btn('Load approval response','commercial-approve',c.id,'quiet small-button')}${btn('Load rejection response','commercial-reject',c.id,'quiet small-button')}</div></div>`:''}${committed&&bookings.length?`<div class="approved-summary"><strong>${money(p.cost_delta)} change authorized</strong><small>${bookings.filter(b=>b.status!=='confirmed').length} counterpart confirmations still required</small></div>${bookings.map(b=>`<div class="booking-row"><div><strong>${esc(vendors().find(v=>v.id===(b.vendor_id||b.recipient_id))?.name||personName(b.recipient_id))}</strong><p>${esc(taskName(b.task_id))}<br>${esc(dt(b.start||b.planned_start,true))} · ${esc(human(b.status))}</p></div>${b.status!=='confirmed'?btn('Load confirmation','confirm-booking',b.id,'quiet small-button'):pill('Confirmed')}</div>`).join('')}<details class="technical-detail"><summary>View authorized cost and schedule comparison</summary>${table}</details>`:table}<details class="technical-detail"><summary>Scope, execution conditions and remaining approvals</summary><h3 class="section-title">Exact scope</h3><p class="scope-copy">${esc(c.request)}</p><ul class="body-list">${arr(p.conditions).map(x=>`<li>${esc(readable(x))}</li>`).join('')}</ul></details><p class="fineprint">${arr(p.conditions).filter(x=>/hold|conditional|permission/i.test(readable(x))).slice(0,1).map(readable).map(esc).join(' ')||'Proposed dates remain subject to the responsible counterparts and institutional acceptance.'}</p>`;
  }
  function performance(p){
    if(!p||!Object.keys(p).length)return 'No recorded history';
    if(p.completed_jobs!=null)return `${p.completed_jobs} completed jobs · ${p.on_time_pct??'—'}% on time · ${p.rework_jobs??'—'} rework jobs · ${p.rating??'—'}/5 from ${p.rating_count??p.reference_count??0} references`;
    return readable(p);
  }
  function vendorOptions(c){
    const offers=arr(c.options);
    const inquiries=arr(c.inquiries||ops().inquiries).filter(x=>!x.case_id||x.case_id===c.id);
    const pending=inquiries.filter(x=>['pending','sent','awaiting_reply'].includes(x.status));
    return `<div class="section-intro"><div><h3>Recommended vendors</h3><p>Qualified for ${esc(human(c.vendor_capability))}. Responses, price and timing are considered together.</p></div>${btn('Vendor directory','nav','vendors','quiet small-button')}</div><div class="outreach-strip"><div>${pill(`${pending.length} inquiries pending`,'amber')}<small>Awaiting scoped availability and pricing</small></div><div>${pending.length?btn('Load sample replies','vendor-replies',c.id,'primary small-button'):btn('Request / refresh availability','inquire',c.id,'quiet small-button')}</div></div>${offers.length?offers.map((v,i)=>`<article class="offer ${!v.eligible?'ineligible':''}"><div class="row-top"><div><span class="eyebrow">${v.eligible?'RECOMMENDATION '+(i+1):v.status==='awaiting_reply'?'AWAITING SCOPED REPLY':'NOT ELIGIBLE'}</span><h3><button class="text-link vendor-name" data-action="vendor" data-id="${esc(v.vendor_id)}">${esc(displayName(v.vendor_name))}</button></h3></div>${pill(v.status)}</div><div class="offer-metrics"><div><small>Earliest availability</small><strong>${esc(dt(v.earliest_start,true))}</strong></div><div><small>Quote total</small><strong>${money(v.total_price)}</strong></div><div><small>Work duration</small><strong>${v.duration_hours!=null?esc(v.duration_hours)+' h':'Awaiting reply'}</strong></div></div><p class="small"><strong>Performance:</strong> ${esc(performance(v.performance))}</p><p class="small muted">${esc(arr(v.ranking_reasons).map(readable).join(' · '))}</p>${arr(v.exclusion_reasons).length?`<p class="excluded">${esc(arr(v.exclusion_reasons).join(' · '))}</p>`:''}<div class="offer-bottom"><small>${v.expires_at?'Quote valid until '+esc(dt(v.expires_at,true)):'No valid quote yet'}</small>${btn(c.current_proposal?.vendor_id===v.vendor_id?'Prepare updated proposal':'Prepare change proposal','choose-vendor',`${c.id}|${v.vendor_id}`,'quiet small-button',!v.eligible||!v.quote_id||['pending','expired','declined','unavailable','superseded'].includes(v.status))}</div></article>`).join(''):empty('Availability inquiries are being prepared','Request availability from the matching vendor directory.')}`;
  }
  function casePeople(c){
    const p=c.current_proposal;
    return `<div class="reason-box approval-policy"><span class="eyebrow">APPROVAL POLICY</span><h3>POLICY_DEMO_01</h3><p>${esc(personName('pm'))} may approve incremental project changes up to <strong>${money(project().pm_approval_limit)}</strong>. Changes above that limit go to ${esc(personName('commercial'))}.</p>${p?`<p><strong>This proposal:</strong> ${esc(personName(p.required_approver_id))} must authorize the ${money(p.cost_delta)} change against the recorded scope and revision.</p>`:''}<small>Commercial approval does not grant engineering acceptance, a customer outage window or utility permission to operate.</small></div><h3 class="section-title">People involved</h3>${arr(c.stakeholder_ids).map(id=>{const s=person(id);return `<div class="person-row"><span class="sender-avatar">${esc(personName(id).slice(0,1))}</span><div><strong>${esc(personName(id))}</strong><p>${esc(s?.role||id)} · ${esc(displayName(s?.organization||''))}</p><small>${esc(s?.contact||'Contact not recorded')}</small></div></div>`;}).join('')}<h3 class="section-title">Institutional gates</h3>${arr(c.required_gates).map(id=>{const g=state().gates?.[id]||arr(state().gates).find(x=>x.id===id);return `<div class="pair"><span>${esc(g?.label||human(id))}</span>${pill(g?.status||'Unknown')}</div>`;}).join('')||'<p class="muted">No additional gates specified on this case. Project gates still apply.</p>'}`;
  }
  function caseEvidence(c){
    const p=c.current_proposal;
    return `<h3>Source-linked decision record</h3><p class="muted small">Reading summaries do not overwrite original messages or constitute approval.</p>${arr(c.source_message_ids).map(id=>{const m=messages().find(x=>x.id===id);return `<div class="pair"><span>${esc(m?.subject||id)}</span>${btn('Read original','message',id,'quiet small-button')}</div>`;}).join('')}<h3 class="section-title">Version and scope</h3><div class="pair"><span>Current project revision</span><strong>${esc(project().revision)}</strong></div><div class="pair"><span>Current design revision</span><strong>${esc(project().design_revision)}</strong></div>${p?`<div class="pair"><span>Proposal based on revision</span><strong>${esc(p.based_on_revision)}</strong></div>`:''}<h3 class="section-title">Affected activities</h3><ul class="body-list">${arr(c.affected_task_ids).map(id=>`<li>${esc(taskName(id))}</li>`).join('')}</ul>${btn('Full evidence library','nav','evidence','quiet')}`;
  }
  function inbox(){
    const ms=messages(),m=ms.find(x=>x.id===ui.messageId)||ms[0];
    return `${crumb('Inbox')}${heading('Site inbox','Original reports, images and source-linked reading summaries.',btn('+ Add stakeholder update','nav','compose','primary'))}<div class="inbox-grid fill"><section class="panel message-list">${panelHead('Stakeholder updates',pill(ms.length+' reports'))}<div class="panel-scroll">${pageRows(ms,'inbox',7).map(messageRow).join('')||empty('No stakeholder reports')}</div>${pager('inbox',ms.length,7)}</section><section class="panel"><div class="panel-scroll panel-body">${source(m,true)}${m?.case_id?`<div class="message-case-link">${btn('Open linked decision →','case',m.case_id,'primary')}</div>`:''}${m?.assertions?`<details class="technical-detail"><summary>Source-linked observations</summary>${arr(m.assertions).map(a=>`<div class="observation"><strong>${esc(a.claim||a.label||a.type||'Reported observation')}</strong><p>${esc(a.quote||a.source_quote||arr(a.source_quotes).join(' · ')||a.text||'')}</p><small>${esc(a.validation_status||a.status||'Reported; not independently validated')}</small></div>`).join('')}</details>`:''}</div></section></div>`;
  }
  function compose(){
    return `${crumb('New report')}${heading('Add a stakeholder update','Preserve the original field message and images, then use ChatGPT to summarize and triage it.',btn('Back to inbox','nav','inbox','quiet'))}<section class="panel compose-panel fill"><form id="message-form" class="panel-scroll panel-body"><div class="form-grid"><label>From<select name="sender_id" required>${people().map(p=>`<option value="${esc(p.id)}">${esc(p.name)} · ${esc(p.role)}</option>`).join('')}</select></label><label>Link to a current decision<select name="case_id"><option value="">New / unclassified report</option>${cases().map(c=>`<option value="${esc(c.id)}">${esc(c.title)}</option>`).join('')}</select></label></div><label>Subject<input name="subject" required maxlength="200" placeholder="Brief description of the issue"></label><label>Original message<textarea name="raw_text" required rows="7" maxlength="16000" placeholder="Paste the electrician, rigger, EPC partner or utility coordinator’s original report…"></textarea></label><label>Original images<input name="attachments" type="file" accept="image/png,image/jpeg,image/webp" multiple><small>PNG, JPEG or WebP, up to 4 MiB each. Files remain attached to the original report.</small></label><div class="form-footer"><p class="muted small">New reports are unverified observations. They do not close gates or authorize spending.</p><button class="btn primary" type="submit" ${ui.busy?'disabled':''}>Save original report</button></div></form></section>`;
  }
  function calendar(){
    const all=calendarRows(),now=new Date(project().now),today=dayKey(project().now);
    const weekEnd=new Date(now.getTime()+7*86400000);
    let rows=all.filter(e=>ui.calendarFilter==='all'||(ui.calendarFilter==='today'?dayKey(e.start||e.at)===today:ui.calendarFilter==='week'?new Date(e.start||e.at)>=now&&new Date(e.start||e.at)<=weekEnd:ui.calendarFilter==='confirmed'?e.status==='confirmed':new Date(e.start||e.at)>=now));
    return `${crumb('Calendar')}${heading('Project calendar',`${timezone()} · project clock ${dt(project().now,true)}`,btn('Back to site','nav','site','quiet'))}<div class="calendar-legend">${['confirmed','planned','offered','deadline'].map(x=>pill(x)).join('')}<span>Only counterpart-confirmed bookings are labelled confirmed.</span></div><section class="panel fill">${panelHead('Checkpoints & activity windows',`<div class="segmented">${[['today','Today'],['week','Next 7 days'],['upcoming','Upcoming'],['confirmed','Confirmed'],['all','All']].map(([k,v])=>`<button data-action="calendar-filter" data-id="${k}" class="${ui.calendarFilter===k?'active':''}">${v}</button>`).join('')}</div>`)}<div class="panel-scroll">${pageRows(rows,'calendar',7).map(timeRow).join('')||empty('No checkpoints in this view','Choose another time range to inspect planned work, offers and response deadlines.')}</div>${pager('calendar',rows.length,7)}</section>`;
  }
  function directory(){
    const vs=vendors(),caps=[...new Set(vs.flatMap(v=>arr(v.capabilities||v.activities)))].sort();
    const query=ui.vendorQuery.toLowerCase();
    const filtered=vs.filter(v=>(ui.vendorFilter==='all'||arr(v.capabilities||v.activities).includes(ui.vendorFilter))&&(!query||`${v.name} ${readable(v.capabilities)} ${v.description||''}`.toLowerCase().includes(query)));
    return `${heading('Vendor directory','Compare capability, qualifications and past performance before committing work.',btn('About these records','nav','about','quiet small-button'),'DELIVERY NETWORK')}<div class="directory-filters"><label class="search-label"><span>Search vendors</span><input id="vendor-search" type="search" value="${esc(ui.vendorQuery)}" placeholder="Search name or activity"></label><label><span>Activity</span><select id="vendor-filter"><option value="all">All activities</option>${caps.map(c=>`<option value="${esc(c)}" ${ui.vendorFilter===c?'selected':''}>${esc(human(c))}</option>`).join('')}</select></label></div><section class="panel fill"><div class="vendor-grid panel-scroll">${pageRows(filtered,'vendors',6).map(v=>`<button class="vendor-card" data-action="vendor" data-id="${esc(v.id)}"><div class="row-top"><span class="vendor-monogram">${esc((v.name||'V').split(' ').slice(0,2).map(s=>s[0]).join(''))}</span>${pill(v.status||'Profile')}</div><h3>${esc(v.name)}</h3><p>${esc(arr(v.capabilities||v.activities).map(human).join(' · '))}</p><p class="small muted clamp2">${esc(v.description||v.profile||readable(v.service_area||v.service_regions||v.service_states)||'')}</p><div class="vendor-history"><span>Recorded performance</span><strong>${esc(performance(v.performance))}</strong></div><span class="text-link">View profile →</span></button>`).join('')||empty('No matching vendors','Try another activity or search term.')}</div>${pager('vendors',filtered.length,6)}</section>`;
  }
  function vendorProfile(){
    const v=vendors().find(x=>x.id===ui.vendorId);
    if(!v)return empty('Vendor profile not found');
    const jobs=arr(v.history||v.past_projects||v.performance_history);
    return `${heading(v.name,arr(v.capabilities||v.activities).map(human).join(' · '),btn('Back to directory','nav','vendors','quiet'),'VENDOR PROFILE')}<div class="profile-grid fill"><section class="panel"><div class="panel-scroll panel-body"><h2>Company & qualifications</h2><p class="section-copy">${esc(v.description||v.profile||'Profile details recorded below.')}</p>${[['Service area',v.service_area||v.service_regions||v.service_states],['Contact',v.contact||v.email],['Qualifications',v.qualifications],['Insurance',v.insurance],['Capabilities',v.capabilities||v.activities]].filter(([,val])=>val).map(([key,val])=>`<div class="profile-fact"><span>${key}</span><strong>${esc(readable(val))}</strong></div>`).join('')}<div class="reason-box"><span class="eyebrow">REPUTATION PROVENANCE</span><p>${esc(readable(v.reputation||v.reputation_source||v.performance?.provenance||v.provenance||'Synthetic performance records for this demo; not independently verified vendor reviews.'))}</p></div></div></section><section class="panel"><div class="panel-scroll panel-body"><h2>Past performance</h2><p class="section-copy">${esc(performance(v.performance))}</p>${jobs.length?jobs.map(j=>`<article class="history-card"><h3>${esc(j.project||j.title||j.project_name||'Completed engagement')}</h3><p>${esc(readable(j))}</p></article>`).join(''):'<p class="muted">No individual project history supplied. The available aggregate and sample size above should be considered when comparing vendors.</p>'}<h3 class="section-title">Availability is case-specific</h3><p class="muted">Directory history does not establish availability. An offer must match this project, scope, dates and current quote validity.</p></div></section></div>`;
  }
  function budget(){
    const f=finance();
    return `${crumb('Budget')}${heading('Budget & expenses','Baseline, authorized commitments and posted costs are different measures.',btn('Back to site','nav','site','quiet'))}${budgetTiles()}<section class="panel fill">${panelHead('Project cost ledger',pill('USD'))}<div class="panel-scroll"><table class="ledger-table"><thead><tr><th>Cost category</th><th>Baseline</th><th>Committed</th><th>Actual</th></tr></thead><tbody>${arr(f.lines).map(l=>`<tr><th>${esc(l.label||l.category)}</th><td>${money(l.baseline)}</td><td>${money(l.committed)}</td><td>${money(l.actual)}</td></tr>`).join('')}</tbody></table><p class="fineprint panel-body">${esc(f.note)}</p></div></section>`;
  }
  function timeline(){
    const phases=arr(ui.data.phases?.phases),p=phases.find(x=>x.id===ui.phaseId)||phases.find(x=>x.status==='current')||phases[0];
    return `${crumb('Timeline')}${heading('Post-signing project timeline','Phases can run in parallel; new evidence can reopen a completed review.',btn('Back to site','nav','site','quiet'))}${phasesRibbon()}<section class="panel fill">${panelHead(p?.title||'Phase',pill(p?.status))}<div class="panel-scroll panel-body"><p>${esc(p?.description)}</p><div class="phase-detail-grid"><div><h3 class="section-title">Exit criteria</h3><ul class="body-list">${arr(p?.exit_criteria).map(x=>`<li>${esc(x)}</li>`).join('')}</ul><h3 class="section-title">Current assessment</h3><p>${esc(p?.status_reason)}</p></div><div><h3 class="section-title">Planned span</h3><p>${esc(dt(p?.milestones?.planned_start,true))} → ${esc(dt(p?.milestones?.planned_finish,true))}</p><h3 class="section-title">Responsible people</h3><p>${esc(arr(p?.owners).map(x=>`${x.name} · ${x.role}`).join('; '))}</p></div></div><h3 class="section-title">Activities</h3>${arr(p?.task_ids).map(id=>{const t=arr(state().tasks).find(x=>x.id===id);return `<div class="pair"><div><strong>${esc(t?.title||id)}</strong><p class="small muted">${esc(dt(t?.planned_start,true))} · ${esc(personName(t?.owner_id))}</p></div>${pill(t?.status)}</div>`;}).join('')}${arr(p?.blockers).length?`<h3 class="section-title">Open constraints</h3>${arr(p.blockers).map(b=>`<div class="reason-box"><strong>${esc(b.title)}</strong><p>${esc(b.reason)}</p></div>`).join('')}` :''}</div></section>`;
  }
  function constraint(){
    const b=arr(ui.data.dashboard?.bottlenecks).find(x=>x.id===ui.constraintId);
    if(!b)return empty('Constraint no longer active');
    return `${crumb('Project bottleneck')}${heading(b.title,b.detail,pill(b.priority_label))}<section class="panel fill"><div class="panel-scroll panel-body"><div class="reason-box"><span class="eyebrow">RECOMMENDED NEXT ACTION</span><p>${esc(b.next_step)}</p></div><div class="phase-detail-grid"><div><h3 class="section-title">Who can resolve this</h3><p>${esc(personName(b.resolver_id))} · ${esc(person(b.resolver_id)?.role)}</p><h3 class="section-title">Authority</h3><p>${esc(b.authority)}</p></div><div><h3 class="section-title">Why this priority</h3><p>${esc(b.ranking_reason)}</p><h3 class="section-title">What this unlocks</h3><ul class="body-list">${arr(b.unlocks).map(x=>`<li>${esc(x)}</li>`).join('')}</ul></div></div></div><div class="panel-bottom">${btn('Back to site','nav','site','quiet')}${b.action?btn('Apply next action','engine-action',b.id,'primary'):pill('Prerequisites remain')}</div></section>`;
  }
  function details(){
    return `${crumb('Project details')}${heading(project().name,'Project scope, commercial assumptions and delivery ownership.',btn('Back to site','nav','site','quiet'))}<section class="panel fill"><div class="panel-scroll panel-body"><div class="phase-detail-grid"><div>${[['Project ID',project().id],['Customer',project().customer],['Site',project().site],['Utility',project().utility],['Design revision',project().design_revision]].map(([k,v])=>`<div class="profile-fact"><span>${k}</span><strong>${esc(v)}</strong></div>`).join('')}</div><div><h3>People & responsibilities</h3>${people().map(p=>`<div class="pair"><strong>${esc(p.name)}</strong><span>${esc(p.role)}</span></div>`).join('')}</div></div><h3 class="section-title">Project assumptions</h3><ul class="body-list">${arr(project().assumptions).map(x=>`<li>${esc(x)}</li>`).join('')}</ul></div></section>`;
  }
  function dialog(){
    const d=ui.dialog;
    if(d.type==='attachment'){
      const a=messages().flatMap(m=>arr(m.attachments)).find(x=>x.id===d.id);
      return `<div class="modal-shade" data-action="close-dialog"><section class="modal image-modal" role="dialog" aria-modal="true" aria-labelledby="modal-title"><header><h2 id="modal-title">${esc(a?.name||a?.filename||'Original attachment')}</h2>${btn('Close','close-dialog','','quiet')}</header><img src="/api/attachments/${encodeURIComponent(d.id)}${project().demo_project_id?'?project_id='+encodeURIComponent(project().demo_project_id):''}" alt="${esc(a?.name||'Original stakeholder image')}"><p>Original stakeholder attachment · ${esc(a?.mime_type||'image')}</p></section></div>`;
    }
    if(d.type==='calendar'||d.type==='resource'){
      const e=(d.type==='resource'?resourceCalendarRows():calendarRows()).find(x=>x.id===d.id);
      return `<div class="modal-shade"><section class="modal" role="dialog" aria-modal="true" aria-labelledby="modal-title"><header><h2 id="modal-title">${esc(e?.title||'Calendar checkpoint')}</h2>${btn('Close','close-dialog','','quiet')}</header><div class="modal-body">${pill(e?.status)}<h3>${esc(dt(e?.start||e?.at,true))}</h3><p>${esc(e?.detail||'Planned project activity. Confirmations and acceptance remain separate.')}</p>${e?.eligible===false?`<p class="excluded">Not currently eligible: ${esc(arr(e.exclusion_reasons).join(' · ')||'Scope and availability need revalidation.')}</p>`:''}${e?.owner_id||e?.owner?`<p>Owner: ${esc(e.owner_id?personName(e.owner_id):person(e.owner)?.name||vendors().find(v=>v.id===e.owner)?.name||e.owner)}</p>`:''}${e?.case_id?btn('Review linked decision','case',e.case_id,'primary'):''}</div></section></div>`;
    }
    return `<div class="modal-shade"><section class="modal" role="dialog" aria-modal="true" aria-labelledby="modal-title"><header><h2 id="modal-title">${d.type==='reject'?'Reject this proposed option':'Request clarification'}</h2>${btn('Cancel','close-dialog','','quiet')}</header><form id="decision-note-form"><div class="modal-body"><p>The original issue remains open. Record the reason or information needed for the next revision.</p><label>${d.type==='reject'?'Reason for rejection':'Clarification request'}<textarea name="text" required rows="5" maxlength="4000" autofocus></textarea></label></div><div class="panel-bottom"><button class="btn primary" type="submit" ${ui.busy?'disabled':''}>${d.type==='reject'?'Record rejection':'Record clarification request'}</button></div></form></section></div>`;
  }
  function sourceLink(source) {
    const raw=source?.url||source?.href;
    if(!raw)return '';
    try {
      const url=new URL(raw);
      if(!['http:','https:'].includes(url.protocol))return '';
      return `<a class="source-reference" href="${esc(url.href)}" target="_blank" rel="noopener noreferrer">${esc(source.title||source.name||url.hostname)} ↗</a>`;
    } catch { return ''; }
  }
  function evidence() {
    const records=arr(state().evidence),current=records.find(e=>e.id===ui.evidenceId)||records[0];
    const sources=arr(ui.data.sources);
    const ids=arr(current?.source_ids||project().source_ids);
    const linked=sources.filter(source=>ids.includes(source.id));
    return `${crumb('Evidence')}${heading('Project evidence','Original records, scope and supporting references.',btn('Back to site','nav','site','quiet'))}<div class="inbox-grid fill"><section class="panel">${panelHead('Evidence records',pill(records.length+' records'))}<div class="panel-scroll">${pageRows(records,'evidence',7).map(e=>`<button class="evidence-record ${current?.id===e.id?'selected':''}" data-action="evidence-record" data-id="${esc(e.id)}"><strong>${esc(e.title||e.id)}</strong><small>${esc(human(e.kind||'Project record'))} · ${esc(dt(e.received_at||e.effective_at,true))}</small></button>`).join('')||empty('No evidence recorded')}</div>${pager('evidence',records.length,7)}</section><section class="panel"><div class="panel-scroll panel-body">${current?`<div class="row-top"><h2>${esc(current.title||current.id)}</h2>${pill(human(current.kind||'Record'))}</div><div class="evidence-metadata"><span>Record ${esc(current.id)}</span><span>From ${esc(personName(current.issuer_id))}</span><span>Design ${esc(current.design_revision||'Not specified')}</span></div><blockquote class="source-text">${esc(readable(current.body||current.text||current.content||'No body recorded.'))}</blockquote>${current.verification_scope?`<p class="fineprint">${esc(current.verification_scope)}</p>`:''}${messages().some(m=>m.id===current.id)?btn('Open original report and attachments','message',current.id,'quiet'):''}<h3 class="section-title">Supporting public references</h3><div class="source-references">${linked.map(sourceLink).join('')||'<p class="muted small">No public reference is directly indexed for this record.</p>'}</div>`:empty('Select an evidence record')}</div></section></div>`;
  }
  function about() {
    return `${heading('About this workspace','A project management demonstration grounded in deployment workflows.',btn('Back to portfolio','nav','portfolio','quiet'))}<section class="panel fill"><div class="panel-scroll panel-body provenance-content"><h2>Data and provenance</h2><p>The projects, stakeholders, vendors, prices, schedules, qualification records and performance samples in this workspace are fictional demonstration records. Vendor ratings are invented internal examples, not independent public reviews or verified real-world credentials.</p><h3>Contractor portal</h3><p>The role picker provides local preview access, not production identity verification. The <a href="/contractor.html" target="_blank" rel="noopener">contractor portal</a> submits reports into this shared workspace. These are the external delivery partners on each project, not EQORE-owned crews. Reports are recorded as claims for PM review; submitting a report does not authorize a change.</p><h3>Actions and responses</h3><p>Availability inquiries and clarification requests are recorded locally. “Load sample replies,” approval-response previews and confirmation controls exercise the workflow without contacting a real vendor, granting a real permission or placing an order.</p><h3>Original reports and AI summaries</h3><p>Uploaded text and images are retained as source records. When ChatGPT is connected, reading summaries are generated from those originals. Summaries and reported observations do not authorize spending, certify engineering work or establish utility acceptance.</p><h3>Decision authority</h3><p><strong>POLICY_DEMO_01</strong> is the explicit delegation used by these projects. The named PM may approve changes within the recorded limit; larger changes require the commercial approver. Bookings, technical verification and institutional permission remain separate.</p><h3>Workflow references</h3><p>Public references inform the workflow categories. Each project’s actual scope, applicability and conditions still require responsible review.</p><div class="source-references">${arr(ui.data.sources).map(sourceLink).join('')}</div></div></section>`;
  }
  function render(){
    if(!ui.data)return;
    const pages={
      portfolio,site,decision,inbox,compose,calendar,vendors:directory,'vendor-profile':vendorProfile,budget,timeline,constraint,details,evidence,about,subcontractors,procurement,readiness
    }
    ;
    app.innerHTML=shell((pages[ui.view]||portfolio)());
    if(ui.dialog)requestAnimationFrame(()=>app.querySelector('.modal [autofocus],.modal button')?.focus());
  }
  async function api(path,body){
    const response=await fetch(path,body===undefined?{
      cache:'no-store'
    }
    :{
      method:'POST',headers:{
        'Content-Type':'application/json'
      }
      ,body:JSON.stringify(body)
    }
    );
    let data;
    try{
      data=await response.json();
    }
    catch{
      throw new Error(`Unreadable server response (${response.status}).`);
    }
    if(!response.ok){
      const e=new Error(data.error||`Request failed (${response.status})`);
      e.status=response.status;
      throw e;
    }
    return data;
  }
  async function refresh(){
    const selector=project().demo_project_id;
    const data=await api('/api/bootstrap'+(selector?'?project_id='+encodeURIComponent(selector):''));
    if(!data.state)throw new Error('Project records were not returned.');
    ui.data=data;
    ui.updates=null;
  }
  async function mutate(path,payload,title,onSuccess){
    if(ui.busy)return;
    ui.busy=true;
    ui.notice=null;
    const version=path==='/api/projects/select' ? (ui.data.active_session_version ?? ui.data.session_version) : ui.data.session_version;
    render();
    try{
      const data=await api(path,{
        ...payload,expected_version:version
      }
      );
      if(data.state){ui.data=data;ui.updates=null;}
      else await refresh();
      ui.notice={
        text:title
      }
      ;
      if(onSuccess)onSuccess(data);
    }
    catch(e){
      if(e.status===409)await refresh().catch(()=>{
      }
      );
      ui.notice={
        text:e.message,error:true
      }
      ;
    }
    finally{
      ui.busy=false;
      render();
    }
  }
  function operation(type,fields={
  }
  ,title='Project records updated'){
    return mutate('/api/operations',{
      operation:{
        type,...fields
      }
    }
    ,title);
  }
  async function summarize(id){
    if(ui.busy)return;
    ui.busy=true;
    ui.job='Summarizing and triaging the original report';
    ui.notice=null;
    render();
    try{
      const r=await api('/api/message-summary',{
        message_id:id,expected_version:ui.data.session_version
      }
      );
      if(!r.job_id)throw new Error('The server did not return a summary job.');
      let j;
      do{
        await new Promise(resolve=>setTimeout(resolve,1300));
        j=await api('/api/jobs/'+encodeURIComponent(r.job_id));
        if(j.status==='failed')throw new Error(j.error||'ChatGPT summary failed. No substitute summary was generated.');
      }
      while(['running','queued'].includes(j.status));
      if(j.status!=='completed')throw new Error('Unknown summary job status.');
      await refresh();
      ui.notice={
        text:'Fresh ChatGPT reading summary saved with the original report.'
      }
      ;
    }
    catch(e){
      ui.notice={
        text:e.message,error:true
      }
      ;
    }
    finally{
      ui.busy=false;
      ui.job=null;
      render();
    }
  }
  function navigate(view){
    ui.view=view;
    ui.dialog=null;
    if(view==='site')ui.tab='cases';
    render();
    document.getElementById('main')?.focus({
      preventScroll:true
    }
    );
  }
  app.addEventListener('click',async event=>{
    const t=event.target.closest('[data-action]');
    if(!t||t.disabled)return;
    const a=t.dataset.action,id=t.dataset.id;
    if(a==='close-dialog'&&event.target.closest('.modal')&&t.classList.contains('modal-shade'))return;
    if(a==='dismiss'){
      ui.notice=null;
      render();
      return;
    }
    if(a==='nav'){
      navigate(id);
      return;
    }
    if(a==='close-dialog'){
      ui.dialog=null;
      render();
      return;
    }
    if(a==='map-region') { ui.mapRegion=id; render(); return; }
    if(a==='portfolio-filter') { ui.portfolioFilter=id; render(); return; }
    if(a==='resource-tab') { ui.resourceTab=id; render(); return; }
    if(a==='subcontractor') { ui.subcontractId=id; render(); return; }
    if(a==='resource-event') { ui.dialog={type:'resource',id}; render(); return; }
    if(a==='week') { ui.weekOffset=id==='reset'?0:ui.weekOffset+Number(id); render(); return; }
    if(a==='cluster'){
      ui.cluster=!ui.cluster;
      render();
      return;
    }
    if(a==='case'){
      ui.caseId=id;
      ui.view='decision';
      ui.tab='change';
      ui.dialog=null;
      ui.messageId=null;
      render();
      return;
    }
    if(a==='case-tab'||a==='queue-tab'){
      ui.tab=id;
      render();
      return;
    }
    if(a==='message'){
      ui.messageId=id;
      ui.view='inbox';
      render();
      return;
    }
    if(a==='case-message'){
      ui.messageId=id;
      render();
      return;
    }
    if(a==='vendor'){
      ui.vendorId=id;
      ui.view='vendor-profile';
      render();
      return;
    }
    if(a==='phase'){
      ui.phaseId=id;
      ui.view='timeline';
      render();
      return;
    }
    if(a==='constraint'){
      ui.constraintId=id;
      ui.view='constraint';
      render();
      return;
    }
    if(a==='calendar-event'){
      ui.dialog={
        type:'calendar',id
      }
      ;
      render();
      return;
    }
    if(a==='attachment'){
      ui.dialog={
        type:'attachment',id
      }
      ;
      render();
      return;
    }
    if(a==='calendar-filter'){
      ui.calendarFilter=id;
      ui.pages.calendar=0;
      render();
      return;
    }
    if(a==='page'){
      const index=id.lastIndexOf(':'),k=id.slice(0,index),delta=Number(id.slice(index+1));
      ui.pages[k]=Math.max(0,(ui.pages[k]||0)+delta);
      render();
      return;
    }
    if(a==='clarify'||a==='reject'){
      ui.dialog={
        type:a==='clarify'?'clarify':'reject',id
      }
      ;
      render();
      return;
    }
    if(a==='evidence-record'){
      ui.evidenceId=id; ui.view='evidence'; render(); return;
    }
    if(ui.busy)return;
    if(a==='refresh'){
      ui.busy=true;
      render();
      try{
        await refresh();
        ui.notice={
          text:'Current records refreshed.'
        }
        ;
      }
      catch(e){
        ui.notice={
          text:e.message,error:true
        }
        ;
      }
      finally{
        ui.busy=false;
        render();
      }
      return;
    }
    if(a==='project'){
      ui.view='site';
      ui.tab='cases';
      ui.caseId=null;
      ui.messageId=null;
      ui.subcontractId=null;
      ui.weekOffset=0;
      ui.pages={
      }
      ;
      await mutate('/api/projects/select',{
        project_id:id
      }
      ,'Project opened at its saved state.');
      return;
    }
    if(a==='summarize'){
      summarize(id);
      return;
    }
    if(a==='vendor-replies'){
      operation('simulate_vendor_replies',{
        case_id:id
      }
      ,'Sample vendor replies loaded. Review availability, price and quote validity.');
      return;
    }
    if(a==='inquire'){
      operation('request_availability',{
        case_id:id
      }
      ,'Availability inquiries queued in the workspace. No external message was sent.');
      return;
    }
    if(a==='choose-vendor'){
      const[caseId,vendorId]=id.split('|');
      await operation('propose_vendor',{
        case_id:caseId,vendor_id:vendorId
      }
      ,'Exact cost and schedule proposal prepared.');
      if(!ui.notice?.error){
        ui.tab='change';
        render();
      }
      return;
    }
    if(a==='commercial-approve'||a==='commercial-reject'){
      const c=cases().find(x=>x.id===id);
      if(c?.current_proposal)mutate('/api/operations/respond',{
        actor_id:'commercial',operation:{
          type:'simulate_authority_response',case_id:id,proposal_id:c.current_proposal.id,status:a==='commercial-approve'?'approved':'rejected',reason:'Explicit simulated commercial response recorded from the demo control.'
        }
      }
      ,a==='commercial-approve'?'Sample commercial approval recorded. Commit the authorized change to update the plan.':'Sample commercial rejection recorded; the case remains open.');
      return;
    }
    if(a==='commit-approved'){
      const c=cases().find(x=>x.id===id);
      if(c?.current_proposal)operation('commit_proposal',{
        case_id:id,proposal_id:c.current_proposal.id
      }
      ,'Commercially authorized package committed; counterpart confirmations remain outstanding.');
      return;
    }
    if(a==='approve'||a==='request-approval'){
      const c=cases().find(x=>x.id===id);
      if(c?.current_proposal)operation(a==='approve'?'approve_and_commit':'request_approval',{
        case_id:id,proposal_id:c.current_proposal.id
      }
      ,a==='approve'?'Authorized change committed. Booking and institutional acceptance remain separate.':'Approval request routed to the designated commercial approver.');
      return;
    }
    if(a==='confirm-booking'){
      const b=arr(ops().bookings).find(x=>x.id===id);
      mutate('/api/operations/respond',{
        actor_id:b?.recipient_id||b?.vendor_id,operation:{
          type:'confirm_booking',case_id:b?.case_id||ui.caseId,booking_id:id
        }
      }
      ,'Sample counterpart confirmation recorded.');
      return;
    }
    if(a==='engine-action'){
      const b=arr(ui.data.dashboard?.bottlenecks).find(x=>x.id===id);
      if(b?.action)await mutate('/api/action',{
        action:b.action
      }
      ,'Next action processed through project controls.');
      return;
    }
  }
  );
  app.addEventListener('change',e=>{
    if(e.target.id==='vendor-filter'){
      ui.vendorFilter=e.target.value;
      ui.pages.vendors=0;
      render();
    }
  }
  );
  let searchTimer;
  app.addEventListener('input',e=>{
    if(e.target.id==='vendor-search'){
      const value=e.target.value,selection=e.target.selectionStart;
      clearTimeout(searchTimer);
      searchTimer=setTimeout(()=>{
        ui.vendorQuery=value;
        ui.pages.vendors=0;
        render();
        const field=document.getElementById('vendor-search');
        field?.focus();
        field?.setSelectionRange(selection,selection);
      }
      ,180);
    }
  }
  );
  app.addEventListener('submit',async e=>{
    e.preventDefault();
    if(ui.busy)return;
    const form=e.target;
    if(form.id==='decision-note-form'){
      const text=new FormData(form).get('text').trim(),d=ui.dialog,c=cases().find(x=>x.id===d.id);
      if(!text)return;
      ui.dialog=null;
      await operation(d.type==='reject'?'reject_proposal':'request_clarification',{
        case_id:d.id,...(d.type==='reject'?{
          proposal_id:c?.current_proposal?.id,reason:text
        }
        :{
          text
        }
        )
      }
      ,d.type==='reject'?'Option rejected. The underlying issue remains open.':'Clarification request recorded. The underlying issue remains open.');
      return;
    }
    if(form.id==='message-form'){
      const data=new FormData(form);
      const files=Array.from(form.elements.attachments.files);
      if(files.length>4){
        ui.notice={
          text:'Attach up to four original images per report.',error:true
        }
        ;
        render();
        return;
      }
      try{
        const attachments=await Promise.all(files.map(file=>new Promise((resolve,reject)=>{
          if(!['image/png','image/jpeg','image/webp'].includes(file.type))return reject(new Error('Attachments must be PNG, JPEG or WebP images.'));
          if(file.size>4*1024*1024)return reject(new Error('Each image must be no larger than 4 MiB.'));
          const reader=new FileReader();
          reader.onload=()=>resolve({
            name:file.name,mime_type:file.type,data_base64:String(reader.result).split(',')[1]
          }
          );
          reader.onerror=()=>reject(new Error('An attachment could not be read.'));
          reader.readAsDataURL(file);
        }
        )));
        await mutate('/api/messages',{
          sender_id:data.get('sender_id'),subject:data.get('subject'),raw_text:data.get('raw_text'),case_id:data.get('case_id')||null,attachments
        }
        ,'Original stakeholder report saved. Generate its ChatGPT summary to triage it.',()=>{
          ui.view='inbox';
          ui.messageId=messages()[0]?.id;
        }
        );
      }
      catch(error){
        ui.notice={
          text:error.message,error:true
        }
        ;
        render();
      }
    }
  }
  );
  document.addEventListener('keydown',event=>{
    if(['Enter',' '].includes(event.key)&&event.target.matches('g[role=button]')) {
      event.preventDefault(); event.target.dispatchEvent(new MouseEvent('click',{bubbles:true}));
    }
    if(event.key==='Escape'&&ui.dialog){
      ui.dialog=null;
      render();
    }
    if(event.key==='Tab'&&ui.dialog){
      const controls=[...app.querySelectorAll('.modal button:not([disabled]),.modal textarea,.modal input,.modal select,.modal a')];
      const first=controls[0],last=controls[controls.length-1];
      if(event.shiftKey&&document.activeElement===first){
        event.preventDefault();
        last?.focus();
      }
      else if(!event.shiftKey&&document.activeElement===last){
        event.preventDefault();
        first?.focus();
      }
    }
  }
  );
  setInterval(checkUpdates,8000);
  document.addEventListener('visibilitychange',()=>{if(!document.hidden)checkUpdates();});
  refresh().then(render).catch(error=>{
    app.innerHTML=`<main class="connection-error"><span class="brand-mark">e</span><h1>Could not open the workspace</h1><p>${esc(error.message)}</p><button class="btn primary" onclick="location.reload()">Retry connection</button></main>`;
  }
  );
}
)();
