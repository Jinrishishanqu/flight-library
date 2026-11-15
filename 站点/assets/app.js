// 表格筛选 + 排序（无依赖）
function initTable(table) {
  const input = document.querySelector('[data-filter="' + table.id + '"]');
  if (input) {
    input.addEventListener('input', () => {
      const q = input.value.trim().toLowerCase();
      table.querySelectorAll('tbody tr').forEach(tr => {
        tr.style.display = !q || tr.textContent.toLowerCase().includes(q) ? '' : 'none';
      });
    });
  }
  const ths = table.querySelectorAll('thead th');
  ths.forEach((th, idx) => {
    th.addEventListener('click', () => {
      const tb = table.tBodies[0];
      const rows = Array.from(tb.rows);
      const asc = th.dataset.dir !== 'asc';
      ths.forEach(o => delete o.dataset.dir);
      th.dataset.dir = asc ? 'asc' : 'desc';
      const val = tr => {
        const c = tr.cells[idx];
        if (!c) return '';
        const t = c.dataset.sort !== undefined ? c.dataset.sort : c.textContent.trim();
        const n = parseFloat(t.replace(/[^\d.\-]/g, ''));
        return isNaN(n) || !/^[\d.\- ]+$/.test(t) ? t : n;
      };
      rows.sort((a, b) => {
        const x = val(a), y = val(b);
        if (typeof x === 'number' && typeof y === 'number') return asc ? x - y : y - x;
        return asc ? String(x).localeCompare(String(y), 'zh') : String(y).localeCompare(String(x), 'zh');
      });
      rows.forEach(r => tb.appendChild(r));
    });
  });
}
document.querySelectorAll('table[data-sortable]').forEach(initTable);

// 统计条动画
document.querySelectorAll('.bar > i[data-pct]').forEach(el => {
  const p = Math.max(0, Math.min(100, parseFloat(el.dataset.pct) || 0));
  el.style.width = p + '%';
});

// 用 data.js 的真实数据刷新页面（跑 采集工具\生成站点.ps1 更新）
(function () {
  const D = window.DATA;
  if (!D) return;
  const set = (k, v) => document.querySelectorAll('[data-stat="' + k + '"]').forEach(e => { e.textContent = v; });
  set('yuanwen', D.yuanwen);
  set('yuanwenMB', D.yuanwenMB);
  set('jiaodui', D.jiaodui);
  set('jiaoduiMB', D.jiaoduiMB);
  set('charsW', Math.round((D.chars || 0) / 10000));
  set('verified', D.verified);
  set('verifiedBad', D.verifiedBad);
  set('regen', D.regen);
  set('merged', D.merged);
  set('dedup', D.dedup);
  set('indexRows', D.indexRows);

  const paint = root => root.querySelectorAll('.bar > i[data-pct]').forEach(el => {
    el.style.width = Math.max(0, Math.min(100, parseFloat(el.dataset.pct) || 0)) + '%';
  });

  const tb = document.getElementById('dist-body');
  if (tb && D.groups && D.groups.length) {
    const total = D.groups.reduce((s, g) => s + g.files, 0) || 1;
    tb.innerHTML = D.groups.map(g =>
      '<tr><td>' + g.name + '</td><td class="num">' + g.files +
      '</td><td><div class="bar"><i data-pct="' + (g.files / total * 100).toFixed(1) + '"></i></div></td></tr>'
    ).join('');
    paint(tb);
  }

  const rt = document.getElementById('rec-body');
  if (rt && D.records) {
    rt.innerHTML = D.records.map(r =>
      '<tr><td><code>' + r.name + '</code></td><td class="num">' + r.rows +
      '</td><td class="num">' + (r.size / 1024).toFixed(1) + ' KB</td><td>' + r.time + '</td></tr>'
    ).join('');
  }

  document.querySelectorAll('[data-gen]').forEach(e => { e.textContent = D.generated; });
})();
