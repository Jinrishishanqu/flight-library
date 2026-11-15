/* ============================================================
   app.js — 书架 / 详情 / 搜索 / 标签
   hash 路由：#/  #/work/12  #/search?q=xx  #/tags
   ============================================================ */

const API = (p, q = {}) => {
  const u = new URL('/api/' + p, location.origin);
  Object.entries(q).forEach(([k, v]) => v != null && v !== '' && u.searchParams.set(k, v));
  return fetch(u).then(r => r.json());
};

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];

function h(tag, attrs = {}, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v == null || v === false) continue;
    if (k === 'class') e.className = v;
    else if (k === 'html') e.innerHTML = v;
    else if (k.startsWith('on')) e.addEventListener(k.slice(2), v);
    else e.setAttribute(k, v === true ? '' : v);
  }
  for (const c of kids.flat()) {
    if (c == null || c === false) continue;
    e.append(c.nodeType ? c : document.createTextNode(c));
  }
  return e;
}

/* ---------------- 主题 ---------------- */
const THEMES = ['ink', 'paper', 'indigo'];
function applyTheme(t) {
  document.documentElement.dataset.theme = t;
  localStorage.setItem('theme', t);
  $$('[data-theme-btn]').forEach(b => b.setAttribute('aria-pressed', b.dataset.themeBtn === t));
  $$('.theme-dot').forEach(b => b.setAttribute('aria-pressed', b.dataset.theme === t));
}
function initTheme() {
  applyTheme(localStorage.getItem('theme') || 'ink');
}

/* ---------------- 工具 ---------------- */
const fmtWan = n => n >= 10000 ? (n / 10000).toFixed(n >= 100000 ? 0 : 1) + ' 万' : String(n);
const clothOf = title => {
  let s = 0;
  for (const ch of title) s = (s * 31 + ch.codePointAt(0)) >>> 0;
  return `var(--cloth-${(s % 6) + 1})`;
};
const coverText = title => title.replace(/[《》「」\s]/g, '').slice(0, 6);

function coverEl(w, withBadge = true) {
  const cv = h('div', { class: 'cover', style: `background:${clothOf(w.title)}` },
    h('div', { class: 'stack' }, coverText(w.title)));
  if (withBadge) cv.append(h('span', { class: 'badge' }, fmtWan(w.char_count) + ' 字'));
  return cv;
}

/* ---------------- 状态 ---------------- */
const state = {
  q: '', source: '', genre: '', tag: '', char: '', status: '',
  min: '', max: '', sort: 'chars', page: 1, view: 'grid',
};

/* ---------------- 书架 ---------------- */
async function renderShelf() {
  const root = $('#view');
  root.replaceChildren(h('div', { class: 'empty' }, h('span', { class: 'spinner' })));
  const data = await API('works', {
    q: state.q, source: state.source, genre: state.genre, tag: state.tag,
    char: state.char, status: state.status, min: state.min, max: state.max,
    sort: state.sort, page: state.page, size: 60,
  });

  const head = h('div', { class: 'toolbar' },
    h('span', { class: 'count' }, `${data.total} 部作品`),
    h('span', { class: 'spacer' }),
    h('div', { class: 'seg' },
      ...[['chars', '字数'], ['title', '书名'], ['recent', '新入库']].map(([k, t]) =>
        h('button', {
          'aria-pressed': state.sort === k,
          onclick: () => { state.sort = k; state.page = 1; renderShelf(); },
        }, t))),
    h('div', { class: 'seg' },
      ...[['grid', '网格'], ['list', '列表']].map(([k, t]) =>
        h('button', {
          'aria-pressed': state.view === k,
          onclick: () => { state.view = k; renderShelf(); },
        }, t))),
    h('button', { class: 'btn', onclick: () => openDrawer() }, '筛选'),
  );

  let list;
  if (state.view === 'grid') {
    list = h('div', { class: 'grid' }, ...data.items.map(w =>
      h('a', { class: 'card', href: `#/work/${w.id}` },
        coverEl(w),
        h('div', { class: 'card-title' }, w.title),
        h('div', { class: 'card-meta' },
          h('span', {}, w.source_work || w.genre || '未归类'),
          h('span', {}, '·'),
          h('span', {}, w.chapter_count + ' 节')))));
  } else {
    list = h('div', { class: 'list' }, ...data.items.map(w =>
      h('a', { class: 'row', href: `#/work/${w.id}` },
        h('div', {},
          h('div', { class: 'row-title' }, w.title),
          h('div', { class: 'row-sub' },
            [w.source_work, w.author, w.genre, w.status].filter(Boolean).join(' · '))),
        h('div', { class: 'row-num' }, fmtWan(w.char_count)),
        h('div', { class: 'row-num' }, w.chapter_count + ' 节'))));
  }

  root.replaceChildren(head, chipsEl(), list);
  if (!data.items.length) root.append(h('div', { class: 'empty' }, '没有符合条件的作品'));
  window.scrollTo({ top: 0 });
}

