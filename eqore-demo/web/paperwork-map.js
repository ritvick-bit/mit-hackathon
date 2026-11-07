/* Relay portfolio map. Local SVG only; no map service or address lookup. */
(() => {
  'use strict';
  const WIDTH = 600, HEIGHT = 340, MAX_ZOOM = 32;
  const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const priority = p => (p.priority || 0) >= 90 ? 'urgent' : (p.priority || 0) >= 70 ? 'high' : 'routine';
  const priorityLabel = p => ({urgent:'Urgent', high:'High priority', routine:'Tracking'})[priority(p)];
  let saved = null;
  function project(geo) {
    if(geo?.lat == null || geo?.lng == null || !Number.isFinite(Number(geo.lat)) || !Number.isFinite(Number(geo.lng))) return null;
    if(Number(geo.lat) < 18 || Number(geo.lat) > 72 || Number(geo.lng) < -180 || Number(geo.lng) > -60) return null;
    const raw = (lat, lng) => {
      const rad = Math.PI / 180, n = (Math.sin(29.5 * rad) + Math.sin(45.5 * rad)) / 2;
      const c = Math.cos(29.5 * rad) ** 2 + 2 * n * Math.sin(29.5 * rad);
      const rho = Math.sqrt(c - 2 * n * Math.sin(lat * rad)) / n, theta = n * (lng + 96) * rad;
      return [rho * Math.sin(theta), rho * Math.cos(theta)];
    };
    // Matches /map.svg's Albers outline. Positions are city reference points.
    const a = raw(42.746, -73.264), b = raw(42.05, -73.508), v = raw(Number(geo.lat), Number(geo.lng));
    const scale = ((b[0] - a[0]) * -.3 + (b[1] - a[1]) * 8.5) / ((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2);
    return [530 + (v[0] - a[0]) * scale, 92.4 + (v[1] - a[1]) * scale];
  }
  function render(projects = [], all = projects, options = {}) {
    const indices = new Map(all.map((p, i) => [p.id, i + 1]));
    const records = projects.map(p => ({id:p.id, name:p.name, site:p.site, priority:p.priority || 0, geography:p.geography, number:indices.get(p.id) || 1}));
    const region = options.region === 'NE' ? 'NE' : 'US';
    const config = {records, all:all.map(p => ({id:p.id, geography:p.geography})), region};
    return `<div class="relay-map" data-relay-map="${escape(JSON.stringify(config))}"><div class="relay-map-canvas"><svg class="relay-map-svg" viewBox="0 0 600 340" tabindex="0" role="group" aria-label="Project map" aria-keyshortcuts="+ - ArrowUp ArrowDown ArrowLeft ArrowRight Home"><image href="/map.svg" x="0" y="0" width="600" height="340" aria-hidden="true"/><g class="relay-map-markers"></g></svg><div class="relay-map-controls" aria-label="Map controls"><button type="button" data-map-control="in" title="Zoom in" aria-label="Zoom in">+</button><button type="button" data-map-control="out" title="Zoom out" aria-label="Zoom out">−</button><button type="button" data-map-control="reset" title="Reset map" aria-label="Reset map"><svg viewBox="0 0 20 20" aria-hidden="true"><path d="M4 8a6 6 0 1 1 0 5M4 3v5h5"/></svg></button></div><output class="relay-map-zoom" aria-label="Map zoom">1×</output>${records.some(p => project(p.geography)) ? '' : '<div class="relay-map-empty">No mapped projects</div>'}</div><div class="relay-map-sites" aria-label="Project sites">${records.map(p => `<button type="button" class="relay-map-site" data-action="project" data-id="${escape(p.id)}" title="${escape(p.name)} · ${escape(p.site)}" aria-label="${escape(p.name)}, ${escape(p.site)}, ${priorityLabel(p)}"><span class="relay-map-number ${priority(p)}">${p.number}</span><span class="relay-map-site-name">${escape(p.geography?.city || String(p.site || p.name).split(',')[0])}<small>${escape(p.geography?.state || '')}</small></span></button>`).join('')}</div></div>`;
  }
  function attach(root) {
    root.querySelectorAll('[data-relay-map]').forEach(element => {
      if(element.dataset.mapAttached) return;
      element.dataset.mapAttached = 'true';
      const config = JSON.parse(element.dataset.relayMap);
      const svg = element.querySelector('.relay-map-svg'), layer = element.querySelector('.relay-map-markers');
      const canvas = element.querySelector('.relay-map-canvas'), output = element.querySelector('.relay-map-zoom');
      const points = config.records.map(p => ({...p, point:project(p.geography)})).filter(p => p.point);
      const signature = config.all.map(p => p.id).sort().join('|');
      const same = saved?.signature === signature && saved?.region === config.region;
      const state = same ? {...saved} : {x:300, y:170, zoom:1, signature, region:config.region};
      const pointers = new Map();
      let drag = null, pinch = null, suppressClick = false, suppressTimer = null, clusters = [];
      function baseSize() {
        const rect = svg.getBoundingClientRect(), ratio = Math.max(.1, rect.width / Math.max(1, rect.height));
        const width = Math.max(WIDTH, HEIGHT * ratio);
        return {width, height:width / ratio, pixels:Math.max(1, rect.width)};
      }
      function view() { const base = baseSize(); return {x:state.x - base.width / state.zoom / 2, y:state.y - base.height / state.zoom / 2, width:base.width / state.zoom, height:base.height / state.zoom, pixels:base.pixels}; }
      function constrain() {
        state.zoom = Math.max(1, Math.min(MAX_ZOOM, state.zoom));
        const v = view();
        state.x = v.width >= 680 ? 300 : Math.max(-40 + v.width / 2, Math.min(640 - v.width / 2, state.x));
        state.y = v.height >= 400 ? 170 : Math.max(-30 + v.height / 2, Math.min(370 - v.height / 2, state.y));
      }
      function fit(list) {
        if(!list.length) {state.x = 300; state.y = 170; state.zoom = 1; return;}
        const xs = list.map(p => p.point[0]), ys = list.map(p => p.point[1]), base = baseSize();
        const minX = Math.min(...xs), maxX = Math.max(...xs), minY = Math.min(...ys), maxY = Math.max(...ys);
        state.x = (minX + maxX) / 2; state.y = (minY + maxY) / 2;
        state.zoom = Math.min(MAX_ZOOM, base.width / Math.max(12, (maxX - minX) * 1.6), base.height / Math.max(10, (maxY - minY) * 1.6));
      }
      function reset() {
        state.x = 300; state.y = 170; state.zoom = 1;
        if(config.region === 'NE') fit(config.all.filter(p => Number(p.geography?.lng) > -80 && Number(p.geography?.lat) > 38).map(p => ({point:project(p.geography)})).filter(p => p.point));
        paint();
      }
      function groupPoints(scale) {
        const groups = [];
        points.forEach(p => {
          let group = groups.find(g => Math.hypot(g.x - p.point[0], g.y - p.point[1]) < 30 * scale);
          if(!group) {group = {x:p.point[0], y:p.point[1], members:[]}; groups.push(group);}
          group.members.push(p);
          group.x = group.members.reduce((n, item) => n + item.point[0], 0) / group.members.length;
          group.y = group.members.reduce((n, item) => n + item.point[1], 0) / group.members.length;
        });
        return groups;
      }
      function paint() {
        constrain();
        saved = {...state};
        const v = view(), scale = v.width / v.pixels;
        svg.setAttribute('viewBox', `${v.x} ${v.y} ${v.width} ${v.height}`);
        output.textContent = `${state.zoom < 10 ? state.zoom.toFixed(1).replace(/\.0$/, '') : Math.round(state.zoom)}×`;
        element.querySelector('[data-map-control="in"]').disabled = state.zoom >= MAX_ZOOM;
        element.querySelector('[data-map-control="out"]').disabled = state.zoom <= 1;
        clusters = groupPoints(scale);
        layer.innerHTML = clusters.map((g, index) => {
          const margin = 22 * scale;
          if(g.x < v.x - margin || g.x > v.x + v.width + margin || g.y < v.y - margin || g.y > v.y + v.height + margin) return '';
          const p = g.members.slice().sort((a,b) => b.priority - a.priority)[0], cluster = g.members.length > 1;
          const label = cluster ? `${g.members.length} projects: ${g.members.map(p => p.name).join(', ')}` : `${p.name}, ${p.site}, ${priorityLabel(p)}`;
          return `<g class="relay-map-marker ${priority(p)} ${cluster ? 'is-cluster' : ''}" transform="translate(${g.x} ${g.y}) scale(${scale})" role="button" tabindex="0" ${cluster ? `data-map-cluster="${index}" aria-label="Zoom to ${escape(label)}"` : `data-action="project" data-id="${escape(p.id)}" aria-label="${escape(label)}"`}><title>${escape(label)}</title><circle class="relay-map-hit" r="18"/><circle class="relay-map-dot" r="${cluster ? 14 : 11}"/><text text-anchor="middle" dominant-baseline="central">${cluster ? g.members.length : p.number}</text>${cluster ? '<path class="relay-map-cluster-plus" d="M9 -13h8m-4 -4v8"/>' : ''}</g>`;
        }).join('');
      }
      function at(clientX, clientY) {
        const rect = svg.getBoundingClientRect(), v = view();
        return {x:v.x + (clientX - rect.left) / Math.max(1, rect.width) * v.width, y:v.y + (clientY - rect.top) / Math.max(1, rect.height) * v.height};
      }
      function zoom(factor, clientX, clientY) {
        const rect = svg.getBoundingClientRect(), x = clientX ?? rect.left + rect.width / 2, y = clientY ?? rect.top + rect.height / 2;
        const before = at(x, y);
        state.zoom = Math.max(1, Math.min(MAX_ZOOM, state.zoom * factor));
        const after = at(x, y); state.x += before.x - after.x; state.y += before.y - after.y;
        paint();
      }
      function stopProjectClick() { suppressClick = true; clearTimeout(suppressTimer); suppressTimer = setTimeout(() => {suppressClick = false;}, 450); }
      element.addEventListener('click', event => {
        if(suppressClick && event.target.closest('.relay-map-svg')) {event.preventDefault(); event.stopPropagation(); suppressClick = false; return;}
        const control = event.target.closest('[data-map-control]');
        if(control) {event.preventDefault(); event.stopPropagation(); const name = control.dataset.mapControl; if(name === 'reset') reset(); else zoom(name === 'in' ? 1.5 : 1 / 1.5); return;}
        const marker = event.target.closest('[data-map-cluster]');
        if(marker) {event.preventDefault(); event.stopPropagation(); const group = clusters[Number(marker.dataset.mapCluster)]; if(group) {fit(group.members); paint(); svg.focus({preventScroll:true});}}
      });
      svg.addEventListener('wheel', event => {
        event.preventDefault();
        const delta = event.deltaY * (event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? 300 : 1);
        zoom(Math.exp(-Math.max(-150, Math.min(150, delta)) * .004), event.clientX, event.clientY);
      }, {passive:false});
      svg.addEventListener('pointerdown', event => {
        if(event.pointerType === 'mouse' && event.button !== 0) return;
        pointers.set(event.pointerId, {x:event.clientX, y:event.clientY});
        drag = {id:event.pointerId, x:event.clientX, y:event.clientY, moved:false};
        if(pointers.size === 2) {const [a,b] = [...pointers.values()]; pinch = {distance:Math.hypot(a.x-b.x, a.y-b.y), x:(a.x+b.x)/2, y:(a.y+b.y)/2}; pointers.forEach((_, id) => svg.setPointerCapture(id)); stopProjectClick();}
      });
      svg.addEventListener('pointermove', event => {
        if(!pointers.has(event.pointerId)) return;
        const previous = pointers.get(event.pointerId);
        pointers.set(event.pointerId, {x:event.clientX, y:event.clientY});
        if(pointers.size === 2 && pinch) {
          const [a,b] = [...pointers.values()], midpoint = {x:(a.x+b.x)/2, y:(a.y+b.y)/2}, distance = Math.hypot(a.x-b.x, a.y-b.y);
          const before = at(pinch.x,pinch.y);
          state.zoom = Math.max(1, Math.min(MAX_ZOOM,state.zoom * distance / Math.max(1,pinch.distance)));
          const after = at(midpoint.x,midpoint.y); state.x += before.x-after.x; state.y += before.y-after.y;
          pinch = {distance,...midpoint}; stopProjectClick(); paint(); return;
        }
        if(!drag || drag.id !== event.pointerId) return;
        if(!drag.moved && Math.hypot(event.clientX-drag.x,event.clientY-drag.y) < 4) return;
        drag.moved = true; svg.setPointerCapture(event.pointerId); stopProjectClick(); canvas.classList.add('is-panning');
        const rect = svg.getBoundingClientRect(), v = view();
        state.x -= (event.clientX-previous.x) / Math.max(1,rect.width) * v.width;
        state.y -= (event.clientY-previous.y) / Math.max(1,rect.height) * v.height;
        paint();
      });
      function endPointer(event) {
        pointers.delete(event.pointerId); if(svg.hasPointerCapture(event.pointerId)) svg.releasePointerCapture(event.pointerId);
        if(pointers.size < 2) pinch = null;
        if(pointers.size === 1) {const [id,p] = [...pointers.entries()][0]; drag = {id,x:p.x,y:p.y,moved:true};}
        else {drag = null; canvas.classList.remove('is-panning');}
      }
      svg.addEventListener('pointerup', endPointer); svg.addEventListener('pointercancel', endPointer);
      svg.addEventListener('pointerleave', event => {if(!svg.hasPointerCapture(event.pointerId)) endPointer(event);});
      svg.addEventListener('keydown', event => {
        if(event.target.closest('[role="button"]') && ['Enter',' '].includes(event.key)) {
          event.preventDefault(); event.stopPropagation(); event.target.closest('[role="button"]').dispatchEvent(new MouseEvent('click',{bubbles:true})); return;
        }
        if(['+','=','-','_','Home','ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(event.key)) {
          event.preventDefault(); event.stopPropagation();
          if(['+','='].includes(event.key)) zoom(1.4);
          else if(['-','_'].includes(event.key)) zoom(1/1.4);
          else if(event.key === 'Home') reset();
          else {const v = view(); state.x += ({ArrowLeft:-1,ArrowRight:1}[event.key] || 0) * v.width * .1; state.y += ({ArrowUp:-1,ArrowDown:1}[event.key] || 0) * v.height * .1; paint();}
        }
      });
      if(!same) reset(); else paint();
      const resize = new ResizeObserver(() => {if(element.isConnected) paint(); else resize.disconnect();});
      resize.observe(canvas);
    });
  }
  window.RelayMap = Object.freeze({render, attach});
})();
