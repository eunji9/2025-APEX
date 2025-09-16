// dashboard.js — 층 탭 전환 + 3층 동시 폴링 + led.svg 화살표 + 전역신호
//              + 대피오버레이(HTML) + 🔥차단간선 불아이콘(현재 층만/복수 간선 표시)
(() => {
  // === 층별 설정 ===
  const FLOORS = {
    1: { api:'/api/shortest-path/?floor=1', svgId:'svg-floor-1', arrowsId:'arrows-1f', firesId:'fires-1', symbol:'arrow1f', img:'/static/img/floor1.png', arrowSvg:'/static/img/led.svg', rotate:180 },
    2: { api:'/api/shortest-path/?floor=2', svgId:'svg-floor-2', arrowsId:'arrows-2f', firesId:'fires-2', symbol:'arrow2f', img:'/static/img/floor2.png', arrowSvg:'/static/img/led.svg', rotate:180 },
    3: { api:'/api/shortest-path/?floor=3', svgId:'svg-floor-3', arrowsId:'arrows-3f', firesId:'fires-3', symbol:'arrow3f', img:'/static/img/floor3.png', arrowSvg:'/static/img/led.svg', rotate:180 },
  };

  // === 신호 관련 ===
  const SIGNAL_CODES = new Set(['1','2','3','4','5','6']);
  function hasActiveSignal(data) {
    const code = data && String(data.last_code || '');
    const ex   = data && data.excluded_edges;
    if (code && SIGNAL_CODES.has(code)) return true;
    if (Array.isArray(ex) && ex.length > 0) return true;
    return false;
  }
  let globalSignalActive = false; // 한 층이라도 신호가 있으면 true

  // 🔥 불아이콘을 현재 층에만 보이게 할지 여부
  const FIRE_ONLY_CURRENT_FLOOR = true;

  // === 상태 ===
  let current = 1;
  let timer = null;
  const sigMap = { 1:'', 2:'', 3:'' };       // 화살표 결과 시그니처
  const arrowDef = {};                       // floor -> { type:'symbol'|'image' }
  let evacActive = false;                    // 대피 오버레이 토글
  const lastExcluded = {1:[], 2:[], 3:[]};   // 최근 층별 차단간선 캐시

  // === 유틸 ===
  const sig = (d)=>{ try { return JSON.stringify(d); } catch { return Math.random()+''; } };
  const deg = (x1,y1,x2,y2)=> Math.atan2(y2-y1, x2-x1) * 180/Math.PI;
  const mid = (x1,y1,x2,y2)=> ({ x:(x1+x2)/2, y:(y1+y2)/2 });
  const keyPair = (a,b)=>{ a=String(a).trim(); b=String(b).trim(); return (a<=b)? `${a}-${b}` : `${b}-${a}`; };

  // === led.svg를 <symbol>로 주입 (실패 시 <image>) ===
  async function ensureSymbol(floor) {
    if (arrowDef[floor]) return arrowDef[floor];
    const { svgId, symbol, arrowSvg } = FLOORS[floor];
    const svg = document.getElementById(svgId);
    if (!svg) return null;
    let defs = svg.querySelector('defs');
    if (!defs) { defs = document.createElementNS('http://www.w3.org/2000/svg','defs'); svg.insertBefore(defs, svg.firstChild); }
    try {
      const txt = await fetch(arrowSvg, { mode:'cors' }).then(r=>{ if(!r.ok) throw new Error('HTTP '+r.status); return r.text(); });
      const doc = new DOMParser().parseFromString(txt, 'image/svg+xml');
      const srcSvg = doc.documentElement;
      const vb = srcSvg.getAttribute('viewBox') || (()=> {
        const w = srcSvg.getAttribute('width')||'24', h = srcSvg.getAttribute('height')||'24';
        return `0 0 ${parseFloat(w)} ${parseFloat(h)}`;
      })();
      const sym = document.createElementNS('http://www.w3.org/2000/svg','symbol');
      sym.setAttribute('id', symbol); sym.setAttribute('viewBox', vb);
      Array.from(srcSvg.childNodes).forEach(n=>{ if(n.nodeType===1) sym.appendChild(n.cloneNode(true)); });
      defs.appendChild(sym);
      arrowDef[floor] = { type:'symbol' };
    } catch {
      arrowDef[floor] = { type:'image' };
    }
    return arrowDef[floor];
  }

  // === 화살표 1개 배치 ===
  function placeArrow(floor, g, x1,y1,x2,y2) {
    const { rotate, symbol, arrowSvg } = FLOORS[floor];
    const m = mid(x1,y1,x2,y2);
    const a = deg(x1,y1,x2,y2) + (rotate||0);
    const size = 24;
    const grp = document.createElementNS('http://www.w3.org/2000/svg','g');
    grp.setAttribute('class','arrow-g');
    grp.setAttribute('transform', `translate(${m.x},${m.y}) rotate(${a}) translate(${-size/2},${-size/2})`);
    if (arrowDef[floor]?.type === 'symbol') {
      const use = document.createElementNS('http://www.w3.org/2000/svg','use');
      use.setAttribute('class','arrow-use');
      use.setAttribute('href', `#${symbol}`);
      use.setAttributeNS('http://www.w3.org/1999/xlink','xlink:href', `#${symbol}`);
      use.setAttribute('width', size); use.setAttribute('height', size);
      grp.appendChild(use);
    } else {
      const im = document.createElementNS('http://www.w3.org/2000/svg','image');
      im.setAttribute('class','arrow-img');
      im.setAttribute('href', arrowSvg);
      im.setAttributeNS('http://www.w3.org/1999/xlink','xlink:href', arrowSvg);
      im.setAttribute('width', size); im.setAttribute('height', size);
      grp.appendChild(im);
    }
    g.appendChild(grp);
  }

  // === 층 결과 적용: all_edges_dir → 화살표 렌더 ===
  async function applyFloor(floor, dirs) {
    const { svgId, arrowsId } = FLOORS[floor];
    const svg = document.getElementById(svgId);
    if (!svg) return;

    let g = document.getElementById(arrowsId);
    if (!g) {
      g = document.createElementNS('http://www.w3.org/2000/svg','g');
      g.setAttribute('id', arrowsId);
      svg.appendChild(g);
    }

    // 배경 간선 흐리게
    svg.querySelectorAll('.edge').forEach(el => { el.style.opacity = 0.25; });

    await ensureSymbol(floor);
    g.innerHTML = '';

    for (const trip of (dirs || [])) {
      let [u, v, d] = trip.map(String);
      const base =
        svg.querySelector(`#edge-${floor}-${u}-${v}`) ||
        svg.querySelector(`#edge-${floor}-${v}-${u}`);
      if (!base) continue;

      let x1 = +base.getAttribute('x1'), y1 = +base.getAttribute('y1');
      let x2 = +base.getAttribute('x2'), y2 = +base.getAttribute('y2');
      if (d === '1') { const tx = x1, ty = y1; x1 = x2; y1 = y2; x2 = tx; y2 = ty; }

      placeArrow(floor, g, x1,y1,x2,y2);
    }
  }

  // === 🔥 차단 간선(불 아이콘) 토글 ===
  // HTML: 각 층 SVG에 <g id="fires-1|2|3">, 내부에 <image data-edge="u-v"> 를 간선마다 배치
  function getFireLayer(floor) {
    const { svgId, firesId } = FLOORS[floor];
    const svg = document.getElementById(svgId);
    if (!svg) return null;
    return svg.querySelector(`#${firesId}`);
  }

  function updateFiresForFloor(floor, excludedEdges) {
    const layer = getFireLayer(floor);
    if (!layer) return;

    // 현재 층만 보이게 할지 여부
    const visibleForThisFloor = !FIRE_ONLY_CURRENT_FLOOR || (floor === current);

    // 차단 간선 집합(정규화: 'min-max' 키)
    const blocked = new Set();
    if (Array.isArray(excludedEdges)) {
      for (const it of excludedEdges) {
        if (!it) continue;
        // ["u","v"] or {u:..., v:...} or {from:..., to:...}
        const u = Array.isArray(it) ? it[0] : (it.u ?? it.from);
        const v = Array.isArray(it) ? it[1] : (it.v ?? it.to);
        if (u == null || v == null) continue;
        blocked.add(keyPair(u, v));
      }
    }

    // 레이어 내 모든 아이콘을 순회하며 on/off
    layer.querySelectorAll('[data-edge]').forEach(el => {
      const val = el.getAttribute('data-edge') || '';
      const [a, b] = val.split('-').map(s => s.trim());
      const k = keyPair(a, b);
      const show = visibleForThisFloor && blocked.has(k);
      el.style.display = show ? 'block' : 'none';
    });
  }

  // === 대피 오버레이: HTML의 <g id="evac-층">만 토글 ===
  function getEvacGroup(floor) {
    return document.querySelector(`#svg-floor-${floor} #evac-${floor}`);
  }
  function updateEvacVisibility() {
    for (const f of [1,2,3]) {
      const g = getEvacGroup(f);
      if (!g) continue;
      g.style.display = (evacActive && f === current) ? 'block' : 'none';
    }
  }

  // === 한 번에 3층 모두 갱신 ===
  async function refreshAllFloorsOnce() {
    const reqs = [1,2,3].map(f =>
      fetch(FLOORS[f].api, { cache:'no-store' })
        .then(r => (r.ok ? r.json() : null))
        .catch(() => null)
    );
    const res = await Promise.all(reqs);
    const dataByFloor = { 1: res[0] || {}, 2: res[1] || {}, 3: res[2] || {} };

    // 전역 신호 여부
    globalSignalActive = [1,2,3].some(f => hasActiveSignal(dataByFloor[f]));

    // 각 층 렌더/불아이콘 토글
    for (const f of [1,2,3]) {
      const data = dataByFloor[f] || {};
      const dirs = data.all_edges_dir || [];
      const exs  = data.excluded_edges || [];

      // 🔥 불아이콘: 층별 여러 간선을 동시에 표시
      lastExcluded[f] = exs;
      updateFiresForFloor(f, lastExcluded[f]);

      // 화살표 렌더 (전역/개별 신호 중 하나라도 있으면 그림)
      const shouldDraw = globalSignalActive || hasActiveSignal(data);
      if (!shouldDraw) {
        const g = document.getElementById(FLOORS[f].arrowsId);
        if (g) g.innerHTML = '';
        sigMap[f] = '';
        continue;
      }

      const s = sig(dirs);
      if (s !== sigMap[f]) {
        sigMap[f] = s;
        await applyFloor(f, dirs);
      }
    }

    // 상태표시
    const st = document.getElementById('modeIndicator');
    if (st) {
      st.style.display = 'block';
      st.textContent = `Floor ${current} 업데이트: ${new Date().toLocaleTimeString()} (전역신호: ${globalSignalActive ? 'ON' : 'OFF'})`;
    }
  }

  function startPolling() {
    if (timer) clearInterval(timer);
    const tick = async () => { try { await refreshAllFloorsOnce(); } catch {} };
    tick();                          // 즉시 1회
    timer = setInterval(tick, 1000); // 1초 폴링
  }

  // === 탭 전환 ===
  window.switchFloor = function (floor) {
    if (!FLOORS[floor]) return;
    current = floor;

    // 탭 UI
    document.querySelectorAll('.floor-tab').forEach(b => b.classList.remove('active'));
    const idx = floor - 1;
    const btn = document.querySelectorAll('.floor-tab')[idx];
    if (btn) btn.classList.add('active');

    const img = document.getElementById('floorImage');
    if (img) { img.src = FLOORS[floor].img; img.alt = `${floor}F`; }

    // 층 SVG 표시 전환
    Object.entries(FLOORS).forEach(([f, info]) => {
      const el = document.getElementById(info.svgId);
      if (!el) return;
      el.classList.toggle('hidden', Number(f) !== floor);
    });

    // 🔥 현재 층만 보기 옵션이므로, 전환 즉시 반영
    for (const f of [1,2,3]) updateFiresForFloor(f, lastExcluded[f]);

    // 대피 오버레이 반영
    updateEvacVisibility();
  };

  // (옵션) 우측 버튼들
  window.startTrainingMode = () => {
    const m = document.getElementById('modeIndicator');
    if (m) { m.style.display = 'block'; m.textContent = '가상훈련 모드'; }
  };
  window.startEvacuationMode = () => {
    evacActive = !evacActive;
    updateEvacVisibility();
    const m = document.getElementById('modeIndicator');
    if (m) { m.style.display = 'block'; m.textContent = evacActive ? '건물대피 ON' : '건물대피 OFF'; }
  };
  window.resetMode = async () => {
  try {
    // 전체 층 초기화 (특정 층만이면 ?floors=1 같은 식으로)
    await fetch('/api/api/reset-exclusions/?floors=1,2,3', { cache: 'no-store' }); // GET로 CSRF 회피
    // await fetch('/api/reset-exclusions/?floors=1,2,3', { cache: 'no-store' }); // 명시도 가능
  } catch (e) {
    console.warn('[reset] request failed:', e);
  }

  // 클라이언트 상태/표시 초기화
  try {
    // 전역 신호 꺼서 화살표가 바로 안 보이게
    if (typeof globalSignalActive !== 'undefined') globalSignalActive = false;

    // 층별 시그니처 리셋 + 화살표/불아이콘 제거
    [1,2,3].forEach(f => {
      if (typeof sigMap !== 'undefined') sigMap[f] = '';
      const cfg = FLOORS[f];
      const g = document.getElementById(cfg.arrowsId);
      if (g) g.innerHTML = '';

      // 불아이콘도 숨김 (사용 중일 때만)
      if (typeof lastExcluded !== 'undefined') lastExcluded[f] = [];
      if (typeof updateFiresForFloor === 'function') updateFiresForFloor(f, []);
    });

    // 상태 문구
    const m = document.getElementById('modeIndicator');
    if (m) { m.style.display = 'block'; m.textContent = '초기화 완료'; }
  } catch (e) {
    console.warn('[reset] ui reset failed:', e);
  }
};

  // 초기 진입
  document.addEventListener('DOMContentLoaded', () => {
    fetch(FLOORS[1].arrowSvg, { cache:'no-store' })
      .then(r => { if (!r.ok) console.warn('led.svg 경로 확인 필요:', FLOORS[1].arrowSvg, r.status); })
      .catch(e => console.warn('led.svg 로드 실패:', e));

    switchFloor(1);
    startPolling();
  });
})();