function chipsEl() {
  const items = [];
  if (state.q) items.push(['q', `“${state.q}”`]);
  for (const v of splitVals(state.source)) items.push(['source', v === '_none' ? '未归类' : v, v]);
  if (state.genre) items.push(['genre', state.genre]);
  for (const v of splitVals(state.tag)) items.push(['tag', v, v]);
  for (const v of splitVals(state.char)) items.push(['char', `角色：${v}`, v]);
  if (state.status) items.push(['status', state.status]);
  if (state.min) items.push(['min', `≥${fmtWan(+state.min)}字`]);
  if (state.max) items.push(['max', `≤${fmtWan(+state.max)}字`]);
  if (!items.length) return h('div', { class: 'chips hidden' });
  return h('div', { class: 'chips' },
    ...items.map(([k, label, val]) =>
      h('span', { class: 'chip accent' }, label,
        h('button', {
          onclick: () => {
            if (val === undefined) state[k] = '';
            else state[k] = splitVals(state[k]).filter(x => x !== val).join(',');
            state.page = 1; syncFilterUI(); renderShelf();
          },
          'aria-label': '移除筛选',
        }, '×'))),
    h('button', { class: 'btn', style: 'height:24px;font-size:12px', onclick: resetFilters }, '清除全部'));
}

function resetFilters() {
  Object.assign(state, { q: '', source: '', genre: '', tag: '', char: '', status: '', min: '', max: '' });
  state.page = 1;
  syncFilterUI();
  renderShelf();
}

/* ---------------- 筛选抽屉 ---------------- */
let META = null;
async function ensureMeta() {
  if (META) return META;
  const [sources, tags, chars] = await Promise.all([API('sources'), API('tags'), API('characters')]);
  META = { sources, tags, chars };
  return META;
}

