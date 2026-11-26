/* ÉnergiTN — utilitaires partagés (i18n, formats, graphiques, ruban de prévision, requêtes). */
(function () {
  const I = JSON.parse(document.getElementById('i18n').textContent);
  const lang = document.documentElement.lang === 'ar' ? 'ar' : 'fr';
  const loc = lang === 'ar' ? 'ar-TN-u-nu-latn' : 'fr-FR';
  const t = (k, vars) => {
    let s = I[k] ?? k;
    if (vars) for (const [a, b] of Object.entries(vars)) {
      // français : « de octobre » -> « d'octobre »
      if (lang === 'fr' && /^[aeiouyéèêâîôûh]/i.test(String(b))) s = s.split('de {' + a + '}').join("d'{" + a + '}');
      s = s.split('{' + a + '}').join(b);
    }
    return s;
  };
  const num = (x, d = 1) => x == null || isNaN(x) ? '–' : Number(x).toLocaleString(loc, { maximumFractionDigits: d, minimumFractionDigits: 0 });
  const pd = s => new Date(String(s).slice(0, 10) + 'T12:00:00');
  const date = (s, o = { day: 'numeric', month: 'short' }) => pd(s).toLocaleDateString(loc, o);
  const wday = s => pd(s).toLocaleDateString(loc, { weekday: 'short' });
  const month = (ym, o = { month: 'long', year: 'numeric' }) => new Date(ym + '-15T12:00:00').toLocaleDateString(loc, o);
  const iso = d => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  const isTomorrow = s => { const d = new Date(); d.setDate(d.getDate() + 1); return String(s).slice(0, 10) === iso(d); };
  /** « Demain » si la date est réellement demain, sinon « J+n » (données de démonstration arrêtées à une date passée). */
  const isToday = s => String(s).slice(0, 10) === iso(new Date());
  /** « Aujourd'hui » / « Demain » si c'est réellement le cas, sinon « J+n » (n = jours après le dernier relevé). */
  const relDay = (s, n) => isToday(s) ? t('today_lbl') : isTomorrow(s) ? t('tomorrow') : t('jplus', {n});
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const css = v => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const data = id => { const e = document.getElementById(id); return e ? JSON.parse(e.textContent) : null; };
  const csrf = () => (document.cookie.match(/csrftoken=([^;]+)/) || [])[1] || ($('[name=csrfmiddlewaretoken]') || {}).value || '';

  async function post(url, body, isForm) {
    const r = await fetch(url, {
      method: 'POST', credentials: 'same-origin',
      headers: isForm ? { 'X-CSRFToken': csrf() } : { 'Content-Type': 'application/json', 'X-CSRFToken': csrf() },
      body: isForm ? body : JSON.stringify(body || {})
    });
    let j = {};
    try { j = await r.json(); } catch (e) { j = { error: 'e_server' }; }
    if (!r.ok && !j.error) j.error = 'e_server';
    return j;
  }
  async function get(url) { const r = await fetch(url, { credentials: 'same-origin' }); return r.json(); }

  let toastTimer;
  function toast(msg, err) {
    let el = $('#toast');
    if (!el) { el = document.createElement('div'); el.id = 'toast'; el.className = 'toast'; el.setAttribute('role', 'status'); document.body.appendChild(el); }
    el.textContent = msg; el.classList.toggle('err', !!err); el.classList.add('on');
    clearTimeout(toastTimer); toastTimer = setTimeout(() => el.classList.remove('on'), 3800);
  }

  // ---------------------------------------------------------------- couleur de chaleur (ruban)
  const STOPS = [[18, [58, 111, 196]], [24, [127, 160, 201]], [29, [233, 195, 90]], [34, [233, 164, 0]], [40, [212, 88, 31]]];
  function heat(tmax) {
    if (tmax == null) return 'rgb(127,160,201)';
    const v = Math.max(STOPS[0][0], Math.min(STOPS[STOPS.length - 1][0], tmax));
    for (let i = 1; i < STOPS.length; i++) {
      if (v <= STOPS[i][0]) {
        const [a, ca] = STOPS[i - 1], [b, cb] = STOPS[i], k = (v - a) / (b - a);
        return 'rgb(' + ca.map((c, j) => Math.round(c + (cb[j] - c) * k)).join(',') + ')';
      }
    }
    return 'rgb(212,88,31)';
  }

  /** Ruban de prévision : une colonne par jour, hauteur = kWh prévus, couleur = chaleur prévue, bande = intervalle q10–q90. */
  function ribbon(el, fc, opts = {}) {
    if (!fc || !fc.length) { el.innerHTML = `<p class="mute">${t('no_forecast')}</p>`; return; }
    const H = opts.height || 150;
    const max = Math.max(...fc.map(f => f.q90 ?? f.pred)) * 1.03, min = Math.max(0, Math.min(...fc.map(f => f.q10 ?? f.pred)) * 0.7);
    const pk = fc.reduce((a, f, i) => f.pred > fc[a].pred ? i : a, 0);
    const y = v => Math.max(18, (v - min) / (max - min) * H);
    el.innerHTML = fc.map((f, i) => {
      const h = y(f.pred), lo = f.q10 != null ? y(f.q10) : null, hi = f.q90 != null ? y(f.q90) : null;
      const band = lo != null && hi != null ? `<span class="band" style="bottom:${lo - 2}px;height:${Math.max(3, hi - lo)}px"></span>` : '';
      return `<div class="rb${i === pk ? ' peak' : ''}" title="${esc(date(f.date, { weekday: 'long', day: 'numeric', month: 'long' }))} : ${num(f.pred)} kWh (${num(f.q10)}–${num(f.q90)})">
        <span class="flag-row">${i === pk ? `<span class="flag">${t('peak')}</span>` : ''}</span>
        <span class="kwh num">${num(f.pred)}<small>kWh</small></span>
        <div style="height:${H}px;display:flex;align-items:flex-end;width:100%;position:relative">
          <div class="col" style="--i:${i};--heat:${heat(f.tmax)};height:${h}px;width:100%">${band}</div>
        </div>
        <span class="day"><b>${opts.tomorrow ? esc(relDay(f.date, i + 1)) : esc(wday(f.date))}</b>${esc(wday(f.date))} ${esc(date(f.date))}</span>
        ${f.tmax != null ? `<span class="t num">${num(f.tmax, 0)}°C</span>` : ''}
      </div>`;
    }).join('');
  }

  // ---------------------------------------------------------------- Chart.js : thème commun
  function chartTheme() {
    if (!window.Chart) return;
    Chart.defaults.font.family = css('--font') || 'system-ui';
    Chart.defaults.font.size = 12;
    Chart.defaults.color = css('--mute');
    Chart.defaults.borderColor = css('--line');
    Chart.defaults.plugins.legend.display = false;
    Chart.defaults.plugins.tooltip.backgroundColor = css('--ink');
    Chart.defaults.plugins.tooltip.titleColor = css('--chaux');
    Chart.defaults.plugins.tooltip.bodyColor = css('--chaux');
    Chart.defaults.plugins.tooltip.padding = 10;
    Chart.defaults.plugins.tooltip.cornerRadius = 8;
    Chart.defaults.plugins.tooltip.rtl = lang === 'ar';
    Chart.defaults.plugins.tooltip.textDirection = lang === 'ar' ? 'rtl' : 'ltr';
    Chart.defaults.maintainAspectRatio = false;
    Chart.defaults.animation.duration = 450;
    Chart.defaults.interaction = { mode: 'index', intersect: false };
    Chart.defaults.elements.bar.borderRadius = 4;
    Chart.defaults.elements.line.borderWidth = 2;
    Chart.defaults.elements.point.radius = 0;
    Chart.defaults.elements.point.hoverRadius = 5;
    Chart.defaults.scale.grid.color = css('--line');
    Chart.defaults.scale.border = { display: false };
  }
  const charts = {};
  function chart(id, cfg) {
    const el = document.getElementById(id);
    if (!el || !window.Chart) return null;
    if (charts[id]) charts[id].destroy();
    charts[id] = new Chart(el, cfg);
    return charts[id];
  }
  const series = i => css('--s' + ((i % 6) + 1));
  const alpha = (c, a) => {
    const m = c.match(/^#([0-9a-f]{6})$/i);
    if (m) { const n = parseInt(m[1], 16); return `rgba(${n >> 16},${(n >> 8) & 255},${n & 255},${a})`; }
    return c.replace('rgb(', 'rgba(').replace(')', `,${a})`);
  };

  // ---------------------------------------------------------------- interface
  function shell() {
    const tb = $('#theme-btn');
    if (tb) tb.addEventListener('click', () => {
      const cur = document.documentElement.dataset.theme || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
      const next = cur === 'dark' ? 'light' : 'dark';
      document.documentElement.dataset.theme = next;
      try { localStorage.setItem('theme', next); } catch (e) { }
      chartTheme();
      document.dispatchEvent(new CustomEvent('themechange'));
    });
    const nb = $('#nav-btn');
    if (nb) nb.addEventListener('click', () => { document.body.classList.toggle('nav-open'); nb.setAttribute('aria-expanded', document.body.classList.contains('nav-open')); });
    document.addEventListener('click', e => { if (document.body.classList.contains('nav-open') && !e.target.closest('.side') && !e.target.closest('#nav-btn')) document.body.classList.remove('nav-open'); });
    document.addEventListener('keydown', e => { if (e.key === 'Escape') document.body.classList.remove('nav-open'); });
    $$('[data-pw]').forEach(b => b.addEventListener('click', () => {
      const inp = document.getElementById(b.dataset.pw); const show = inp.type === 'password';
      inp.type = show ? 'text' : 'password'; b.setAttribute('aria-label', show ? t('hide_pw') : t('show_pw')); b.setAttribute('aria-pressed', show);
    }));
  }
  const sevBadge = s => `<span class="badge ${s === 'haute' ? 'b-high' : s === 'moyenne' ? 'b-mid' : 'b-low'}"><svg class="i"><use href="#i-alert"/></svg>${t('sev_' + s)}</span>`;

  window.EN = { t, lang, loc, num, date, wday, relDay, isTomorrow, isToday, month, pd, esc, css, $, $$, data, post, get, toast, heat, ribbon, chart, chartTheme, series, alpha, sevBadge };
  chartTheme();
  shell();
})();
