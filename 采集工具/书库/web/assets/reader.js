/* ============================================================
   reader.js — 正文阅读页
   URL: read.html?c=<chapterId>
   位置记忆：localStorage 存 {c, para, ratio, ts}
   ============================================================ */

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];

const API = (p, q = {}) => {
  const u = new URL('/api/' + p, location.origin);
  Object.entries(q).forEach(([k, v]) => v != null && u.searchParams.set(k, v));
  return fetch(u).then(r => r.json());
};

const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

/* ---------------- 阅读设置 ---------------- */
const RD = {
  fs: +(localStorage.getItem('rd_fs') || 19),
  lh: +(localStorage.getItem('rd_lh') || 1.75),
  ls: +(localStorage.getItem('rd_ls') || 0.015),
  theme: localStorage.getItem('theme') || 'ink',
  font: localStorage.getItem('rd_font') || 'serif',
};

function applyRD() {
  const r = document.documentElement;
  r.style.setProperty('--rd-fs', RD.fs + 'px');
  r.style.setProperty('--rd-lh', String(RD.lh));
  r.style.setProperty('--rd-ls', RD.ls + 'em');
  r.style.setProperty('--f-serif',
    RD.font === 'hei'
      ? '"Source Han Sans SC","PingFang SC","Microsoft YaHei",system-ui,sans-serif'
      : RD.font === 'kai'
        ? '"LXGW WenKai Screen","Kaiti SC",KaiTi,"Source Han Serif SC",serif'
        : '"Source Han Serif SC","Songti SC",SimSun,"Noto Serif SC",serif');
  r.dataset.theme = RD.theme;
  localStorage.setItem('rd_fs', RD.fs);
  localStorage.setItem('rd_lh', RD.lh);
  localStorage.setItem('rd_ls', RD.ls);
  localStorage.setItem('rd_font', RD.font);
  localStorage.setItem('theme', RD.theme);
  $('#fsVal').textContent = RD.fs;
  $('#lhVal').textContent = RD.lh.toFixed(2);
}

/* ---------------- 章节渲染 ---------------- */
let CUR = null;
let SECTIONS = [];

async function loadChapter(id) {
  const root = $('#rdRoot');
  root.innerHTML = '<p class="no-indent" style="opacity:.5">载入中…</p>';

  const c = await API('chapters/' + id);
  if (c.error) {
    root.innerHTML = '<p class="no-indent">这一节不存在。</p>';
    return;
  }
  CUR = c;

  const paras = String(c.content || '')
    .replace(/\r\n/g, '\n')
    .split('\n')
    .map(s => s.trim())
    .filter(Boolean);

  const html = [
    `<h1>${esc(c.title || ('第 ' + ((c.idx ?? 0) + 1) + ' 节'))}</h1>`,
    ...paras.map(t => `<p>${esc(t)}</p>`),
  ].join('\n');

  root.innerHTML = html;
  root.dataset.chapter = id;

  // 面包屑/标题
  document.title = `${c.work_title || ''} · ${c.title || ''}`;
  $('#barTitle').innerHTML = `<a href="#back"><b>${esc(c.work_title || '')}</b></a>` +
    `<span style="opacity:.5"> · </span>${esc(c.title || '')}`;

  // 章末导航
  const nav = $('#rdNav');
  nav.innerHTML = '';
  nav.append(
    c.prev_id ? mkNav(c.prev_id, c.prev || '上一节', 'prev') : mkNav(null, '已是第一节', 'prev'),
    c.next_id ? mkNav(c.next_id, c.next || '下一节', 'next') : mkNav(null, '全文完', 'next'),
  );

  // 目录高亮 + 位置
  $$('#tocList a').forEach(a =>
    a.setAttribute('aria-current', String(a.dataset.cid) === String(id) ? 'true' : 'false'));

  // 恢复阅读位置
  const saved = JSON.parse(localStorage.getItem('rd_pos_' + id) || 'null');
  if (saved?.para != null) {
    requestAnimationFrame(() => {
      const ps = root.querySelectorAll('p');
      const target = ps[saved.para];
      if (target) target.scrollIntoView({ block: 'center' });
    });
  } else {
    window.scrollTo({ top: 0 });
  }

  $('#tocBtn')?.setAttribute('aria-expanded', 'false');
  $('#rdToc')?.classList.remove('open');

  history.replaceState(null, '', `read.html?c=${id}`);
  observeProgress();
}

function mkNav(c, label, cls) {
  if (!c) {
    const el = document.createElement('a');
    el.className = 'disabled ' + cls;
    el.innerHTML = `<span class="k">${cls === 'prev' ? '上一节' : '下一节'}</span><span>${label}</span>`;
    return el;
  }
  const a = document.createElement('a');
  a.className = cls;
  a.href = `read.html?c=${c}`;
  a.addEventListener('click', e => { e.preventDefault(); loadChapter(c); });
  a.innerHTML = `<span class="k">${cls === 'prev' ? '上一节' : '下一节'}</span><span>${label}</span>`;
  a.dataset.target = c;
  return a;
}

/* ---------------- 进度 ---------------- */
let io = null;
let curPara = 0;

function observeProgress() {
  if (io) io.disconnect();
  const ps = $$('#rdRoot p');
  if (!ps.length) return;

  let anchor = ps[0];
  io = new IntersectionObserver(entries => {
    for (const e of entries) if (e.isIntersecting) anchor = e.target;
    const i = ps.indexOf(anchor);
    if (i >= 0) {
      curPara = i;
      const pct = Math.round(((i + 1) / ps.length) * 100);
      $('#pct').textContent = pct + '%';
      $('#progress').style.width = pct + '%';
      savePos(i, pct);
    }
  }, { rootMargin: '-45% 0px -50% 0px', threshold: 0 });

  ps.forEach(p => io.observe(p));
}