async function openDrawer() {
  const meta = await ensureMeta();
  const d = $('#drawer'), b = $('#drawerBackdrop');
  const body = $('.body', d);

  const opts = (key, list, fmt) => h('div', { class: 'opts' }, ...list.map(([v, label, n]) =>
    h('button', {
      class: 'opt',
      'aria-pressed': state[key] === v,
      onclick: (e) => {
        state[key] = state[key] === v ? '' : v;
        state.page = 1;
        $$('.opt', e.target.parentElement).forEach(o => o.setAttribute('aria-pressed', 'false'));
        if (state[key]) e.target.setAttribute('aria-pressed', 'true');
        renderShelf();
      },
    }, label, n != null ? h('span', { class: 'n', style: 'opacity:.55;margin-left:4px' }, n) : null)));

  body.replaceChildren(
    h('div', { class: 'field' },
      h('span', { class: 'label' }, '原作'),
      opts('source', [
        ...meta.sources.map(s => [s.name === '未归类' ? '_none' : s.name, s.name, s.works]),
      ])),
    h('div', { class: 'field' },
      h('span', { class: 'label' }, '类型'),
      opts('genre', [...new Set(['同人', '原创', '短篇集'])].map(g => [g, g]))),
    h('div', { class: 'field' },
      h('span', { class: 'label' }, '完成度'),
      opts('status', [['完', '完结'], ['合集', '合集'], ['未完', '未完']])),
    h('div', { class: 'field' },
      h('span', { class: 'label' }, '篇幅（字）'),
      h('div', { class: 'range-row' },
        h('input', {
          type: 'number', placeholder: '最小', value: state.min,
          oninput: e => { state.min = e.target.value; state.page = 1; renderShelf(); },
        }),
        h('span', { class: 'dimmer' }, '—'),
        h('input', {
          type: 'number', placeholder: '最大', value: state.max,
          oninput: e => { state.max = e.target.value; state.page = 1; renderShelf(); },
        }))),
    h('div', { class: 'field' },
      h('span', { class: 'label' }, '角色'),
      h('input', {
        type: 'search', class: 'char-filter', placeholder: '搜角色名…',
        oninput: (e) => fillChars(e.target.value.trim()),
      }),
      h('div', { class: 'opts charopts' })),
    h('div', { class: 'field' },
      h('span', { class: 'label' }, '标签'),
      h('div', { class: 'opts' },
        ...meta.tags.slice(0, 40).map(t =>
          h('button', {
            class: 'opt',
            'aria-pressed': splitVals(state.tag).includes(t.name),
            onclick: (e) => {
              toggleVal('tag', t.name);
              e.currentTarget.setAttribute('aria-pressed', splitVals(state.tag).includes(t.name));
              renderShelf();
            },
          }, t.name, h('span', { class: 'n', style: 'opacity:.55;margin-left:4px' }, t.count))))),
  );

  fillChars('');
  d.classList.add('open');
  b.classList.add('open');
}

function fillChars(kw) {
  const box = $('.charopts');
  if (!box || !META) return;
  const picked = splitVals(state.char);
  let list = META.chars;
  if (kw) list = list.filter(c => c.name.includes(kw));
  else list = list.filter(c => c.works >= 2 || picked.includes(c.name));
  const show = list.slice(0, 60);
  box.replaceChildren(...show.map(c =>
    h('button', {
      class: 'opt',
      'aria-pressed': picked.includes(c.name),
      onclick: (e) => {
        toggleVal('char', c.name);
        e.currentTarget.setAttribute('aria-pressed', splitVals(state.char).includes(c.name));
        renderShelf();
      },
    }, c.name,
      h('span', { class: 'n', style: 'opacity:.55;margin-left:4px' }, `${c.works} 部`))));
  if (!show.length) box.replaceChildren(h('span', { class: 'dimmer' }, '无匹配角色'));
}

function closeDrawer() {
  $('#drawer').classList.remove('open');
  $('#drawerBackdrop').classList.remove('open');
}

function syncFilterUI() {
  $('#searchInput') && ($('#searchInput').value = state.q);
}

