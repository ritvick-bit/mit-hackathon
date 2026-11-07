(() => {
  'use strict';
  const root = document.getElementById('paperwork-app');
  const sessionKey = 'eqore-paperwork-session';
  const query = new URLSearchParams(location.search);
  const ui = {
    token: sessionStorage.getItem(sessionKey), accounts: [], accountId: '', data: null,
    view: query.get('doc_id') ? 'document' : query.get('project_id') ? 'project' : query.get('view')==='integrations'?'integrations':'dashboard',
    projectId: query.get('project_id'), docId: query.get('doc_id'), personId: null,
    filter: 'all', docFilter: 'all', phase: 'all', search: '', archiveSearch: '', coverageFilter: 'all',
    history: [], navOpen: false, restoreScroll: null,
    mapRegion: 'US', mapPriority: 'all',
    tab: 'document', busy: false, notice: null, modal: null, job: null, outputs: {}, connectors: null,
  };
  const navigation = {hovered:false, keyboard:false, keyboardInput:false, pointerType:null, suppressed:false};
  const navigationExpanded = () => ui.navOpen || (!navigation.suppressed && (navigation.hovered || navigation.keyboard));
  function syncNavigation() {
    const expanded=navigationExpanded(), shell=root.querySelector('.shell'), toggle=root.querySelector('.rail-toggle');
    shell?.classList.toggle('nav-expanded',expanded);
    shell?.classList.toggle('nav-open',ui.navOpen);
    toggle?.setAttribute('aria-expanded',String(expanded));
    toggle?.setAttribute('aria-label',`${expanded?'Collapse':'Expand'} navigation`);
    const scrim=root.querySelector('.nav-scrim');if(scrim)scrim.hidden=!ui.navOpen;
  }
  function closeNavigation() {
    ui.navOpen=false;
    navigation.keyboard=false;
    // A click on Collapse must win over the pointer still being inside the rail.
    navigation.suppressed=navigation.hovered;
    syncNavigation();
  }
  function attachNavigation() {
    const sidebar=root.querySelector('#workspace-navigation');if(!sidebar)return;
    navigation.keyboard=false;
    navigation.hovered=navigation.pointerType!=='touch' && globalThis.matchMedia?.('(hover: hover)').matches===true && sidebar.matches(':hover');
    sidebar.addEventListener('pointerenter',event=>{
      if(event.pointerType==='touch'||globalThis.matchMedia?.('(hover: hover)').matches!==true)return;
      navigation.pointerType=event.pointerType;navigation.hovered=true;syncNavigation();
    });
    sidebar.addEventListener('pointerleave',event=>{
      navigation.hovered=false;navigation.suppressed=false;
      if(event.pointerType!=='touch')ui.navOpen=false;
      syncNavigation();
    });
    sidebar.addEventListener('focusin',()=>{
      navigation.keyboard=navigation.keyboardInput;
      if(navigation.keyboard)navigation.suppressed=false;
      syncNavigation();
    });
    sidebar.addEventListener('focusout',event=>{
      if(sidebar.contains(event.relatedTarget))return;
      navigation.keyboard=false;
      if(navigation.keyboardInput)ui.navOpen=false;
      syncNavigation();
    });
    syncNavigation();
  }
  const list = x => Array.isArray(x) ? x : x && typeof x === 'object' ? Object.values(x) : [];
  const escape = x => String(x ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const text = x => x == null ? '' : typeof x === 'object' ? JSON.stringify(x, null, 2) : String(x);
  const human = x => String(x || '').replace(/_/g, ' ');
  const project = () => ui.data?.selected_project || {};
  const docs = () => list(project().documents);
  const doc = () => docs().find(d => d.id === ui.docId);
  const pm = () => ui.data?.pm || {};
  const people = () => list(project().stakeholders);
  const person = id => people().find(p => p.id === id);
  const fullName = x => x?.name || x?.title || x?.id || 'Unassigned';
  const initial = name => String(name || 'PM').split(' ').slice(0,2).map(n => n[0]).join('').toUpperCase();
  const archived = () => project().status === 'archived';
  const isComplete = d => ['completed','signed','accepted','received'].includes(d.status);
  const date = value => {
    if(!value) return 'Not set';
    const d = new Date(String(value).length === 10 ? value + 'T12:00:00Z' : value);
    if(Number.isNaN(d.getTime())) return String(value);
    return new Intl.DateTimeFormat('en-US',{month:'short',day:'numeric',timeZone:'America/New_York'}).format(d);
  };
  const projectDate = value => {
    if(!value)return '';
    const d=new Date(String(value).length===10?value+'T12:00:00Z':value);
    return Number.isNaN(d.getTime())?String(value):new Intl.DateTimeFormat('en-US',{month:'short',day:'numeric',year:'numeric',timeZone:'America/New_York'}).format(d);
  };
  const dateTime = value => {
    if(!value) return 'Not recorded';
    const d = new Date(value);
    return Number.isNaN(d.getTime()) ? String(value) : new Intl.DateTimeFormat('en-US',{month:'short',day:'numeric',hour:'numeric',minute:'2-digit',timeZone:'America/New_York'}).format(d);
  };
  const overdue = d => !isComplete(d) && d.due_at && new Date(d.due_at) < new Date(ui.data?.now || Date.now());
  const tone = status => /overdue|returned|declined|voided|failed|error/i.test(status) ? 'red' : /completed|signed|accepted|received|connected/i.test(status) && !/not.connected|partially/.test(status) ? 'green' : /ready|draft/i.test(status) ? 'blue' : /sent|pending|waiting|partially|blocked/.test(status) ? 'amber' : '';
  const statusLabel = d => d.status === 'sent' ? (d.kind === 'esign' ? 'Awaiting signatures' : d.kind === 'review' ? 'Awaiting review' : 'Awaiting record') : human(d.status);
  const pill = (label, color) => `<span class="pill ${escape(color || tone(String(label)))}">${escape(human(label || 'Not recorded'))}</span>`;
  const btn = (label, action, id = '', style = '', disabled = false) => `<button type="button" class="btn ${style}" data-action="${action}" data-id="${escape(id)}" ${(ui.busy&&!['dismiss','close-modal','close-nav'].includes(action)) || disabled ? 'disabled' : ''}>${escape(label)}</button>`;
  const link = (label, view, id = '') => `<button type="button" class="text-link" data-action="${view}" data-id="${escape(id)}">${escape(label)} →</button>`;
  const empty = (title, detail = '') => `<div class="empty"><h3>${escape(title)}</h3>${detail ? `<p>${escape(detail)}</p>` : ''}</div>`;
  const icons = {
    map:'<path d="m3 6 6-3 6 3 6-3v15l-6 3-6-3-6 3V6Zm6-3v15m6-12v15"/>',
    menu:'<path d="M4 6h16M4 12h16M4 18h16"/>',
    back:'<path d="m10 5-7 7 7 7M3 12h18"/>',
    info:'<circle cx="12" cy="12" r="9"/><path d="M12 11v6m0-10v1"/>',
    queue:'<path d="m4 6 2 2 4-4M13 6h7M4 13h3m6 0h7M4 20h3m6 0h7"/>',
    projects:'<path d="M3 21V9l7-5v5l7-5v8h4v9H3Zm4-4h2m4 0h2m3 0h1"/>',
    archive:'<path d="M4 8h16v13H4zM3 3h18v5H3zM9 12h6"/>',
    integrations:'<path d="M8 3v5m8-5v5M6 8h12v3a6 6 0 0 1-6 6v4m-6-10V8"/>',
    paper:'<path d="M5 3h10l4 4v14H5zM15 3v5h4M8 12h8m-8 4h6"/>',
    arrow:'<path d="M4 12h16m-6-6 6 6-6 6"/>', chevron:'<path d="m9 5 7 7-7 7"/>',
    refresh:'<path d="M20 4v6h-6M4 20v-6h6m-5-5a8 8 0 0 1 14-3m0 9a8 8 0 0 1-14 3"/>',
    mail:'<rect x="3" y="5" width="18" height="14" rx="2"/><path d="m4 6 8 6 8-6"/>',
    signature:'<path d="m4 16 9-9 4 4-9 9H4v-4Zm9-9 3-3 4 4-3 3M13 21h8"/>',
  };
  const icon = name => `<svg class="icon" viewBox="0 0 24 24" aria-hidden="true">${icons[name] || icons.paper}</svg>`;
  const head = (title, subtitle, actions = '', kicker = '') => `<div class="page-head"><div>${kicker ? `<div class="eyebrow">${escape(kicker)}</div>` : ''}<h1>${escape(title)}</h1>${subtitle ? `<p>${escape(subtitle)}</p>` : ''}</div><div class="actions">${actions}</div></div>`;
  const panelHead = (title, right = '') => `<div class="panel-head"><h2>${escape(title)}</h2>${right}</div>`;
  const routeFields = ['view','projectId','docId','personId','filter','docFilter','phase','search','archiveSearch','mapRegion','mapPriority','tab','coverageFilter'];
  const projectViews = ['project','register','document','stakeholder','compliance'];
  function snapshot() {
    return {...Object.fromEntries(routeFields.map(key=>[key,ui[key]])),
      scrolls:[...root.querySelectorAll('.scroll')].map(el=>({top:el.scrollTop,left:el.scrollLeft}))};
  }
  function routeLabel(route) {
    return ({dashboard:'Portfolio',queue:'Work queue',projects:'Projects',archives:'Archives',
      project:'Project overview',register:'Document register',document:'Document',stakeholder:'Contact',
      integrations:'Integrations',about:'About',compliance:'Compliance documents',references:'EQORE references'})[route?.view]||'Portfolio';
  }
  function remember(previous) {
    const last=ui.history[ui.history.length-1];
    if(!last || ['view','projectId','docId','personId'].some(key=>last[key]!==previous[key])) ui.history.push(previous);
    if(ui.history.length>40)ui.history.shift();
  }
  function visit(view,fields={}) {
    if(ui.busy)return;
    clearTimeout(searchTimer);
    if(ui.view!==view || Object.entries(fields).some(([key,value])=>['projectId','docId','personId'].includes(key)&&ui[key]!==value))remember(snapshot());
    Object.assign(ui,{view,navOpen:false,notice:null},fields);
    render();
    root.querySelector('#main')?.focus({preventScroll:true});
  }
  function backTarget() {
    if(ui.history.length)return ui.history[ui.history.length-1];
    if(['document','stakeholder'].includes(ui.view))return {...snapshot(),view:'register',docId:null,personId:null,scrolls:[]};
    if(['register','compliance'].includes(ui.view))return {...snapshot(),view:'project',scrolls:[]};
    if(ui.view!=='dashboard')return {...snapshot(),view:'dashboard',scrolls:[]};
    return null;
  }
  async function goBack() {
    if(ui.busy)return;
    clearTimeout(searchTimer);
    const previous=backTarget();if(!previous)return;
    await run(async()=>{
      if(projectViews.includes(previous.view)&&previous.projectId&&project().id!==previous.projectId)
        accept(await api('/bootstrap?project_id='+encodeURIComponent(previous.projectId)));
      if(ui.history.length)ui.history.pop();
      for(const key of routeFields)ui[key]=previous[key];
      ui.navOpen=false;ui.restoreScroll=previous.scrolls||[];
    });
    root.querySelector('#main')?.focus({preventScroll:true});
  }
  function notices() {
    return `${ui.notice ? `<div class="notice ${ui.notice.error ? 'error' : ''}" role="${ui.notice.error ? 'alert' : 'status'}"><span>${escape(ui.notice.text)}</span><button data-action="dismiss" aria-label="Dismiss notification">×</button></div>` : ''}${ui.job ? `<div class="notice" role="status">${escape(ui.job)}</div>` : ''}`;
  }
  function shell(content) {
    const current=projectViews.includes(ui.view)?'projects':ui.view, previous=backTarget();
    const nav=[['dashboard','map','Portfolio'],['queue','queue','Work queue'],['projects','projects','Projects'],['archives','archive','Archives'],['references','paper','EQORE references'],['integrations','integrations','Integrations']];
    return `<div class="shell ${navigationExpanded()?'nav-expanded':''} ${ui.navOpen?'nav-open':''}"><aside class="sidebar" id="workspace-navigation"><button class="brand" data-action="nav" data-id="dashboard" aria-label="Relay portfolio"><span class="brand-mark">↗</span><strong>RELAY</strong></button><button class="rail-toggle" data-action="toggle-nav" aria-label="${navigationExpanded()?'Collapse':'Expand'} navigation" aria-expanded="${navigationExpanded()}" aria-controls="primary-navigation">${icon('menu')}</button><nav id="primary-navigation" aria-label="Main navigation">${nav.map(([id,symbol,title])=>`<button class="nav-item ${id===current?'active':''}" data-action="nav" data-id="${id}" ${id===current?'aria-current="page"':''} aria-label="${title}" title="${title}">${icon(symbol)}<span>${title}</span></button>`).join('')}</nav><div class="sidebar-bottom"><a href="/delivery.html" aria-label="Site coordination" title="Crew, deliveries and procurement">${icon('projects')}<span>Site coordination ↗</span></a><button data-action="nav" data-id="about" aria-label="About Relay" title="About Relay">${icon('info')}<span>About Relay</span></button></div></aside><button class="nav-scrim" data-action="close-nav" aria-label="Close navigation" ${ui.navOpen?'':'hidden'}></button><div class="workspace"><header class="topbar"><div class="context">${previous?`<button class="back-button" data-action="back" aria-label="Back to ${routeLabel(previous)}" ${ui.busy?'disabled':''}>${icon('back')}<span>${routeLabel(previous)}</span></button>`:''}</div><div class="top-actions"><button class="icon-button" data-action="refresh" aria-label="Refresh records" ${ui.busy?'disabled':''}>${icon('refresh')}</button><button class="profile-button" data-action="profile" title="PM profile"><span class="avatar">${escape(initial(pm().name))}</span><span>${escape(pm().name)}</span></button></div></header><main class="main" id="main" tabindex="-1">${notices()}${content}</main></div></div>${ui.modal?modal():''}`;
  }
  function login() {
    return `<div class="login-shell"><section class="login-story"><div class="brand"><span class="brand-mark">↗</span><strong>RELAY</strong></div><div class="sidebar-caption">EQORE WORKSPACE</div><h1>Projects.<br>Documents.<br>Next steps.</h1><p>Coordinate project paperwork, signatures and stakeholder replies.</p></section><main class="login-form-wrap"><form id="login-form" class="login-form"><h2>Open your workspace</h2>${notices()}<label>Project manager<select name="account_id" required>${ui.accounts.map(a=>`<option value="${escape(a.id)}" ${ui.accountId===a.id?'selected':''}>${escape(a.name)}</option>`).join('')}</select></label><button class="btn primary" type="submit" ${ui.busy||!ui.accounts.length?'disabled':''}>${ui.busy?'Opening…':'Continue →'}</button><p class="fineprint">Local profile preview. Account connections are managed separately in Integrations.</p></form></main></div>`;
  }
  function actionCategory(a) {
    if(a.overdue || a.due_at && new Date(a.due_at)<new Date(ui.data.now) && !isComplete(a)) return 'overdue';
    if(['returned','declined'].includes(a.status)) return 'returned';
    if(['ready','draft'].includes(a.status)) return 'ready';
    if(['sent','partially_signed'].includes(a.status)) return 'waiting';
    return 'other';
  }
  function portfolioActions() {
    const direct = list(ui.data?.action_queue || ui.data?.next_actions);
    if(direct.length) return direct.slice().sort((a,b)=>(b.priority||0)-(a.priority||0));
    return list(ui.data?.projects).flatMap(p => {
      const actions = list(p.action_summary || p.actions);
      return (actions.length ? actions : p.next_action ? [p.next_action] : []).map(a => ({...a, project_id:p.id, project_name:p.name}));
    }).sort((a,b)=>(b.priority||0)-(a.priority||0));
  }
  function metric(label, value, detail, action, id) {
    return `<${action?'button':'div'} class="metric ${action?'clickable':''}" ${action?`data-action="${action}" data-id="${id}"`:''}><span>${escape(label)}</span><strong>${escape(value ?? '—')}</strong><small>${escape(detail)}</small></${action?'button':'div'}>`;
  }
  function queueRow(a, index) {
    return `<button class="queue-row" data-action="${a.view==='compliance'?'open-compliance':'open-action'}" data-id="${escape(a.project_id)}|${escape(a.view==='compliance'?a.requirement_id:(a.doc_id||a.document_id||a.id||''))}"><span class="queue-rank">${String(index+1).padStart(2,'0')}</span><span class="queue-copy"><span class="row-top"><h3>${escape(a.title||'Review project paperwork')}</h3>${pill(actionCategory(a)==='overdue'?'Overdue':a.status?statusLabel(a):a.priority>=90?'Urgent':'Next action')}</span><p>${escape(a.reason||a.next_action||'Review the document, owner and outstanding response before progressing.')}</p><span class="queue-meta">${a.project_name?`<span>${escape(a.project_name)}</span>`:''}<span>${escape(a.owner_name||a.owner_id||'Project PM')}</span>${a.due_at?`<span>Due ${escape(date(a.due_at))}</span>`:''}</span></span></button>`;
  }
  function projectMini(p) {
    const percentage = p.document_count ? 100*p.completed_count/p.document_count : 0;
    return `<button class="project-mini" data-action="project" data-id="${escape(p.id)}"><span class="project-avatar">${icon('projects')}</span><div><strong>${escape(p.name)}</strong><small>${escape(p.completed_count??0)}/${escape(p.document_count??0)} complete · ${escape(p.phase||p.site||'Active project')}</small><div class="progress-line"><i style="width:${Math.min(100,Math.max(0,percentage))}%"></i></div></div>${p.overdue_count?pill(p.overdue_count+' overdue','red'):icon('chevron')}</button>`;
  }
  const mapPriority = p => (p.priority||0)>=90?'urgent':(p.priority||0)>=70?'high':'routine';
  function portfolioMap(projects,all) {
    return globalThis.RelayMap?.render(projects,all,{region:ui.mapRegion})||`<div class="scroll">${projects.map(projectMini).join('')}</div>`;
  }
  function dashboard() {
    const all=list(ui.data.projects).slice().sort((a,b)=>(b.priority||0)-(a.priority||0));
    const projects=all.filter(p=>ui.mapPriority==='all'||mapPriority(p)===ui.mapPriority);
    const ids=new Set(projects.map(p=>p.id)), actions=portfolioActions().filter(a=>ids.has(a.project_id));
    const m=ui.data.metrics||{}, counts=Object.fromEntries(['urgent','high','routine'].map(k=>[k,all.filter(p=>mapPriority(p)===k).length]));
    return `${head('Portfolio',`${all.length} active projects`,btn('Work queue','nav','queue','quiet'))}<div class="metrics">${metric('Active projects',all.length,'Your portfolio','nav','projects')}${metric('Actionable overdue',m.actionable_overdue_count??portfolioActions().filter(overdue).length,m.blocked_overdue_count?`${m.blocked_overdue_count} more await prerequisites`:'Follow-up needed','queue-filter','overdue')}${metric('Ready for the next step',m.ready_count??0,'Ready to prepare','queue-filter','ready')}${metric('Completed documents',m.completed_count??all.reduce((n,p)=>n+(p.completed_count||0),0),'Current accepted revisions')}</div><div class="portfolio-dashboard fill"><section class="panel portfolio-map-panel">${panelHead('Project locations',`<div class="map-views" aria-label="Map region">${[['US','United States'],['NE','Northeast']].map(([id,label])=>`<button data-action="map-region" data-id="${id}" class="${ui.mapRegion===id?'active':''}" aria-pressed="${ui.mapRegion===id}">${label}</button>`).join('')}</div>`)}<div class="map-legend" aria-label="Filter sites by priority">${[['all','All sites',all.length],['urgent','Urgent',counts.urgent],['high','High',counts.high],['routine','Tracking',counts.routine]].map(([id,label,count])=>`<button data-action="map-priority" data-id="${id}" class="${ui.mapPriority===id?'active':''}" aria-pressed="${ui.mapPriority===id}">${id!=='all'?`<i class="priority-dot ${id}"></i>`:''}${label}<strong>${count}</strong></button>`).join('')}</div>${portfolioMap(projects,all)}</section><section class="panel portfolio-queue">${panelHead('Next actions',link('Full queue','nav','queue'))}<div class="queue-context"><span>Highest priority first</span>${pill(actions.length+' actions')}</div><div class="scroll">${actions.map((a,i)=>queueRow(a,i)).join('')||empty('No open actions in this view','Choose another priority or open a project register.')}</div></section></div>`;
  }
  function workQueue() {
    const projects = list(ui.data.projects), all = portfolioActions(), m = ui.data.metrics || {};
    const rows = all.filter(a=>ui.filter==='all'||ui.filter==='overdue'&&overdue(a)||ui.filter==='ready'&&['ready','draft'].includes(a.status)||ui.filter==='waiting'&&['sent','partially_signed'].includes(a.status)||ui.filter==='returned'&&['returned','declined','voided'].includes(a.status));
    const filters = [['all','All priorities'],['overdue','Overdue'],['ready','Ready to prepare'],['waiting','Awaiting response'],['returned','Returned']];
    return `${head('Work queue',`${all.length} actions across ${projects.length} projects`,btn('Projects','nav','projects','quiet'))}<div class="metrics">${metric('Active projects',projects.length,'Your portfolio','nav','projects')}${metric('Actionable overdue',m.actionable_overdue_count??all.filter(a=>overdue(a)).length,m.blocked_overdue_count?`${m.blocked_overdue_count} more await prerequisites`:'Follow-up needed','queue-filter','overdue')}${metric('Ready for the next step',m.ready_count??all.filter(a=>actionCategory(a)==='ready').length,'Ready to prepare','queue-filter','ready')}${metric('Completed documents',m.completed_count??projects.reduce((n,p)=>n+(p.completed_count||0),0),'Current accepted revisions')}</div><div class="dashboard-grid fill"><section class="panel">${panelHead('Priority queue',pill(all.length+' next actions'))}<div class="filters">${filters.map(([id,label])=>`<button class="filter ${ui.filter===id?'active':''}" data-action="queue-filter" data-id="${id}">${label}</button>`).join('')}</div><div class="scroll">${rows.map((a,i)=>queueRow(a,i)).join('')||empty('No actions in this view','Choose another priority or review the project registers.')}</div></section><section class="panel">${panelHead('Active projects',link('All projects','nav','projects'))}<div class="scroll">${projects.map(projectMini).join('')}</div></section></div>`;
  }
  function projectCard(p) {
    const percent = p.document_count ? 100*p.completed_count/p.document_count : 0;
    return `<button class="project-card" data-action="project" data-id="${escape(p.id)}"><span class="row-top"><span class="eyebrow">${escape(p.site||p.id)}</span>${pill(p.status==='archived'?'Archived':p.overdue_count?p.overdue_count+' overdue':p.phase||'Active',p.overdue_count?'red':'')}</span><h2>${escape(p.name)}</h2><p>${escape(p.next_action?.reason||p.next_action?.title||'Current documents and signed records are available in the project register.')}</p><div class="progress-line"><i style="width:${Math.min(100,Math.max(0,percent))}%"></i></div><div class="card-meta"><span>${p.completed_count??0}/${p.document_count??0} documents complete</span><span>${p.status==='archived'?'Read archive':'Open project'} →</span></div></button>`;
  }
  function projectList(isArchive = false) {
    const query = (isArchive ? ui.archiveSearch : ui.search).toLowerCase();
    const rows = list(isArchive?ui.data.archives:ui.data.projects).filter(p=>`${p.name} ${p.site} ${p.phase}`.toLowerCase().includes(query));
    const key = isArchive?'archives':'projects';
    return `${head(isArchive?'Archives':'Projects',isArchive?'Completed projects · read only':'Active projects',pill(`${rows.length} projects`))}<div class="toolbar"><input type="search" data-search="${key}" aria-label="${isArchive?'Search archived projects':'Search projects'}" value="${escape(isArchive?ui.archiveSearch:ui.search)}" placeholder="Search project, location or stage…"></div><section class="panel fill"><div class="project-grid scroll">${rows.map(projectCard).join('')||empty('No matching projects','Try another project name or location.')}</div></section>`;
  }
  function phaseStrip() {
    const phases = [...new Set(docs().map(d=>d.phase).filter(Boolean))];
    return `<div class="stage-strip" aria-label="Document stages">${phases.map(phase=>{
      const group=docs().filter(d=>d.phase===phase), done=group.filter(isComplete).length;
      return `<button class="stage-step ${done===group.length?'complete':group.some(d=>d.status!=='blocked')?'current':''} ${ui.phase===phase?'active':''}" data-action="phase" data-id="${escape(phase)}"><strong>${escape(human(phase))}</strong><small>${done}/${group.length} complete</small></button>`;
    }).join('')}</div>`;
  }
  function profileFacts(p) {
    const f=p.profile||{}, power=f.system_power_kw, energy=f.system_energy_kwh;
    const capacity=[power!=null?`${power.toLocaleString()} kW`:null,energy!=null?`${energy.toLocaleString()} kWh`:null].filter(Boolean).join(' / ');
    const budget=f.project_budget_usd!=null?new Intl.NumberFormat('en-US',{style:'currency',currency:'USD',maximumFractionDigits:0}).format(f.project_budget_usd):null;
    const fields=[['System',capacity],['Industry',f.industry],['Target handover',f.target_handover_date?projectDate(f.target_handover_date):null],['Baseline budget',budget]];
    return `<div class="project-facts">${fields.filter(([,value])=>value).map(([label,value])=>`<div class="fact"><span>${label}</span><strong>${escape(value)}</strong></div>`).join('')}</div>`;
  }
  function projectPeople() {
    return people().map(p=>`<button class="person-row" data-action="stakeholder" data-id="${escape(p.id)}"><span class="avatar">${escape(initial(p.name))}</span><span><strong>${escape(p.name)}</strong><small>${escape(p.role)}</small></span>${icon('chevron')}</button>`).join('');
  }
  function projectView() {
    if(!project().id)return empty('Project not loaded');
    const p=project(),all=docs(),f=p.profile||{};
    const actions=list(p.action_summary).filter(a=>a.status!=='blocked').sort((a,b)=>(b.priority||0)-(a.priority||0));
    const blocked=all.filter(d=>d.status==='blocked'), waiting=all.filter(d=>['sent','partially_signed'].includes(d.status));
    const progress=p.document_count?Math.round(100*p.completed_count/p.document_count):0;
    return `${head(p.name,`${p.site||''} · ${p.phase||'Active'}${archived()?' · Archived':''}`,`${btn('Document register','register',p.id,'primary')}${p.can_archive&&!archived()?btn('Archive project','archive-project',p.id,'quiet'):''}`)}${profileFacts(p)}${phaseStrip()}<div class="project-overview fill"><section class="panel">${panelHead(archived()?'Completion record':'Next actions',`<div class="actions">${coverageButton()}${pill(archived()?'Read only':actions.length+' actions')}</div>`)}<div class="scroll" data-scroll-label="Project actions">${archived()?`<div class="panel-body"><div class="reason-box"><p>${escape(p.closeout_attestation?.text||p.closeout_attestation?.attestation||'Project completed and archived.')}</p></div><p class="muted small">${p.completed_count}/${p.document_count} current documents complete.</p></div>`:actions.map((a,i)=>queueRow({...a,project_id:p.id,owner_name:a.owner_name||person(a.owner_id)?.name||a.owner_id},i)).join('')||empty('No outstanding actions')}${!archived()&&blocked.length?`<details class="blocked-documents"><summary>${blocked.length} documents await prerequisites</summary>${blocked.map(d=>`<button class="mini-action" data-action="document" data-id="${escape(d.id)}"><strong>${escape(d.title)}</strong><small>${escape(list(d.blockers).map(text).join(' · ')||nextReason(d))}</small></button>`).join('')}</details>`:''}</div></section><aside class="panel project-context">${panelHead('Project details')}<div class="scroll"><div class="panel-body"><div class="completion-line"><strong>${p.completed_count??0}<small> / ${p.document_count??all.length} documents</small></strong><span>${progress}%</span></div><div class="progress-line"><i style="width:${progress}%"></i></div><div class="project-counts"><div><strong>${waiting.length}</strong><span>Awaiting response</span></div><div><strong>${blocked.length}</strong><span>Blocked</span></div><div><strong>${all.filter(overdue).length}</strong><span>Overdue</span></div></div>${f.scope?`<p class="scope-summary">${escape(f.scope)}</p>`:''}<details class="scope-details"><summary>Scope & site requirements</summary><dl>${[['Contract signed',f.contract_date?projectDate(f.contract_date):null],['Delivery',f.delivery_model],['Utility',f.utility],['Budget basis',f.budget_basis]].filter(([,v])=>v).map(([label,value])=>`<div><dt>${label}</dt><dd>${escape(value)}</dd></div>`).join('')}</dl>${list(f.site_constraints).length?`<ul>${list(f.site_constraints).map(x=>`<li>${escape(x)}</li>`).join('')}</ul>`:'<p class="muted small">No site constraints recorded.</p>'}</details></div><details class="project-people"><summary>Contacts <span>${people().length}</span></summary>${projectPeople()}</details></div></aside></div>`;
  }
  const complianceRows = () => list(project().compliance_review?.requirements);
  const requirement = id => complianceRows().find(row=>row.id===id);
  const needsCoverageReview = row => ['missing_record','needs_review','update_due','upcoming'].includes(row.status);
  const laterRequirement = row => ['not_yet_due'].includes(row.status);
  function coverageButton() {
    const rows=complianceRows();if(!rows.length)return '';
    const count=archived()?0:rows.filter(needsCoverageReview).length;
    return `<button class="coverage-button" data-action="compliance" aria-label="Document coverage${count?' · '+count+' to review':''}">${icon('paper')}<span>Document coverage</span>${count?`<strong>${count}</strong>`:icon('chevron')}</button>`;
  }
  function sourceLink(source,label) {
    const url=typeof source==='string'?source:source?.url;
    let valid=false;try {valid=new URL(url).protocol==='https:';}catch{}
    const name=label||(typeof source==='object'?((source.title||source.name||source.id||'Source')+(source.page?' · p. '+source.page:'')+(source.sheet?' · '+source.sheet:'')+(source.section?' · '+source.section:'')):source)||'Source';
    return valid?`<a href="${escape(url)}" target="_blank" rel="noopener noreferrer">${escape(name)} ↗</a>`:`<span>${escape(name)}</span>`;
  }
  function referenceSource(id) {
    const sources=list(ui.data?.client_reference?.sources||ui.data?.client_reference?.source_inventory);
    const identity=typeof id==='object'?(id.source_id||id.id):id;
    return {...(sources.find(source=>source.id===identity)||{id:identity,title:identity}),...(typeof id==='object'?id:{})};
  }
  function complianceLabel(row) {
    return ({missing_record:'Not tracked',needs_review:'Review needed',update_due:'Update due',upcoming:'Due soon',not_yet_due:'Later phase',current_record:'Current record'})[row.status]||human(row.status);
  }
  function complianceView() {
    if(!project().id)return empty('Project not loaded');
    const review=project().compliance_review||{}, all=complianceRows();
    const attention=all.filter(needsCoverageReview),later=all.filter(laterRequirement);
    const rows=all.filter(row=>ui.coverageFilter==='all'||ui.coverageFilter==='attention'&&needsCoverageReview(row)||ui.coverageFilter==='later'&&laterRequirement(row)).sort((a,b)=>(b.priority||0)-(a.priority||0));
    const filters=[['all','All documents',all.length],['attention','Needs attention',attention.length],['later','Later phase',later.length]];
    return `${head('Compliance documents',project().name+(archived()?' · Read only':''),btn('Overview','project',project().id,'quiet'))}<div class="coverage-intro"><p>${escape(review.note||'Document coverage and review dates. Applicability and acceptance remain subject to the project’s approved scope and authorities.')}</p>${link('EQORE references','nav','references')}</div><section class="panel fill"><div class="filters">${filters.map(([id,label,count])=>`<button class="filter ${ui.coverageFilter===id?'active':''}" data-action="coverage-filter" data-id="${id}" aria-pressed="${ui.coverageFilter===id}">${label} <strong>${count}</strong></button>`).join('')}</div><div class="scroll coverage-list" data-scroll-label="Compliance document coverage">${rows.map(row=>{
      const tracked=list(row.tracked_document_ids).filter(id=>docs().some(d=>d.id===id));
      const related=list(row.related_document_ids).filter(id=>!tracked.includes(id)&&docs().some(d=>d.id===id));
      const metadata=row.review||{};
      return `<article class="coverage-card"><div class="row-top"><h2>${escape(row.title)}</h2>${pill(complianceLabel(row),needsCoverageReview(row)?'amber':laterRequirement(row)?'':'blue')}</div><p class="coverage-reason">${escape(row.reason||row.action_title||'Review this document requirement for the project.')}</p><dl class="coverage-facts"><div><dt>Owner</dt><dd>${escape(row.owner_name||human(row.owner_role||'Project PM'))}${row.owner_name&&row.owner_name!==row.owner_role?`<small>${escape(human(row.owner_role))}</small>`:''}</dd></div><div><dt>When</dt><dd>${escape(row.when||row.phase||'Confirm timing')}${row.due_at?`<small>Due ${escape(dateTime(row.due_at))}</small>`:''}</dd></div></dl><details class="requirement-details"><summary>Checklist, recipients & sources</summary><dl><div><dt>Recipients / reviewers</dt><dd>${list(row.audiences).map(x=>escape(human(x))).join(' · ')||'Confirm for this site'}</dd></div><div><dt>Update when</dt><dd>${escape(row.update_trigger||'Scope or approved design changes')}</dd></div></dl>${row.evidence_required?`<h3 class="small">Completion evidence</h3>${Array.isArray(row.evidence_required)?`<ul>${row.evidence_required.map(item=>`<li>${escape(item)}</li>`).join('')}</ul>`:`<p class="coverage-reason">${escape(row.evidence_required)}</p>`}`:''}<div class="source-links">${list(row.source_refs).map(id=>sourceLink(referenceSource(id))).join('')}</div>${metadata.review_due_at?`<p class="fineprint">Next review: ${escape(dateTime(metadata.review_due_at))}</p>`:''}${metadata.changed_at?`<p class="fineprint">Change recorded ${escape(dateTime(metadata.changed_at))}: ${escape(metadata.change_reason||'Review source change')}</p>`:''}</details><div class="coverage-actions">${tracked.map(id=>btn('Open tracked document','document',id,'primary small')).join('')}${!tracked.length&&!archived()?btn('Track document','track-requirement',row.id,'primary small'):''}${tracked.length&&!archived()?btn('Review schedule / changes','review-requirement',row.id,'quiet small'):''}${related.map(id=>btn('Related: '+(docs().find(d=>d.id===id)?.title||id),'document',id,'quiet small')).join('')}</div></article>`;
    }).join('')||empty(all.length?'No requirements in this view':'Coverage review unavailable',all.length?'Choose another filter.':'Refresh the project to load its source-based document checklist.')}</div></section>`;
  }
  function referencesView() {
    const reference=ui.data?.client_reference;
    if(!reference)return `${head('EQORE references','Client materials')}<section class="panel fill">${empty('References not loaded','Refresh to load the reviewed EQORE materials.')}</section>`;
    const sources=list(reference.sources),cases=list(reference.reference_cases),requirements=list(reference.requirements);
    return `${head('EQORE references',reference.focus||'Client materials',sourceLink(reference.folder_url,'Shared folder'))}<section class="panel fill"><div class="scroll reference-layout" data-scroll-label="EQORE reference materials"><p class="fineprint">Reviewed ${escape(projectDate(reference.reviewed_at))} · ${sources.length} source files. Source cases are separate from your active projects.</p>${cases.map(item=>`<details class="reference-card" open><summary>${escape(item.name)} <small>${escape(item.system_power_kw)} kW / ${escape(item.system_energy_kwh)} kWh</small></summary><div><p>${escape(item.scope)}</p><dl class="reference-facts">${[['Site',item.site],['Battery',item.battery_model],['Inverter',item.inverter_model],['Industry',item.industry],['Utility',item.utility],['Authority',item.authority],['Plan revision',item.source_revision],['Drawing date, as printed',item.source_date_as_printed]].filter(([,v])=>v).map(([label,value])=>`<div><dt>${label}</dt><dd>${escape(value)}</dd></div>`).join('')}</dl><div class="source-links">${list(item.source_refs).map(ref=>sourceLink(referenceSource(ref))).join('')}</div><details class="requirement-details"><summary>Verified plan details</summary>${list(item.verified_facts).map(fact=>`<div class="reference-source"><p>${escape(fact.fact)}</p><div class="source-links">${sourceLink(referenceSource(fact))}</div></div>`).join('')}</details><details class="requirement-details" open><summary>Items to confirm <small>${list(item.review_flags).length}</small></summary>${list(item.review_flags).map(flag=>`<div class="reference-source"><h3>${escape(flag.title)}</h3><p>${escape(flag.reason)}</p><p><strong>Owner:</strong> ${escape(flag.owner_role)}</p>${flag.does_not_mean?`<p class="fineprint">${escape(flag.does_not_mean)}</p>`:''}<div class="source-links">${list(flag.source_refs).map(ref=>sourceLink(referenceSource(ref))).join('')}</div>`).join('')}</details><details class="requirement-details"><summary>Information not supplied</summary><ul>${list(item.unknowns).map(value=>`<li>${escape(value)}</li>`).join('')}</ul></details></div></details>`).join('')}<details class="reference-card"><summary>Document scope <small>${requirements.length} requirements</small></summary><div><p>The project’s Document coverage view applies this checklist to its tracked records and stage.</p>${requirements.map(row=>`<div class="reference-source"><h3>${escape(row.title)}</h3><p>${escape(row.phase)} · ${escape(row.owner_role)}</p><p>${escape(row.completion_evidence)}</p><div class="source-links">${list(row.source_refs).map(ref=>sourceLink(referenceSource(ref))).join('')}</div></div>`).join('')}</div></details><details class="reference-card"><summary>Source inventory <small>${sources.length} files reviewed</small></summary><div class="reference-sources">${sources.map(source=>`<article class="reference-source"><h3>${sourceLink(source)}</h3><p>${escape(human(source.kind))}${source.page_count?' · '+escape(source.page_count)+' pages':''}</p><p>${escape(source.summary)}</p>${list(source.limitations).length?`<details class="requirement-details"><summary>Source limitations</summary><ul>${source.limitations.map(item=>`<li>${escape(item)}</li>`).join('')}</ul></details>`:''}</article>`).join('')}</div></details><details class="reference-card"><summary>How these references are used</summary><div><ul>${list(reference.boundaries).map(item=>`<li>${escape(item)}</li>`).join('')}</ul></div></details></div></section>`;
  }
  const inputTimezone = () => new Intl.DateTimeFormat().resolvedOptions().timeZone||'your browser time zone';
  function inputDateTime(value) {
    if(!value)return '';const date=new Date(value);if(Number.isNaN(date.getTime()))return '';
    const pad=n=>String(n).padStart(2,'0');
    return `${date.getFullYear()}-${pad(date.getMonth()+1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
  }
  function isoInput(value,label) {
    if(!value)return null;
    const date=new Date(value);
    if(Number.isNaN(date.getTime())||inputDateTime(date)!==value)throw new Error(`${label} is not a valid local date and time.`);
    return date.toISOString();
  }
  function matchesDocumentFilter(d) {
    if(ui.docFilter==='all')return true;
    if(ui.docFilter==='overdue')return overdue(d);
    if(ui.docFilter==='complete')return isComplete(d);
    if(ui.docFilter==='open')return !isComplete(d);
    if(ui.docFilter==='ready')return ['ready','draft'].includes(d.status);
    if(ui.docFilter==='sent')return ['sent','partially_signed'].includes(d.status);
    if(ui.docFilter==='returned')return ['returned','declined','voided'].includes(d.status);
    return d.status===ui.docFilter;
  }
  function registerView() {
    if(!project().id)return empty('Project not loaded');
    const p=project(),query=ui.search.toLowerCase();
    const rows=docs().filter(d=>(ui.phase==='all'||d.phase===ui.phase)&&matchesDocumentFilter(d)&&(!query||`${d.title} ${d.id} ${d.owner_name}`.toLowerCase().includes(query)));
    return `${head('Document register',`${p.name} · ${p.completed_count}/${p.document_count} complete${archived()?' · Read only':''}`,btn('Overview','project',p.id,'quiet'))}${phaseStrip()}<div class="toolbar"><input type="search" data-search="documents" aria-label="Search project documents" value="${escape(ui.search)}" placeholder="Search document or owner…"><select data-change="doc-filter" aria-label="Document status">${[['all','All statuses'],['overdue','Overdue'],['ready','Ready'],['sent','Awaiting response'],['returned','Returned'],['complete','Completed'],['open','Open']].map(([id,label])=>`<option value="${id}" ${ui.docFilter===id?'selected':''}>${label}</option>`).join('')}</select>${ui.phase!=='all'?btn('All stages','phase','all','quiet small'):''}${pill(rows.length+' documents')}</div><section class="panel fill"><div class="scroll document-table-wrap" data-scroll-label="Document register"><table class="document-table"><thead><tr><th>Document</th><th>Status</th><th>Owner</th><th>Due</th></tr></thead><tbody>${rows.map(d=>`<tr role="button" tabindex="0" data-action="document" data-id="${escape(d.id)}" aria-label="Open ${escape(d.title)}"><td class="doc-title">${escape(d.title)}<small>${escape(d.id)} · revision ${escape(d.revision)} · ${escape(human(d.kind))}</small></td><td>${pill(statusLabel(d))}${overdue(d)?'<br><small class="overdue-text">Overdue</small>':''}</td><td class="person-cell">${escape(d.owner_name||person(d.owner_id)?.name||d.owner_id)}</td><td class="date-cell">${escape(date(d.due_at))}</td></tr>`).join('')}</tbody></table>${!rows.length?empty('No matching documents'):''}</div></section>`;
  }
  function linkedEmails(d) {
    return list(project().emails).filter(e=>e.doc_id===d.id||e.document_id===d.id||list(e.doc_ids).includes(d.id));
  }
  function events(d) {
    const own=list(d.source_events);
    return own.length?own:list(project().history).filter(e=>e.doc_id===d.id||e.document_id===d.id);
  }
  function emailsView(d) {
    const rows=linkedEmails(d);
    const records=rows.map(e=>`<article class="email"><div class="row-top"><h3>${escape(e.subject||'Stakeholder email')}</h3>${pill(e.direction||'Incoming')}</div><div class="email-meta">${escape(e.sender_name||e.original_from||e.from||person(e.sender_id)?.name||e.sender_id||'Sender not recorded')} · ${escape(dateTime(e.received_at||e.created_at||e.occurred_at||e.at))}</div><blockquote>${escape(e.text||e.body||e.raw_text||'No email body recorded.')}</blockquote><p class="fineprint">${escape(e.source||e.provider||human(e.source_mode)||'Original recorded email')} · ${escape(e.id||e.event_id||'')}</p></article>`).join('')||empty('No email is linked to this document','Email replies are source records. A reply alone does not establish a signature or formal acceptance.');
    return `${!archived()?`<div class="actions section-title">${btn('Record an original email','record-email',d.id,'quiet small')}${connector('gmail').configured?btn('Sync Gmail replies','connector-sync','gmail','quiet small'):''}</div>`:''}${records}`;
  }
  function eventsView(d) {
    return events(d).map(e=>`<article class="timeline-event"><span class="event-dot"></span><div><div class="row-top"><h3>${escape(human(e.event_type||e.type||e.status||'Document event'))}</h3>${e.source_mode==='sample'?pill('Local sample'):e.provider?pill(e.provider):e.source_mode==='provider'?pill('Verified provider'):''}</div><p>${escape(e.description||e.detail||e.text||e.reason||`${e.recipient_name||person(e.recipient_id)?.name||e.actor_name||person(e.actor_id)?.name||''} ${human(e.status||'')}`)}</p><small>${escape(dateTime(e.at||e.created_at||e.occurred_at||e.timestamp||e.received_at))} · revision ${escape(e.revision??'—')} · ${escape(e.event_id||e.id||'')}</small></div></article>`).join('')||empty('No signing or review events yet','When recorded, each event keeps its source, recipient and timestamp.');
  }
  function dependenciesView(d) {
    const next=docs().filter(x=>list(x.prerequisites).some(p=>p.doc_id===d.id));
    return `<h3>Required before this document</h3>${list(d.prerequisites).map(p=>`<div class="history-row"><div><strong>${escape(p.title||p.doc_id)}</strong><small>Required revision ${escape(p.required_revision)} · current revision ${escape(p.current_revision)}</small></div>${pill(p.status)}${link('Open','document',p.doc_id)}</div>`).join('')||'<p class="muted small section-title">No prerequisite document is required.</p>'}<h3 class="section-title">What completion unlocks</h3>${next.map(x=>`<div class="history-row"><div><strong>${escape(x.title)}</strong><small>${escape(human(x.phase))}</small></div>${pill(statusLabel(x))}${link('Open','document',x.id)}</div>`).join('')||'<p class="muted small">No downstream document is linked.</p>'}<p class="fineprint section-title">A revised prerequisite may invalidate downstream readiness. Acceptance must match the current revision.</p>`;
  }
  function documentView() {
    const d=doc();
    if(!d)return `${empty('Document not found','Open a document in this project’s register.')}`;
    const allowed=list(d.allowed_actions), output=ui.outputs[`${project().id}:${d.id}:summary`]||d.reading_summary||d.summary;
    const content=ui.tab==='emails'?emailsView(d):ui.tab==='events'?eventsView(d):ui.tab==='dependencies'?dependenciesView(d):`<div class="facts">${[['Document',d.id],['Revision',d.revision],['Owner',d.owner_name||person(d.owner_id)?.name||d.owner_id],['Due',date(d.due_at)],['Stage',human(d.phase)],['Package type',d.kind==='esign'?'Electronic signature':d.kind==='review'?'Formal review':'Evidence record']].map(([k,v])=>`<div class="fact"><span>${k}</span><strong>${escape(v)}</strong></div>`).join('')}</div><article class="document-preview"><div class="eyebrow">CURRENT DOCUMENT · REVISION ${escape(d.revision)}</div><h2>${escape(d.title)}</h2><div class="body">${escape(d.body||'A document draft has not been prepared yet. Use the source requirements and responsible stakeholders to prepare the next revision.')}</div></article>${output?`<div class="reason-box"><div class="eyebrow">CHATGPT READING SUMMARY</div><p>${escape(output.text||output.summary||text(output))}</p></div>`:''}<p class="fineprint">The document and its source events are the record. Summaries help with reading; they do not replace signature evidence or acceptance authority.</p>`;
    return `${head(d.title,`${project().name} · ${d.id} · revision ${d.revision}`,`${pill(statusLabel(d))}${overdue(d)?pill('Overdue','red'):''}${btn('Register','register',project().id,'quiet')}`)}<div class="detail-grid fill"><section class="panel"><div class="tabs">${[['document','Document'],['emails','Original emails'],['events','Signing & events'],['dependencies','Dependencies']].map(([id,label])=>`<button data-action="tab" data-id="${id}" class="${ui.tab===id?'active':''}">${label}</button>`).join('')}</div><div class="scroll panel-body">${content}</div></section><aside class="detail-sidebar"><section class="panel">${panelHead('Next step',archived()?pill('Read only'):'')}<div class="scroll panel-body"><div class="reason-box"><div class="eyebrow">WHY THIS ACTION</div><p>${escape(list(d.blockers).length?list(d.blockers).map(text).join(' · '):nextReason(d))}</p></div>${archived()?'<p class="muted small">This project is archived. Its records and event history are read-only.</p>':`<div class="action-stack">${allowed.includes('draft_document')?btn(d.body?'Edit document draft':'Prepare document draft','edit-document',d.id,'primary'):''}${allowed.includes('send_document')?btn('Prepare local package','prepare-package',d.id,'primary'):''}${btn('Draft stakeholder email','draft-email',d.id,'quiet')}${ui.data.runtime?.available&&ui.data.runtime?.authenticated?btn('Draft with ChatGPT','assist-email',d.id,'quiet'):''}${allowed.includes('revise_document')?btn('Open a new revision','revise-document',d.id,'quiet'):''}${allowed.includes('void_document')?btn('Void current package','void-document',d.id,'quiet'):''}${externalDraftActions(d)}</div><p class="fineprint section-title">Local packages exercise the workflow without contacting a signer. Connected account drafts are separate and remain unsent.</p>`}${!archived()&&ui.data.runtime?.available&&ui.data.runtime?.authenticated?`<div class="section-title">${link('Summarize with ChatGPT','assist-summary',d.id)}</div>`:''}</div></section><section class="panel">${panelHead(d.kind==='esign'?'Signers':'Responsible recipients',pill(list(d.recipients).length+' recipients'))}<div class="scroll panel-body">${list(d.recipients).map(r=>`<div class="signer-row"><span class="avatar">${escape(initial(r.name))}</span><div><strong><button class="text-link" data-action="stakeholder" data-id="${escape(r.id)}">${escape(r.name)}</button></strong><small>${escape(person(r.id)?.email||r.role||r.email||'Recipient')}${r.signed_at?' · '+escape(date(r.signed_at)):''}</small></div>${pill(r.status)}</div>`).join('')||'<p class="muted small">Recipients have not been specified.</p>'}${d.envelope_id?`<p class="fineprint section-title">Package ${escape(d.envelope_id)} · ${escape(human(d.envelope_status))}</p>`:''}${!archived()&&allowed.includes('simulate_event')?`<details class="sample-controls"><summary>Try a sample update</summary><p class="fineprint">Record a local example event. This does not contact a real signer.</p>${btn('Choose a sample response','sample-event',d.id,'quiet small')}</details>`:''}</div></section></aside></div>`;
  }
  function nextReason(d) {
    const next=list(project().action_summary).find(a=>a.doc_id===d.id);
    if(next?.reason)return next.reason;
    if(isComplete(d))return 'The current revision is complete. Review the dependencies to see which documents can move next.';
    if(d.next_action?.reason)return d.next_action.reason;
    if(['sent','partially_signed'].includes(d.status))return 'The package is awaiting its remaining recipients. Review individual responses and follow up on the outstanding requirement.';
    if(['returned','declined'].includes(d.status))return 'A recipient returned this revision. Resolve the recorded comments before preparing a revised package.';
    return 'Review the current scope, prerequisites, recipients and due date before preparing the package.';
  }
  function connectorRows() {
    const source=ui.connectors||ui.data?.connectors||{};
    const configuration=source.configuration||source.providers||source;
    const rows=Array.isArray(configuration)?configuration:Object.entries(configuration).filter(([,v])=>v&&typeof v==='object').map(([id,v])=>({id,...v}));
    return rows.map(c=>({...c,check:source.checks?.[c.id||c.provider]}));
  }
  function connector(id) { return connectorRows().find(c=>(c.id||c.provider)===id)||{}; }
  function externalDraftActions(d) {
    if(archived())return '';
    const ds=connector('docusign');
    return `${d.kind==='esign'&&ds.configured?btn(d.provider==='docusign'?'Sync DocuSign status':'Create DocuSign draft',d.provider==='docusign'?'connector-sync':'connector-draft','docusign','quiet'):''}${['gmail'].filter(id=>connector(id).configured).map(id=>btn(`Create ${id==='gmail'?'Gmail':'Outlook'} draft`,'connector-draft',id,'quiet')).join('')}`;
  }
  function stakeholderView() {
    const p=person(ui.personId)||docs().flatMap(d=>list(d.recipients)).find(p=>p.id===ui.personId)||{id:ui.personId};
    const related=docs().filter(d=>d.owner_id===p.id||list(d.recipients).some(r=>r.id===p.id));
    const signed=list(project().signed_history).filter(h=>h.recipient_id===p.id);
    const accepted=related.filter(d=>d.kind!=='esign'&&list(d.recipients).some(r=>r.id===p.id&&['accepted','received'].includes(r.status))).map(d=>{const r=list(d.recipients).find(r=>r.id===p.id);return {doc_id:d.id,title:d.title,revision:d.revision,signed_at:r.responded_at,status:r.status,source_mode:d.source_mode};});
    const history=[...signed,...accepted].sort((a,b)=>String(b.signed_at||'').localeCompare(String(a.signed_at||'')));
    const open=related.filter(d=>!isComplete(d));
    return `${head(p.name||p.id,`${p.role||'Project stakeholder'} · ${project().name} only`,`${!archived()?btn('Edit project contact','edit-contact',p.id,'quiet'):''}${btn('Back to project','project',project().id,'quiet')}`)}<div class="metrics">${metric('Documents involved',related.length,'Within this project')}${metric('Signed / accepted records',history.length,'Including recorded prior signatures')}${metric('Open documents',open.length,'Current project revisions')}${metric('Contact',p.email?'Recorded':'Not set',p.email||p.contact||'Configure the intended test contact')}</div><div class="detail-grid fill"><section class="panel">${panelHead('Completed & signed history',pill(history.length+' records'))}<div class="scroll">${history.map(h=>`<div class="history-row"><div><strong>${escape(h.title||h.doc_id)}</strong><small>Revision ${escape(h.revision)} · ${escape(dateTime(h.signed_at))}${h.source_mode==='sample'?' · Local sample':''}</small></div>${pill(h.status||'Signed')}${btn('Open record','document',h.doc_id,'quiet small')}</div>`).join('')||empty('No completed records for this stakeholder','Completed reviews and signatures appear here with their project and revision.')}</div></section><section class="panel">${panelHead('Outstanding in this project',pill(open.length+' documents'))}<div class="scroll">${open.map(d=>`<button class="mini-action" data-action="document" data-id="${escape(d.id)}"><strong>${escape(d.title)}</strong>${pill(statusLabel(d))}<small> Due ${escape(date(d.due_at))} · revision ${escape(d.revision)}</small></button>`).join('')||empty('No outstanding documents')}</div></section></div>`;
  }
  function integrations() {
    const providers=['docusign','gmail'].map(id=>({id,...connector(id)}));
    const names={docusign:'DocuSign',gmail:'Gmail'};
    return `${head('Integrations','Account connections and sync status.',btn('Refresh status','refresh-connectors','','quiet'))}<section class="panel fill"><div class="scroll"><div class="integration-grid">${providers.map(c=>{
      const id=c.id||c.provider, email=id==='gmail';
      const connected=c.connected||['connected','healthy','ready'].includes(c.status), configured=c.configured;
      const setup=email?'Google OAuth client ID':'DocuSign integration key';
      const description=c.message||c.detail||c.reason||c.error?.message||text(c.error)||(connected?'The account connection was verified. External drafts remain unsent until separately dispatched.':configured?'Configuration is present. Test the provider connection before creating external drafts.':'No connected account is available. Account configuration is required before external drafts or event synchronization.');
      return `<article class="integration-card"><div class="row-top"><span class="integration-icon">${icon(email?'mail':'signature')}</span>${pill(connected?'Connected':configured?'Configured · test required':'Not configured',connected?'green':configured?'amber':'')}</div><h2>${escape(names[id])}</h2>${email?'<p>Email connection is optional. Prepare, edit, copy and download stakeholder drafts without connecting Gmail. No mailbox connection starts automatically.</p>':''}<p>${escape(description)}</p>${email?'<details class="optional-connection"><summary>Optional Gmail connection setup</summary>':''}<form class="oauth-form" data-provider="${id}"><label>${setup}<input name="client_id" value="${escape(c.client_id||c.oauth?.client_id||'')}" placeholder="${email?'Your public Google client ID':'DocuSign integration key'}" autocomplete="off"></label><button class="btn primary small" type="submit" ${ui.busy||location.hostname!=='localhost'?'disabled':''}>${connected?'Reconnect account':'Connect account'}</button>${location.hostname!=='localhost'?`<p class="fineprint section-title"><a href="${escape('http://localhost'+(location.port?':'+location.port:'')+'/paperwork.html?view=integrations')}">Open localhost to connect →</a></p>`:''}</form>${email?'</details>':''}${list(c.missing_env).length?`<details class="setup-details"><summary>Connection setup requirements</summary><p>${escape(email?'Use the intended Google test account and a configured Google OAuth client. Review Gmail access on Google’s permission screen before connecting.':'Use a DocuSign developer sandbox account and its integration key. Creating an account alone does not configure API access.')}</p><code>${escape(c.missing_env.join(' · '))}</code><p class="fineprint">Only public application identifiers belong in this form. Complete sign-in and permissions on the provider’s page.</p></details>`:''}<div class="fact"><span>Last successful connection / sync</span><strong>${escape(dateTime(c.last_success||c.last_success_at||c.last_sync_at||c.last_checked_at||(c.check?.state==='connected'?c.check.checked_at:null)))}</strong></div><div class="actions section-title">${btn('Test connection','connector-test',id,'quiet small',!configured)}${id==='docusign'&&connected?btn('Create test draft','connection-test','','quiet small'):''}</div>${id==='docusign'&&ui.connectors?.latest_connection_test?`<div class="reason-box section-title"><strong>Connection test draft</strong><p class="small">${escape(ui.connectors.latest_connection_test.envelope_id||'Request recorded')} · ${escape(ui.connectors.latest_connection_test.result?.envelope_status||ui.connectors.latest_connection_test.envelope_status||ui.connectors.latest_connection_test.status||'Pending')}</p><p class="fineprint">Last observed provider status. No signature request was sent by Relay; project approvals are unchanged.</p></div>`:''}</article>`;
    }).join('')}</div><div class="integration-events"><div class="reason-box"><h3>Packages and drafts stay reviewable</h3><p>Prepare a document from its project page, check its recipients and scope, then create an external account draft when a provider is configured. No draft button sends an email or requests a live signature.</p></div><h3>After connecting</h3><p class="fineprint">Finish the provider’s sign-in screen, return here and refresh status. Edit the intended test recipient’s contact on the project page before preparing a provider draft. Synchronize replies from that document’s Original emails tab.</p><h3 class="section-title">Local sample activity</h3><p class="fineprint">The sample-response controls on each document exercise signing and review events locally. They are labelled separately from provider events and cannot establish a real DocuSign signature.</p></div></div></section>`;
  }
  function about() {
    return `${head('About Relay','EQORE project coordination.',btn('Back to work queue','nav','queue','quiet'))}<section class="panel fill"><div class="scroll panel-body provenance"><h2>Relay · EQORE workspace</h2><p>Relay keeps documents and decisions moving between the people responsible for each project. The portfolio map uses illustrative city-centre locations; it does not identify surveyed installation addresses.</p><h3>Project records and boundaries</h3><p>The seeded projects, contacts, dates and document contents are demonstration records. Each selected PM sees only their assigned projects. Signed history stays linked to the particular project, document revision and recipient.</p><h3>Profile selection and account connections</h3><p>The local profile picker is a preview of separate PM workspaces, not an identity-verified login system. The session is kept in this browser tab. Email and DocuSign access require a separately configured test account; Integrations reports the server’s current connection state.</p><h3>Source events and approvals</h3><p>Original emails, recipient responses and provider events remain distinct. An email acknowledgement does not count as a signature, regulator acceptance or completed record. Local sample updates are clearly marked in their event trail.</p><h3>Drafts and AI assistance</h3><p>A prepared email is editable and can be copied before use. ChatGPT assistance is available only when the server reports an authenticated connection. Drafts and summaries do not authorize spending, certify technical work or replace stakeholder acceptance.</p><h3>Archives</h3><p>Completed projects retain their document and stakeholder history as read-only records. Closing a project requires every current document to be complete and an explicit PM completion statement.</p><h3>Site coordination</h3><p><a href="/delivery.html">Open site coordination →</a> for crew, delivery, procurement and installation schedules, plus project budgets.</p></div></section>`;
  }
  function modal() {
    const m=ui.modal, d=doc();
    let title='',body='',footer='';
    if(m.type==='connection-test') {
      title='Create a DocuSign test draft';body=`<form id="connection-test-form"><p>A single unsent test document confirms the DocuSign connection and signature fields. It is separate from all project approvals.</p><label class="section-title">Test signer email<input type="email" name="email" value="${escape(m.email||'')}" required autocomplete="email"></label><p class="fineprint section-title">The document will be uploaded to your connected DocuSign developer account. No email will be sent.</p><button type="submit" class="btn primary">Create unsent test draft</button></form>`;
    } else if(m.type==='profile') {
      title='Your PM workspace';body=`<p><strong>${escape(pm().name)}</strong></p><p class="muted section-title">Project membership is checked by the server for this profile. This local profile picker is not production identity authentication.</p>`;footer=btn('Switch PM profile','logout','','quiet');
    } else if(m.type==='email') {
      title='Review stakeholder email';body=`<div class="eyebrow">${escape(m.mode||'Prepared draft')}</div><label>To<input name="to" value="${escape(m.to||'')}" readonly><small class="muted">Recipients come from this project’s reviewed contact records.</small></label><label>Subject<input name="subject" value="${escape(m.subject||'')}" data-draft="subject"></label><label>Email body<textarea name="body" data-draft="body" rows="10">${escape(m.body||'')}</textarea></label>`;footer=`<p>Editable draft only. Copying or downloading does not send it.</p><div class="actions">${btn('Save reviewed draft','save-email-draft','','quiet')}${btn('Download draft','download-draft','','quiet')}${btn('Copy draft','copy-draft','','primary')}</div>`;
    } else if(['edit','revise','void'].includes(m.type)) {
      title=m.type==='edit'?'Review document draft':m.type==='revise'?'Prepare a new revision':'Void the current package';body=`<form id="document-form"><p class="muted small">${escape(d?.title)} · current revision ${escape(d?.revision)}</p>${m.type!=='edit'?'<label class="section-title">Reason<textarea name="reason" required rows="3" maxlength="4000"></textarea></label>':''}${m.type!=='void'?`<label class="section-title">Document body<textarea name="body" rows="12" required maxlength="30000">${escape(d?.body||'')}</textarea></label>`:''}<button class="btn primary" type="submit" ${ui.busy?'disabled':''}>${m.type==='void'?'Record void reason':m.type==='revise'?'Save new revision':'Save prepared draft'}</button></form>`;
    } else if(m.type==='sample') {
      title='Try a sample response';const allowedTypes=d?.kind==='esign'?[['recipient_signed','Recipient signed'],['recipient_declined','Recipient declined']]:d?.kind==='review'?[['review_accepted','Review accepted'],['review_returned','Review returned']]:[['record_received','Required record received']];
      body=`<p class="fineprint">This records a local example event, without contacting a real recipient or issuing a real signature.</p><form id="sample-form"><label class="section-title">Recipient<select name="recipient_id">${list(d?.recipients).slice().sort((a,b)=>(a.status==='pending'?-1:1)-(b.status==='pending'?-1:1)).map(r=>`<option value="${escape(r.id)}">${escape(r.name)} · ${escape(human(r.status))}</option>`).join('')}</select></label><label>Response<select name="event_type">${allowedTypes.map(([id,label])=>`<option value="${id}">${label}</option>`).join('')}</select></label><button class="btn primary" type="submit">Load sample response</button></form>`;
    } else if(m.type==='package') {
      title='Prepare a local package';body=`<p><strong>${escape(d?.title)}</strong> · revision ${escape(d?.revision)}</p><p class="muted section-title">Record this package for the listed recipients in the local workflow. This will not send a live signature request or email.</p>${list(d?.recipients).map(r=>`<div class="signer-row"><div><strong>${escape(r.name)}</strong><small>${escape(r.role)}</small></div>${pill(r.status)}</div>`).join('')}`;footer=btn('Prepare local package','confirm-package',d?.id,'primary');
    } else if(m.type==='contact') {
      const contact=person(ui.personId)||{};
      title='Review project contact';body=`<form id="contact-form"><p><strong>${escape(contact.name)}</strong> · ${escape(contact.role)}</p><p class="fineprint section-title">Use the intended test recipient address. This changes the project contact for future drafts; original emails and signatures remain intact.</p><label>Email address<input type="email" name="email" required value="${escape(contact.email||'')}" maxlength="254"></label><button class="btn primary" type="submit">Save project contact</button></form>`;
    } else if(m.type==='record-email') {
      title='Record an original email';body=`<form id="email-record-form"><p class="fineprint">Retain the message as an unverified local entry. It does not change signing or acceptance status.</p><label class="section-title">Sender<select name="sender_id">${people().map(p=>`<option value="${escape(p.id)}">${escape(p.name)} · ${escape(p.role)}</option>`).join('')}</select></label><label>Original subject<input name="subject" required maxlength="250"></label><label>Original email text<textarea name="text" required rows="9" maxlength="30000"></textarea></label><button class="btn primary" type="submit">Save original email</button></form>`;
    } else if(m.type==='track-requirement'||m.type==='review-requirement') {
      const row=requirement(m.requirementId),review=row?.review||{},canReview=list(row?.tracked_document_ids).some(id=>docs().some(d=>d.id===id&&isComplete(d)));
      if(!row||archived()){title='Document coverage';body='<p>This requirement is unavailable for changes.</p>';}
      else if(m.type==='track-requirement') {
        title='Track document';body=`<form id="track-requirement-form"><p><strong>${escape(row.title)}</strong></p><p class="muted small section-title">${escape(row.when||row.reason||'Confirm the project-specific due date before adding this document.')}</p><label class="section-title">Due date and time<input type="datetime-local" name="due_at" required><small class="muted">${escape(inputTimezone())} · set by the project PM</small></label><p class="fineprint section-title">Creates a project record and preparation checklist. No email, signature request or approval is sent.</p><button class="btn primary" type="submit" ${ui.busy?'disabled':''}>Add to document register</button></form>`;
      } else {
        title='Review schedule / changes';body=`<form id="requirement-review-form"><p><strong>${escape(row.title)}</strong></p><p class="fineprint section-title">Times use ${escape(inputTimezone())}. A review date or recorded change does not establish formal approval.</p><label class="section-title">Next review date<input type="datetime-local" name="review_due_at" value="${escape(inputDateTime(review.review_due_at))}"><small class="muted">Leave blank to clear the scheduled review.</small></label><details class="requirement-details"><summary>Record a new scope or source change</summary><label class="section-title">When the change occurred<input type="datetime-local" name="changed_at"></label><label>Change and affected documents<textarea name="change_reason" rows="3" maxlength="2000" placeholder="What changed and why must this document be reviewed?"></textarea></label></details>${canReview?`<details class="requirement-details"><summary>Record a completed document review</summary><label class="checkbox-label section-title"><input type="checkbox" name="attest_review"> I reviewed the current document and its supporting evidence.</label><label>Review note<textarea name="review_note" rows="3" maxlength="2000" placeholder="What was checked, and what changed or remains unchanged?"></textarea></label></details>`:''}<button class="btn primary section-title" type="submit" ${ui.busy?'disabled':''}>Save review details</button></form>`;
      }
    } else if(m.type==='archive') {
      title='Archive completed project';body=`<form id="archive-form"><p>All current document requirements must be complete. The archived project becomes read-only.</p><label class="section-title">Completion statement<textarea name="attestation" rows="4" required maxlength="4000" placeholder="Record the project closeout scope and completion confirmation…"></textarea></label><label class="checkbox-label"><input type="checkbox" name="complete" required> I confirm that this project is complete.</label><button class="btn primary" type="submit">Archive project</button></form>`;
    }
    return `<div class="modal-shade"><section class="modal" role="dialog" aria-modal="true" aria-labelledby="modal-title"><header><h2 id="modal-title">${title}</h2>${btn('Close','close-modal','','quiet small')}</header><div class="modal-body">${ui.notice?.error?`<p class="notice error" role="alert">${escape(ui.notice.text)}</p>`:''}${body}</div>${footer?`<div class="modal-footer">${footer}</div>`:''}</section></div>`;
  }
  function render() {
    if(!ui.token||!ui.data) { root.innerHTML=login(); return; }
    const pages={dashboard,queue:workQueue,register:registerView,projects:()=>projectList(false),archives:()=>projectList(true),project:projectView,document:documentView,stakeholder:stakeholderView,compliance:complianceView,references:referencesView,integrations,about};
    root.innerHTML=shell((pages[ui.view]||dashboard)());
    attachNavigation();
    globalThis.RelayMap?.attach(root);
    root.querySelector('#main')?.setAttribute('aria-busy',String(ui.busy));
    if(ui.busy)root.querySelectorAll('[data-action]').forEach(control=>{
      if(['dismiss','close-modal','close-nav'].includes(control.dataset.action))return;
      control.setAttribute('aria-disabled','true');
      control.classList.add('async-disabled');
      if(control.tagName==='BUTTON')control.disabled=true;
      else if(control.hasAttribute('tabindex'))control.setAttribute('tabindex','-1');
    });
    const scrolls=[...root.querySelectorAll('.scroll')];
    scrolls.forEach((el,i)=>{
      el.setAttribute('tabindex','0');
      el.setAttribute('aria-label',el.dataset.scrollLabel||el.closest('.panel')?.querySelector('h2')?.textContent||'Scrollable records');
      if(ui.restoreScroll?.[i]){el.scrollTop=ui.restoreScroll[i].top;el.scrollLeft=ui.restoreScroll[i].left;}
    });
    ui.restoreScroll=null;
    if(ui.modal)requestAnimationFrame(()=>root.querySelector('.modal input,.modal textarea,.modal select,.modal button')?.focus());
  }
  async function api(path, payload) {
    const response=await fetch('/api/paperwork'+path,{method:payload===undefined?'GET':'POST',cache:'no-store',headers:{...(ui.token?{Authorization:'Bearer '+ui.token}:{}),...(payload===undefined?{}:{'Content-Type':'application/json'})},...(payload===undefined?{}:{body:JSON.stringify(payload)})});
    let result;try {result=await response.json();}catch{throw new Error(`The server returned an unreadable response (${response.status}).`);}
    if(!response.ok) {const error=new Error(result.error||`Request failed (${response.status}).`);error.status=response.status;throw error;}
    return result;
  }
  function accept(result) {
    const data=result.bootstrap||result.view||result;
    if(data.projects&&data.pm) {ui.data=data;ui.connectors=data.connectors||ui.connectors;if(data.selected_project)ui.projectId=data.selected_project.id;}
  }
  async function refresh() {
    accept(await api('/bootstrap'+(ui.projectId?'?project_id='+encodeURIComponent(ui.projectId):'')));
  }
  async function run(task, success) {
    if(ui.busy)return;
    const previous=snapshot();
    ui.restoreScroll=previous.scrolls;ui.busy=true;ui.notice=null;render();
    try {await task();if(success)ui.notice={text:success};}
    catch(error) {
      if(error.status===401) {sessionStorage.removeItem(sessionKey);ui.token=null;ui.data=null;}
      if(error.status===409||error.status===502)await refresh().catch(()=>{});
      ui.notice={text:error.message,error:true};
    } finally {
      if(ui.restoreScroll===null&&['view','projectId','docId','personId','tab'].every(key=>ui[key]===previous[key]))
        ui.restoreScroll=previous.scrolls;
      ui.busy=false;render();
    }
  }
  async function action(type, fields={}, success='Project document records updated.') {
    await run(async()=>{const r=await api('/action',{expected_version:ui.data.version,action:{type,project_id:project().id,...fields}});accept(r);ui.modal=null;},success);
  }
  async function openProject(id,documentId) {
    if(ui.busy)return;
    clearTimeout(searchTimer);
    const view=documentId?'document':'project';
    if(project().id===id){
      visit(view,{docId:documentId||null,projectId:id,tab:'document',
        ...(!projectViews.includes(ui.view)?{search:'',phase:'all',docFilter:'all'}:{})});
      return;
    }
    const previous=snapshot();
    await run(async()=>{
      accept(await api('/bootstrap?project_id='+encodeURIComponent(id)));
      remember(previous);
      Object.assign(ui,{projectId:id,docId:documentId||null,view,search:'',phase:'all',docFilter:'all',tab:'document',navOpen:false});
    });
    root.querySelector('#main')?.focus({preventScroll:true});
  }
  function preparedEmail(d) {
    const recipients=list(d.recipients), names=recipients.map(r=>r.name).join(', ');
    return {type:'email',mode:'Prepared draft · editable',to:recipients.map(r=>r.email||person(r.id)?.email||person(r.id)?.contact||'').filter(Boolean).join(', '),subject:`${project().name}: ${d.title} · revision ${d.revision}`,body:`Hello ${names||d.owner_name||'team'},\n\nPlease review ${d.title} (revision ${d.revision}) for ${project().name}.\n\n${nextReason(d)}\n\n${d.due_at?'The recorded due date is '+date(d.due_at)+'. Please let me know if this timing is not feasible.\n\n':''}Please reply with any questions or corrections. Formal signature or review acceptance should be recorded through the appropriate document workflow.\n\nThank you,\n${pm().name}`};
  }
  function emailModal(d, mode) {
    const saved=d.email_draft||{};
    return {...preparedEmail(d),...saved,to:list(saved.to).join(', ')||preparedEmail(d).to,type:'email',mode:mode||(saved.mode==='live'?'ChatGPT draft · review before use':'Prepared draft · editable')};
  }
  async function prepareEmail() {
    await run(async()=>{
      accept(await api('/action',{expected_version:ui.data.version,action:{type:'draft_email',project_id:project().id,doc_id:doc().id}}));
      ui.modal=emailModal(doc());
    });
  }
  async function saveEmailDraft() {
    const m=ui.modal;
    await run(async()=>{
      accept(await api('/action',{expected_version:ui.data.version,action:{type:'draft_email',project_id:project().id,doc_id:doc().id,subject:m.subject,body:m.body}}));
      ui.modal=emailModal(doc());
    },'Reviewed email draft saved. No email was sent.');
  }
  async function assist(kind) {
    const d=doc(),key=`${project().id}:${d.id}:${kind}`;
    await run(async()=>{
      ui.job=kind==='draft_email'?'Preparing a fresh ChatGPT email draft…':'Reading this document and its source events with ChatGPT…';render();
      try {
        const started=await api('/assist',{expected_version:ui.data.version,project_id:project().id,doc_id:d.id,kind});
        if(!started.job_id)throw new Error('The server did not return an assistance job.');
        let job;
        do {await new Promise(resolve=>setTimeout(resolve,1300));job=await api('/jobs/'+encodeURIComponent(started.job_id));if(job.status==='failed')throw new Error(job.error||'ChatGPT assistance failed.');}while(['running','queued'].includes(job.status));
        if(job.status!=='completed')throw new Error('The assistance job did not complete.');
        await refresh();
        if(kind==='draft_email')ui.modal=emailModal(doc(),'ChatGPT draft · review before use');
        else {ui.outputs[key]=doc().reading_summary||doc().summary||job.result;ui.tab='document';}
      } finally {ui.job=null;}
    });
  }
  async function connectorAction(operation, provider) {
    await run(async()=>{
      if(operation==='create_email_draft'&&!doc()?.email_draft)throw new Error('Prepare and review a stakeholder email draft first.');
      const result=await api('/connectors',{operation,provider,expected_version:ui.data.version,...(project().id?{project_id:project().id}:{}),...(doc()?.id?{doc_id:doc().id}:{}),request_id:crypto.randomUUID()});
      accept(result);
      if(result.connectors)ui.connectors=result.connectors;
      const details=result.connector_result;
      const issues=list(details?.errors);
      ui.notice={text:issues.length?issues.map(e=>e.message||e.code||'Provider reconciliation needs review.').join(' '):details?.message||details?.detail||(operation==='create_envelope_draft'?'DocuSign draft created. Review its document and signature fields in DocuSign before sending.':'Provider request completed. Review its connection state and source events.'),error:issues.length>0};
    });
  }
  root.addEventListener('click',async event=>{
    const target=event.target.closest('[data-action]');if(!target||target.disabled)return;
    const a=target.dataset.action,id=target.dataset.id;
    if(a==='dismiss'){ui.notice=null;render();return;}
    if(a==='close-modal'){ui.modal=null;render();return;}
    if(a==='close-nav'){closeNavigation();return;}
    if(ui.busy)return;
    if(a==='connection-test'){ui.modal={type:'connection-test'};render();return;}
    if(a==='profile'){ui.modal={type:'profile'};render();return;}
    if(a==='logout'){await api('/logout',{}).catch(()=>{});sessionStorage.removeItem(sessionKey);ui.token=null;ui.data=null;ui.modal=null;ui.projectId=null;ui.history=[];ui.navOpen=false;ui.view='dashboard';render();return;}
    if(a==='nav'){visit(id,{search:''});return;}
    if(a==='back'){if(!ui.busy)await goBack();return;}
    if(a==='toggle-nav'){if(navigationExpanded())closeNavigation();else{ui.navOpen=true;navigation.suppressed=false;syncNavigation();}return;}
    if(a==='map-region'){ui.mapRegion=id;render();return;}
    if(a==='map-priority'){ui.mapPriority=id;render();return;}
    if(a==='queue-filter'){visit('queue',{filter:id});return;}
    if(a==='phase'){visit('register',{phase:id});return;}
    if(a==='tab'){ui.tab=id;render();return;}
    if(a==='stakeholder'){visit('stakeholder',{personId:id});return;}
    if(a==='document'){visit('document',{docId:id,tab:'document'});return;}
    if(a==='register'){visit('register');return;}
    if(a==='compliance'){visit('compliance',{coverageFilter:'all'});return;}
    if(a==='coverage-filter'){ui.coverageFilter=id;render();return;}
    if(['track-requirement','review-requirement'].includes(a)){if(archived())return;ui.modal={type:a,requirementId:id};render();return;}
    if(a==='draft-email'){await prepareEmail();return;}
    if(a==='save-email-draft'){await saveEmailDraft();return;}
    const modals={'edit-document':'edit','revise-document':'revise','void-document':'void','sample-event':'sample','prepare-package':'package','archive-project':'archive','edit-contact':'contact','record-email':'record-email'};
    if(modals[a]){ui.modal={type:modals[a]};render();return;}
    if(a==='copy-draft') {
      const m=ui.modal;
      try {await navigator.clipboard.writeText(`To: ${m.to||''}\nSubject: ${m.subject||''}\n\n${m.body||''}`);target.textContent='Copied';}
      catch {target.textContent='Select and copy the text manually';}return;
    }
    if(a==='download-draft') {
      const m=ui.modal,blob=new Blob([`To: ${m.to||''}\nSubject: ${m.subject||''}\n\n${m.body||''}`],{type:'text/plain;charset=utf-8'}),url=URL.createObjectURL(blob),anchor=document.createElement('a');anchor.href=url;anchor.download='eqore-email-draft.txt';anchor.click();URL.revokeObjectURL(url);return;
    }
    if(ui.busy)return;
    if(a==='refresh'){await run(refresh,'Current records refreshed.');return;}
    if(a==='project'){await openProject(id);return;}
    if(a==='open-action'){const[projectId,documentId]=id.split('|');await openProject(projectId,documentId);return;}
    if(a==='open-compliance'){const[projectId]=id.split('|');await openProject(projectId);if(project().id===projectId)visit('compliance',{coverageFilter:'attention'});return;}
    if(a==='confirm-package'){await action('send_document',{doc_id:id},'Local package prepared. No live signature request or email was sent.');return;}
    if(a==='assist-email'||a==='assist-summary'){await assist(a==='assist-email'?'draft_email':'summary');return;}
    if(a==='refresh-connectors'){await run(async()=>{const r=await api('/connectors');ui.connectors=r.connectors||r;},'Provider connection status refreshed.');return;}
    if(a==='connector-test'){await connectorAction('test',id);return;}
    if(a==='connector-sync'){await connectorAction(id==='docusign'?'sync_envelope':'pull_email',id);return;}
    if(a==='connector-draft'){await connectorAction(id==='docusign'?'create_envelope_draft':'create_email_draft',id);return;}
  });
  let searchTimer;
  root.addEventListener('input',event=>{
    const target=event.target;
    if(target.dataset.draft&&ui.modal){ui.modal[target.dataset.draft]=target.value;return;}
    if(!target.dataset.search)return;
    const key=target.dataset.search,value=target.value,selection=target.selectionStart;
    const sourceView=ui.view,sourceProject=ui.projectId;
    if(key==='archives')ui.archiveSearch=value;else ui.search=value;
    clearTimeout(searchTimer);
    searchTimer=setTimeout(()=>{
      if(ui.view!==sourceView||ui.projectId!==sourceProject)return;
      render();const input=root.querySelector(`[data-search="${key}"]`);input?.focus();input?.setSelectionRange(selection,selection);
    },180);
  });
  root.addEventListener('change',event=>{
    if(event.target.dataset.change==='doc-filter'){ui.docFilter=event.target.value;render();}
  });
  root.addEventListener('submit',async event=>{
    event.preventDefault();if(ui.busy)return;
    const form=event.target,values=new FormData(form);
    if(form.id==='connection-test-form') {
      ui.modal.email=String(values.get('email')||'').trim();
      await run(async()=>{
        const result=await api('/connectors',{operation:'create_connection_draft',provider:'docusign',email:String(values.get('email')||'').trim(),expected_version:ui.data.version});
        accept(result);if(result.connectors)ui.connectors=result.connectors;
        ui.modal=null;const observed=result.connector_result||{};ui.notice={text:`DocuSign connection test ${observed.already_created?'already recorded':observed.recovered?'recovered':'created'}. Last observed status: ${human(observed.envelope_status||'unknown')}. Relay sent no email.`};
      });return;
    }
    if(form.classList.contains('oauth-form')) {
      const provider=form.dataset.provider;
      await run(async()=>{
        const result=await api('/oauth/start',{provider,client_id:String(values.get('client_id')||'').trim()});
        const url=new URL(result.authorization_url);
        if(url.protocol!=='https:'||!['account-d.docusign.com','account.docusign.com','accounts.google.com'].includes(url.hostname))throw new Error('The server returned an unexpected authorization address.');
        location.assign(url.href);
      });
      return;
    }
    if(form.id==='login-form') {
      await run(async()=>{const result=await api('/login',{account_id:values.get('account_id')});if(!result.token)throw new Error('The server did not create a PM session.');ui.token=result.token;sessionStorage.setItem(sessionKey,result.token);await refresh();});return;
    }
    if(form.id==='document-form') {
      const type=ui.modal.type==='edit'?'draft_document':ui.modal.type==='revise'?'revise_document':'void_document';
      await action(type,{doc_id:doc().id,...(values.has('body')?{body:values.get('body')}:{}),...(values.has('reason')?{reason:values.get('reason')}: {})},type==='revise_document'?'New revision saved. Downstream requirements have been rechecked.':'Document record updated.');return;
    }
    if(form.id==='contact-form'){await action('configure_contact',{stakeholder_id:ui.personId,email:values.get('email')},'Project contact updated for future drafts.');return;}
    if(form.id==='email-record-form'){await action('record_email',{doc_id:doc().id,event_id:'local-email-'+crypto.randomUUID(),sender_id:values.get('sender_id'),subject:values.get('subject'),text:values.get('text')},'Original email recorded. Signature and acceptance status are unchanged.');return;}
    if(form.id==='sample-form'){await action('simulate_event',{doc_id:doc().id,event_type:values.get('event_type'),recipient_id:values.get('recipient_id')},'Local sample response recorded with its event provenance.');return;}
    if(form.id==='track-requirement-form') {
      if(archived())return;
      const requirementId=ui.modal.requirementId,previous=snapshot();
      await run(async()=>{
        const dueAt=isoInput(String(values.get('due_at')||''),'Due date');if(!dueAt)throw new Error('Set a due date before tracking this document.');
        accept(await api('/action',{expected_version:ui.data.version,action:{type:'track_requirement',project_id:project().id,requirement_id:requirementId,due_at:dueAt}}));
        const id='C_'+requirementId;
        if(!docs().some(d=>d.id===id))throw new Error('The document was not returned in this project. Refresh the coverage view before trying again.');
        remember(previous);Object.assign(ui,{view:'document',docId:id,tab:'document',modal:null});
      },'Document added. Review the checklist and prepare the project-specific content.');return;
    }
    if(form.id==='requirement-review-form') {
      if(archived())return;
      const requirementId=ui.modal.requirementId;
      await run(async()=>{
        const reviewDueAt=isoInput(String(values.get('review_due_at')||''),'Review date');
        const changedAt=isoInput(String(values.get('changed_at')||''),'Change date'),reason=String(values.get('change_reason')||'').trim();
        if((changedAt&&!reason)||(!changedAt&&reason))throw new Error('Record both the change time and the reason, or leave both blank.');
        const attestReview=values.get('attest_review')==='on',reviewNote=String(values.get('review_note')||'').trim();
        if(attestReview&&!reviewNote)throw new Error('Add a review note before recording the completed review.');
        if(reviewNote&&!attestReview)throw new Error('Confirm the review checkbox to save a completed review, or leave its note blank.');
        accept(await api('/action',{expected_version:ui.data.version,action:{type:'set_requirement_review',project_id:project().id,requirement_id:requirementId,review_due_at:reviewDueAt,...(changedAt?{changed_at:changedAt,change_reason:reason}:{}),...(attestReview?{attest_review:true,review_note:reviewNote}:{})}}));ui.modal=null;
      },'Review schedule and changes saved.');return;
    }
    if(form.id==='archive-form'){await action('archive_project',{attest_project_complete:values.get('complete')==='on',attestation:values.get('attestation')},'Project archived. Its document records are now read-only.');return;}
  });
  document.addEventListener('pointerdown',event=>{
    navigation.keyboardInput=false;navigation.keyboard=false;navigation.pointerType=event.pointerType;
    if(event.pointerType==='touch')navigation.hovered=false;
    syncNavigation();
  },true);
  document.addEventListener('keydown',event=>{
    if(event.key==='Tab'){
      navigation.keyboardInput=true;navigation.suppressed=false;
      navigation.keyboard=Boolean(event.target.closest?.('#workspace-navigation'));
      syncNavigation();
    }
    if(event.key==='Escape'&&ui.modal){ui.modal=null;render();}
    else if(event.key==='Escape'&&navigationExpanded()){closeNavigation();root.querySelector('#main')?.focus({preventScroll:true});}
    if(['Enter',' '].includes(event.key)&&event.target.matches('[role=button]')){event.preventDefault();event.target.dispatchEvent(new MouseEvent('click',{bubbles:true}));}
    if(event.key==='Tab'&&ui.modal){const controls=[...root.querySelectorAll('.modal button:not(:disabled),.modal input,.modal select,.modal textarea,.modal a')],first=controls[0],last=controls[controls.length-1];if(event.shiftKey&&document.activeElement===first){event.preventDefault();last?.focus();}else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first?.focus();}}
  });
  async function start() {
    try {const r=await api('/accounts');ui.accounts=list(r.accounts);ui.accountId=ui.accounts[0]?.id||'';if(ui.token)await refresh();render();}
    catch(error){if(error.status===401){sessionStorage.removeItem(sessionKey);ui.token=null;ui.data=null;}ui.notice={text:error.message,error:true};render();}
  }
  start();
})();