let saveTimer = null;
function savePos(para, pct) {
  clearTimeout(saveTimer);
  saveTimer = setTimeout(() => {
    if (!CUR) return;
    const rec = { c: CUR.id, para, pct, ts: Date.now(), work: CUR.work_title };
    localStorage.setItem('rd_pos_' + CUR.id, JSON.stringify(rec));
    localStorage.setItem('rd_last', JSON.stringify(rec));
  }, 400);
}

/* ---------------- 目录 ---------------- */
async function loadToc(workId) {
  const list = $('#tocList');
  const chs = await API(`works/${workId}/chapters`);
  list.innerHTML = '';
  chs.forEach(c => {
    const li = document.createElement('li');
    const a = document.createElement('a');
    a.href = `read.html?c=${c.id}`;
    a.dataset.cid = c.id;
    a.innerHTML = `<span>${esc(c.title)}</span><span class="dim" style="font-size:11px">${fmtWan(c.char_count)}</span>`;
    a.addEventListener('click', e => {
      e.preventDefault();
      loadChapter(c.id);
      $('#rdToc').classList.remove('open');
    });
    li.append(a);
    list.append(li);
  });
  if (CUR) {
    $$('#tocList a').forEach(a =>
      a.setAttribute('aria-current', String(a.dataset.cid) === String(CUR.id) ? 'true' : 'false'));
  }
}

const fmtWan = n => n >= 10000 ? (n / 10000).toFixed(1) + '万' : String(n);

/* ---------------- 键盘 ---------------- */
function bindKeys() {
  document.addEventListener('keydown', e => {
    if (e.target.matches('input')) return;
    if (e.key === 'ArrowLeft' && CUR?.prev_id) { loadChapter(CUR.prev_id); }
    if (e.key === 'ArrowRight' && CUR?.next_id) { loadChapter(CUR.next_id); }
    if (e.key === 'Escape') {
      $('#rdToc').classList.remove('open');
      $('#rdPanel').classList.remove('open');
    }
  });
}

/* ---------------- 隐私 ---------------- */
function initPrivacy() {
  document.addEventListener('visibilitychange', () =>
    document.body.classList.toggle('veiled', document.hidden));
  window.addEventListener('blur', () => document.body.classList.add('veiled'));
  window.addEventListener('focus', () => setTimeout(() => document.body.classList.remove('veiled'), 120));
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) document.title = '飞行图书馆';
  });
}

/* ---------------- 启动 ---------------- */
async function boot() {
  applyRD();
  initPrivacy();
  bindKeys();

  const id = new URLSearchParams(location.search).get('c');
  if (!id) {
    // 无参数 → 回到最近阅读
    const last = JSON.parse(localStorage.getItem('rd_last') || 'null');
    if (last?.c) return loadChapter(last.c);
    document.getElementById('rdRoot').innerHTML = '<p class="no-indent">没有指定章节。</p>';
    return;
  }

  await loadChapter(id);
  if (CUR?.work_id) loadToc(CUR.work_id);

  // 目录按钮
  $('#tocBtn').addEventListener('click', () => {
    const d = $('#rdToc');
    d.classList.toggle('open');
    if (d.classList.contains('open') && CUR?.work_id) loadToc(CUR.work_id);
  });
  $('#tocClose').addEventListener('click', () => $('#rdToc').classList.remove('open'));

  // 设置面板
  $('#setBtn').addEventListener('click', e => {
    e.stopPropagation();
    $('#rdPanel').classList.toggle('open');
  });
  document.addEventListener('click', e => {
    const p = $('#rdPanel');
    if (p.classList.contains('open') && !p.contains(e.target) && e.target.id !== 'setBtn') {
      p.classList.remove('open');
    }
  });

  $('#fsMinus').addEventListener('click', () => { RD.fs = Math.max(14, RD.fs - 1); applyRD(); });
  $('#fsPlus').addEventListener('click', () => { RD.fs = Math.min(28, RD.fs + 1); applyRD(); });
  $('#lhMinus').addEventListener('click', () => { RD.lh = Math.max(1.5, +(RD.lh - .05).toFixed(2)); applyRD(); });
  $('#lhPlus').addEventListener('click', () => { RD.lh = Math.min(2.2, +(RD.lh + .05).toFixed(2)); applyRD(); });
  $('#fsRange').addEventListener('input', e => { RD.fs = +e.target.value; applyRD(); });
  $$('.theme-dot').forEach(b => b.addEventListener('click', () => { RD.theme = b.dataset.theme; applyRD(); }));
  $$('[data-font]').forEach(b => b.addEventListener('click', () => {
    RD.font = b.dataset.font;
    $$('[data-font]').forEach(x => x.setAttribute('aria-pressed', 'false'));
    b.setAttribute('aria-pressed', 'true');
    applyRD();
  }));

  // 滚动隐藏 dock
  let lastY = 0, hideT;
  window.addEventListener('scroll', () => {
    const y = scrollY;
    const dock = $('#rdDock'), bar = $('.rd-bar');
    clearTimeout(hideT);
    if (y > lastY + 40 && y > 200) {
      dock.classList.add('hide'); bar.classList.add('hide');
    } else if (y < lastY - 20) {
      dock.classList.remove('hide'); bar.classList.remove('hide');
    }
    lastY = y;
  }, { passive: true });
}

boot();