/* ---------------- 详情 ---------------- */
async function renderWork(id) {
  const root = $('#view');
  root.replaceChildren(h('div', { class: 'empty' }, h('span', { class: 'spinner' })));
  const [w, chs] = await Promise.all([API('works/' + id), API(`works/${id}/chapters`)]);
  if (w.error) { root.replaceChildren(h('div', { class: 'empty' }, '作品不存在')); return; }

  const tags = JSON.parse(w.tags || '[]');
  const first = chs[0];

  const hero = h('div', { class: 'work-hero' },
    coverEl(w, false),
    h('div', {},
      h('div', { class: 'eyebrow' }, [w.source_work, w.genre].filter(Boolean).join(' · ') || '未归类'),
      h('h1', { class: 'work-title' }, w.title),
      h('div', { class: 'work-subline' },
        h('span', {}, w.author || '佚名'),
        h('span', { class: 'dot' }, '·'),
        h('span', {}, fmtWan(w.char_count) + ' 字'),
        h('span', { class: 'dot' }, '·'),
        h('span', {}, w.chapter_count + ' 节'),
        h('span', { class: 'dot' }, '·'),
        h('span', {}, `约 ${w.reading_minutes} 分钟`),
        w.status ? h('span', { class: 'dot' }, '·') : null,
        w.status ? h('span', {}, w.status) : null),
      h('div', { class: 'work-actions' },
        first ? h('a', { class: 'btn btn-primary', href: `read.html?c=${first.id ?? ''}` }, '开始阅读') : null,
        h('a', { class: 'btn', href: '#/' }, '返回书架')),
      h('div', { class: 'meta-grid' },
        metaItem('原作', w.source_work || '—'),
        metaItem('作者', w.author || w.author_note || '—'),
        metaItem('类型', w.genre || '—'),
        metaItem('分级', w.rating || '—'),
        metaItem('入库', (w.created_at || '').slice(0, 10)),
        metaItem('角色数', String(w.characters.length))),
      tags.length ? h('div', { class: 'chips tagbar', style: 'padding:var(--s4) 0 0' },
        ...(tags.length > 10
          ? [...tags.slice(0, 10).map(tagLink),
             h('details', { class: 'tagmore' },
               h('summary', {}, `展开全部 ${tags.length} 个标签`),
               h('div', { class: 'chips' }, ...tags.slice(10).map(tagLink)))]
          : tags.map(tagLink))) : null,
      w.summary ? h('p', { class: 'work-summary' }, w.summary) : null,
    ));

  const toc = h('div', { class: 'section' },
    h('h2', {}, '目录', h('span', { class: 'n' }, `${chs.length} 节`)),
    h('div', { class: 'toc' }, ...chs.map(c =>
      h('a', { href: `read.html?c=${c.id ?? ''}` },
        h('span', {}, c.title),
        h('span', { class: 'cc' }, c.char_count)))));

  const chars = w.characters.length ? h('div', { class: 'section' },
    h('h2', {}, '主要角色', h('span', { class: 'n' }, `${w.characters.length}`)),
    h('div', { class: 'cast' },
      ...w.characters.map(c => castCard(c)))) : null;

  const fileinfo = h('div', { class: 'section' },
    h('details', { class: 'fileinfo' },
      h('summary', {}, '文件与来源'),
      h('pre', {},
        `校勘版：${w.path_canon || '—'}\n` +
        `校对版：${w.path_proof || '—'}\n` +
        `原文：  ${w.path_source || '—'}\n` +
        `SHA256：${w.sha256 || '—'}`)));

  root.replaceChildren(...[hero, h('div', { class: 'hair' }), chars, toc, fileinfo].filter(Boolean));
  window.scrollTo({ top: 0 });
}

const tagLink = t => h('a', { class: 'tag', href: `#/search?q=${encodeURIComponent(t)}` }, t);

const splitVals = v => (v || '').split(',').filter(Boolean);
function toggleVal(key, v) {
  const arr = splitVals(state[key]);
  const i = arr.indexOf(v);
  if (i >= 0) arr.splice(i, 1); else arr.push(v);
  state[key] = arr.join(',');
  state.page = 1;
}

const J = v => { try { return v ? JSON.parse(v) : null; } catch (_) { return null; } };

function castCard(c) {
  const story = J(c.story) || [];
  const tags = J(c.sex_tags) || [];
  const sexual = (c.sexual || '').split('\n').filter(Boolean);
  const facts = [
    ['外貌', c.looks], ['身体', c.figure], ['性格', c.personality], ['关系', c.relations],
  ].filter(([, v]) => v && v !== '的' );
  const bioParas = (c.bio || '').split(/\n+/).map(s => s.trim()).filter(Boolean);
  const gender = c.gender && c.gender !== '不明' ? c.gender : '';

  const head = h('div', { class: 'cast-top' },
    h('span', { class: 'cast-name' }, c.name),
    c.title ? h('span', { class: 'cast-title' }, c.title) : null);

  const meta = h('div', { class: 'cast-meta' },
    h('span', { class: `role r-${c.role === '主角' ? 'lead' : 'side'}` }, c.role),
    c.origin === '原创' ? h('span', { class: 'cast-origin' }, '原创') : null,
    gender ? h('span', {}, gender) : null,
    h('span', {}, `${c.mentions.toLocaleString()} 次`));

  if (bioParas.length) {
    return h('div', { class: `cast-card hue-${c.hue ?? 0}` },
      head, meta,
      h('div', { class: 'cast-bio' }, ...bioParas.map(p => h('p', {}, p))),
      h('a', { class: 'cast-more', href: `#/search?q=${encodeURIComponent(c.name)}` }, '全文检索 →'));
  }

  return h('div', { class: `cast-card hue-${c.hue ?? 0}` },
    head, meta,
    c.intro ? h('p', { class: 'cast-intro' }, c.intro) : null,
    story.length ? h('div', { class: 'cast-sec' },
      h('h4', {}, '本书片段'),
      h('ul', { class: 'cast-list' },
        ...story.map(s => h('li', {}, h('b', {}, `第${s.i}节 `), s.t)))) : null,
    facts.length ? h('dl', { class: 'cast-dl' },
      ...facts.flatMap(([k, v]) => [h('dt', {}, k), h('dd', {}, v)])) : null,
    (sexual.length || tags.length) ? h('div', { class: 'cast-sec sex' },
      h('h4', {}, '性', tags.length ? h('span', { class: 'cast-tags' },
        ...tags.map(t => h('span', { class: 'ctag' }, t))) : null),
      sexual.length ? h('ul', { class: 'cast-list' },
        ...sexual.map(s => h('li', {}, s))) : null) : null,
    h('a', { class: 'cast-more', href: `#/search?q=${encodeURIComponent(c.name)}` }, '全文检索 →'));
}

const metaItem = (k, v) => h('div', {}, h('div', { class: 'k' }, k), h('div', { class: 'v' }, v));

/* ---------------- 搜索 ---------------- */
async function renderSearch(q) {
  const root = $('#view');
  root.replaceChildren(h('div', { class: 'empty' }, h('span', { class: 'spinner' })));
  const data = await API('search', { q, size: 40 });

  const head = h('div', { class: 'toolbar' },
    h('span', { class: 'count' }, `“${q}” 命中 ${data.total} 处`),
    h('span', { class: 'spacer' }),
    h('a', { class: 'btn', href: '#/' }, '返回书架'));

  if (!data.items.length) {
    root.replaceChildren(head, h('div', { class: 'empty' }, '没有找到，试试更短的关键词或单个人名'));
    return;
  }

  const list = h('div', { class: 'page' }, ...data.items.map(it =>
    h('div', { class: 'hit' },
      h('div', { class: 'hit-head' },
        h('a', { class: 'hit-title', href: `read.html?c=${it.id}` }, it.work_title),
        h('span', { class: 'hit-where' }, `${it.title} · ${it.source_work || ''}`)),
      h('div', { class: 'hit-snippet', html: it.snippet }))));

  root.replaceChildren(head, list);
}

/* ---------------- 标签墙 ---------------- */
async function renderTags() {
  const root = $('#view');
  const tags = await API('tags');
  root.replaceChildren(
    h('div', { class: 'toolbar' }, h('span', { class: 'count' }, `${tags.length} 个标签`)),
    h('div', { class: 'section' },
      h('div', { style: 'display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px' },
        ...tags.map(t =>
          h('a', {
            href: '#/',
            class: 'row',
            style: 'grid-template-columns:1fr auto;padding:10px 0',
            onclick: (e) => {
              e.preventDefault();
              Object.assign(state, { page: 1, tag: t.name, char: '', source: '', genre: '' });
              location.hash = '#/';
              renderShelf();
            },
          },
            h('span', { class: 'row-title' }, t.name),
            h('span', { class: 'row-num' }, t.count))))));
}

/* ---------------- 路由 ---------------- */
async function route() {
  const hash = location.hash || '#/';
  const [path, query] = hash.slice(1).split('?');
  const qs = new URLSearchParams(query || '');
  $$('[data-nav]').forEach(a => a.setAttribute('aria-current', a.dataset.nav === path ? 'true' : 'false'));

  // 详情页是「内容页」，收窄成居中内容带；其余是索引页，用满宽网格
  const isDetail = path.startsWith('/work/');
  $('#view').className = isDetail ? 'detail' : '';
  document.body.classList.toggle('is-detail', isDetail);

  if (path.startsWith('/work/')) return renderWork(path.split('/')[2]);
  if (path === '/search') return renderSearch(qs.get('q') || '');
  if (path === '/tags') return renderTags();
  if (path === '/cats') return renderCats();
  return renderShelf();
}

/* ---------------- 分类 ---------------- */
async function renderCats() {
  const root = $('#view');
  root.replaceChildren(h('div', { class: 'empty' }, h('span', { class: 'spinner' })));
  const [srcs, tags, chars] = await Promise.all([API('sources'), API('tags'), API('characters')]);

  const jump = (patch) => (e) => {
    e.preventDefault();
    Object.assign(state, { page: 1, q: '', source: '', genre: '', tag: '', char: '' }, patch);
    location.hash = '#/';
    renderShelf();
  };

  const group = (title, items) => h('div', { class: 'section' },
    h('h2', {}, title, h('span', { class: 'n' }, `${items.length}`)),
    h('div', { class: 'catgrid' },
      ...items.map(it => h('a', {
        class: 'catchip', href: '#/', onclick: jump(it.patch),
      }, h('b', {}, it.name), h('span', {}, it.note)))));


  root.replaceChildren(
    h('div', { class: 'toolbar' },
      h('span', { class: 'count' }, '分类浏览'),
      h('span', { class: 'spacer' }),
      h('a', { class: 'btn ghost', href: '#/' }, '返回书架')),
    group('按原作', srcs.map(s => ({
      name: s.name, note: `${s.works} 部 · ${fmtWan(s.chars)}字`,
      patch: { source: s.name },
    }))),
    group('按标签', tags.filter(t => t.count >= 5).slice(0, 40).map(t => ({
      name: t.name, note: `${t.count} 部`, patch: { tag: t.name },
    }))),
    group('按角色', chars.filter(c => c.works >= 2).slice(0, 60).map(c => ({
      name: c.name,
      note: `${c.works} 部${c.leads ? ` · 主角 ${c.leads}` : ''}${c.original ? ' · 原创' : ''}`,
      patch: { char: c.name },
    }))));
}

/* ---------------- 隐私 ---------------- */
function initPrivacy() {
  const veil = () => document.body.classList.add('veiled');
  const unveil = () => document.body.classList.remove('veiled');
  document.addEventListener('visibilitychange', () => document.hidden ? veil() : setTimeout(unveil, 120));
  window.addEventListener('blur', veil);
  window.addEventListener('focus', () => setTimeout(unveil, 120));
  const base = '飞行图书馆';
  document.addEventListener('visibilitychange', () => {
    document.title = document.hidden ? '飞行图书馆' : base;
  });
}

/* ---------------- 启动 ---------------- */
async function boot() {
  initTheme();
  initPrivacy();

  // 主题按钮
  $$('[data-theme-btn]').forEach(b =>
    b.addEventListener('click', () => applyTheme(b.dataset.themeBtn)));

  // 搜索框
  const inp = $('#searchInput');
  let timer;
  inp.addEventListener('input', () => {
    clearTimeout(timer);
    timer = setTimeout(() => {
      state.q = inp.value.trim();
      state.page = 1;
      if (location.hash.startsWith('#/search')) location.hash = '#/';
      renderShelf();
    }, 200);
  });
  inp.addEventListener('keydown', e => {
    if (e.key === 'Enter') {
      const q = inp.value.trim();
      if (q) location.hash = `#/search?q=${encodeURIComponent(q)}`;
    }
    if (e.key === 'Escape') { inp.value = ''; state.q = ''; renderShelf(); }
  });
  document.addEventListener('keydown', e => {
    if (e.key === '/' && document.activeElement !== inp) { e.preventDefault(); inp.focus(); }
  });

  $('#drawerClose')?.addEventListener('click', closeDrawer);
  $('#drawerBackdrop')?.addEventListener('click', closeDrawer);

  // 统计数字
  API('stats').then(s => {
    const el = $('#statline');
    if (el) el.textContent = `${s.works} 部 · ${fmtWan(s.chars)}字 · ${s.chapters} 节 · ${s.characters} 个角色`;
  });

  window.addEventListener('hashchange', route);
  await route();
}

boot();
