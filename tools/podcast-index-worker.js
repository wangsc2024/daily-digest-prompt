// podcast-index Worker
// Bindings: PODCASTS (R2 bucket), KNOWLEDGE_VIEWS (KV namespace)

var AUDIO_BASE_URL = "https://podcasts.pdoont.us.kg";
var SITE_TITLE = "Podcast \u2014 \u6BCF\u65E5\u77E5\u8B58\u96FB\u53F0";
var SITE_SUBTITLE = "AI \u96D9\u4E3B\u6301\u4EBA\u5C0D\u8A71\uFF0C\u6BCF\u65E5\u7CBE\u9078\u77E5\u8B58\u7B46\u8A18";
var META_KEY = "_meta/podcast-titles.json";

function formatSize(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDate(date) {
  if (!(date instanceof Date)) date = new Date(date);
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

function titleFromKey(key) {
  const base = key.replace(/\.(mp3|m4a|mp4)$/i, "");
  const match = base.match(/^(.+)_(\d{8})_(\d{6})$/);
  if (match)
    return `${match[1]} \xB7 ${match[2].slice(0, 4)}-${match[2].slice(4, 6)}-${match[2].slice(6, 8)}`;
  return base;
}

async function loadTitlesMeta(env) {
  try {
    const obj = await env.PODCASTS.get(META_KEY);
    if (!obj || !obj.body) return {};
    const text = await obj.text();
    const data = JSON.parse(text);
    return typeof data === "object" && data !== null ? data : {};
  } catch {
    return {};
  }
}

function escapeHtml(s) {
  if (typeof s !== "string") return "";
  const m = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
  return s.replace(/[&<>"']/g, (c) => m[c]);
}

// ── KV Play Counter helpers ──
async function getPlayCount(env, key) {
  if (!env.KNOWLEDGE_VIEWS) return 0;
  try {
    const val = await env.KNOWLEDGE_VIEWS.get(`podcast:${key}`);
    return val ? parseInt(val, 10) : 0;
  } catch { return 0; }
}

async function incrementPlayCount(env, key) {
  if (!env.KNOWLEDGE_VIEWS) return 0;
  try {
    const kvKey = `podcast:${key}`;
    const val = await env.KNOWLEDGE_VIEWS.get(kvKey);
    const plays = (val ? parseInt(val, 10) : 0) + 1;
    await env.KNOWLEDGE_VIEWS.put(kvKey, String(plays));
    return plays;
  } catch { return 0; }
}

var index_default = {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);

    // ── API: POST /play/{key} — 播放計數 +1 ──
    const playMatch = url.pathname.match(/^\/play\/(.+)$/);
    if (playMatch) {
      const key = decodeURIComponent(playMatch[1]);
      if (request.method === "POST") {
        const plays = await incrementPlayCount(env, key);
        return new Response(JSON.stringify({ key, plays }), {
          headers: { "Content-Type": "application/json", "Access-Control-Allow-Origin": "*" }
        });
      }
      if (request.method === "GET") {
        const plays = await getPlayCount(env, key);
        return new Response(JSON.stringify({ key, plays }), {
          headers: { "Content-Type": "application/json", "Cache-Control": "no-store", "Access-Control-Allow-Origin": "*" }
        });
      }
    }

    // ── API: GET /plays — 批次取得所有播放數 ──
    if (url.pathname === "/plays" && request.method === "GET") {
      try {
        const listed = await env.PODCASTS.list({ limit: 1000 });
        const keys = (listed.objects || [])
          .filter(o => /\.(mp3|m4a)$/i.test(o.key) && !o.key.startsWith("_meta/"))
          .map(o => o.key);
        const counts = await Promise.all(
          keys.map(async k => [k, await getPlayCount(env, k)])
        );
        const result = Object.fromEntries(counts);
        return new Response(JSON.stringify(result), {
          headers: { "Content-Type": "application/json", "Cache-Control": "no-store", "Access-Control-Allow-Origin": "*" }
        });
      } catch (e) {
        return new Response("{}", { headers: { "Content-Type": "application/json" } });
      }
    }

    // ── 主頁面 ──
    if (url.pathname !== "/" && url.pathname !== "/index.html") {
      return new Response("Not Found", { status: 404 });
    }

    try {
      const [listed, titlesMeta] = await Promise.all([
        env.PODCASTS.list({ limit: 1000, include: ["customMetadata"] }),
        loadTitlesMeta(env)
      ]);

      let objects = (listed.objects || []).filter(
        o => /\.(mp3|m4a)$/i.test(o.key) && !o.key.startsWith("_meta/")
      );
      objects.sort((a, b) => {
        const ta = a.uploaded ? new Date(a.uploaded).getTime() : 0;
        const tb = b.uploaded ? new Date(b.uploaded).getTime() : 0;
        return tb - ta;
      });

      // 預載播放次數
      const playCounts = await Promise.all(
        objects.map(o => getPlayCount(env, o.key))
      );

      const tracks = objects.map((o, i) => {
        const meta = titlesMeta[o.key] || {};
        const title = meta.title || o.customMetadata?.title || titleFromKey(o.key);
        const topic = meta.topic || "";
        const dateStr = o.uploaded ? formatDate(o.uploaded) : "";
        const sizeStr = formatSize(o.size ?? 0);
        const audioUrl = `${AUDIO_BASE_URL}/${encodeURIComponent(o.key)}`;
        const plays = playCounts[i] || 0;
        return { i, title, topic, dateStr, sizeStr, audioUrl, plays, key: o.key };
      });

      const trackListJson = JSON.stringify(
        tracks.map(t => ({ title: t.title, topic: t.topic, url: t.audioUrl, key: t.key, plays: t.plays }))
      );

      const cards = tracks.map(t => `
        <article class="card" data-idx="${t.i}" onclick="P.play(${t.i})">
          <div class="card-body">
            <div class="card-idx">${t.i + 1}</div>
            <div class="card-info">
              <h2 class="card-title">${escapeHtml(t.title)}</h2>
              <p class="card-meta">
                ${t.topic ? `<span class="badge">${escapeHtml(t.topic)}</span>` : ""}
                <span>${escapeHtml(t.dateStr)}</span>
                <span>${t.sizeStr}</span>
                <span class="plays" id="plays-${t.i}">${t.plays > 0 ? `\u25B6\uFE0F ${t.plays}` : ""}</span>
              </p>
            </div>
            <button class="card-play" aria-label="\u64AD\u653E" data-idx="${t.i}">
              <svg class="icon-play" viewBox="0 0 24 24"><polygon points="6,3 20,12 6,21"/></svg>
              <svg class="icon-pause" viewBox="0 0 24 24"><rect x="5" y="3" width="4" height="18"/><rect x="15" y="3" width="4" height="18"/></svg>
              <svg class="icon-eq" viewBox="0 0 24 24"><rect x="3" y="14" width="4" height="7" rx="1"><animate attributeName="height" values="7;14;7" dur="0.8s" repeatCount="indefinite"/><animate attributeName="y" values="14;7;14" dur="0.8s" repeatCount="indefinite"/></rect><rect x="10" y="7" width="4" height="14" rx="1"><animate attributeName="height" values="14;7;14" dur="0.6s" repeatCount="indefinite"/><animate attributeName="y" values="7;14;7" dur="0.6s" repeatCount="indefinite"/></rect><rect x="17" y="10" width="4" height="11" rx="1"><animate attributeName="height" values="11;4;11" dur="0.7s" repeatCount="indefinite"/><animate attributeName="y" values="10;17;10" dur="0.7s" repeatCount="indefinite"/></rect></svg>
            </button>
          </div>
        </article>`
      );

      const html = `<!DOCTYPE html>
<html lang="zh-Hant">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>${escapeHtml(SITE_TITLE)}</title>
  <meta name="description" content="${escapeHtml(SITE_SUBTITLE)}"/>
  <link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>\u{1F399}\uFE0F</text></svg>"/>
  <style>
    :root {
      --bg: #0b1120;
      --surface: #101828;
      --card: #131b2e;
      --card-hover: #1a2540;
      --card-active: #1c2a45;
      --text: #f1f5f9;
      --text-secondary: #8892a8;
      --accent: #ff6b6b;
      --accent-mint: #2dd4bf;
      --accent-yellow: #ffd93d;
      --accent-glow: rgba(255,107,107,0.2);
      --bar-bg: rgba(11,17,32,0.92);
      --radius: 14px;
      --player-h: 88px;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
      background: var(--bg);
      color: var(--text);
      min-height: 100vh;
      padding-bottom: calc(var(--player-h) + 1rem);
    }
    header {
      max-width: 640px;
      margin: 0 auto;
      padding: 2.5rem 1.25rem 1.25rem;
    }
    header h1 {
      font-size: 1.6rem;
      font-weight: 700;
      letter-spacing: -0.02em;
      display: flex;
      align-items: center;
      gap: 0.5rem;
    }
    header h1 .logo { font-size: 1.4rem; }
    .title-text {
      background: linear-gradient(135deg, var(--accent) 0%, var(--accent-yellow) 50%, var(--accent-mint) 100%);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      background-clip: text;
    }
    header p {
      color: var(--text-secondary);
      font-size: 0.9rem;
      margin-top: 0.4rem;
    }
    .count-badge {
      display: inline-block;
      background: linear-gradient(135deg, var(--accent), #ff8e53);
      color: #fff;
      font-size: 0.7rem;
      font-weight: 600;
      padding: 0.15em 0.55em;
      border-radius: 99px;
      vertical-align: middle;
      margin-left: 0.3rem;
    }
    .list {
      max-width: 640px;
      margin: 0 auto;
      padding: 0 1.25rem;
      display: flex;
      flex-direction: column;
      gap: 6px;
    }
    .card {
      background: var(--card);
      border-radius: var(--radius);
      border: 1px solid rgba(255,255,255,0.04);
      cursor: pointer;
      transition: background 0.15s, border-color 0.15s, box-shadow 0.25s;
      user-select: none;
      -webkit-tap-highlight-color: transparent;
    }
    .card:hover { background: var(--card-hover); border-color: rgba(255,255,255,0.08); }
    .card.active {
      background: var(--card-active);
      border-color: var(--accent);
      box-shadow: 0 0 0 1px var(--accent-glow), 0 4px 28px var(--accent-glow);
    }
    .card-body {
      display: flex;
      align-items: center;
      gap: 0.75rem;
      padding: 0.85rem 1rem;
    }
    .card-idx {
      flex-shrink: 0;
      width: 1.8rem;
      text-align: center;
      font-size: 0.85rem;
      color: var(--text-secondary);
      font-variant-numeric: tabular-nums;
    }
    .card.active .card-idx { color: var(--accent); font-weight: 600; }
    .card-info { flex: 1; min-width: 0; }
    .card-title {
      font-size: 0.95rem;
      font-weight: 500;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      line-height: 1.4;
    }
    .card.active .card-title { color: #fff; }
    .card-meta {
      font-size: 0.78rem;
      color: var(--text-secondary);
      display: flex;
      align-items: center;
      gap: 0.5rem;
      margin-top: 0.15rem;
      flex-wrap: wrap;
    }
    .badge {
      background: rgba(45,212,191,0.12);
      color: var(--accent-mint);
      padding: 0.1em 0.5em;
      border-radius: 4px;
      font-size: 0.72rem;
      font-weight: 500;
    }
    .plays {
      color: var(--accent-yellow);
      font-size: 0.72rem;
    }
    .card-play {
      flex-shrink: 0;
      width: 2.4rem;
      height: 2.4rem;
      border: none;
      border-radius: 50%;
      background: rgba(255,107,107,0.1);
      color: var(--accent);
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      transition: background 0.15s, transform 0.1s;
    }
    .card-play:hover { background: rgba(255,107,107,0.22); }
    .card-play:active { transform: scale(0.92); }
    .card-play svg { width: 16px; height: 16px; fill: currentColor; }
    .card-play .icon-pause,
    .card-play .icon-eq { display: none; }
    .card.active .card-play .icon-play { display: none; }
    .card.active.playing .card-play .icon-eq { display: block; }
    .card.active.playing .card-play { color: var(--accent-mint); }
    .card.active:not(.playing) .card-play .icon-pause { display: block; }
    .player-bar {
      position: fixed;
      bottom: 0;
      left: 0;
      right: 0;
      height: var(--player-h);
      background: var(--bar-bg);
      border-top: 1px solid rgba(255,255,255,0.06);
      backdrop-filter: blur(16px);
      -webkit-backdrop-filter: blur(16px);
      z-index: 100;
      display: flex;
      flex-direction: column;
      transform: translateY(100%);
      transition: transform 0.3s ease;
    }
    .player-bar.visible { transform: translateY(0); }
    .progress-wrap {
      width: 100%;
      height: 4px;
      background: rgba(255,255,255,0.06);
      cursor: pointer;
      flex-shrink: 0;
      position: relative;
    }
    .progress-wrap:hover { height: 6px; }
    .progress-fill {
      height: 100%;
      background: linear-gradient(90deg, var(--accent), var(--accent-yellow), var(--accent-mint));
      width: 0;
      border-radius: 0 2px 2px 0;
      transition: width 0.15s linear;
    }
    .progress-buffer {
      position: absolute;
      top: 0; left: 0;
      height: 100%;
      background: rgba(255,255,255,0.06);
      width: 0;
      pointer-events: none;
    }
    .player-main {
      flex: 1;
      display: flex;
      align-items: center;
      gap: 0.75rem;
      padding: 0 1rem;
      max-width: 640px;
      width: 100%;
      margin: 0 auto;
    }
    .player-info { flex: 1; min-width: 0; }
    .player-title {
      font-size: 0.88rem;
      font-weight: 500;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .player-sub { font-size: 0.75rem; color: var(--accent-mint); margin-top: 1px; }
    .player-time {
      font-size: 0.72rem;
      color: var(--text-secondary);
      font-variant-numeric: tabular-nums;
      flex-shrink: 0;
    }
    .player-controls { display: flex; align-items: center; gap: 0.35rem; flex-shrink: 0; }
    .ctrl {
      width: 2.5rem; height: 2.5rem;
      border: none; border-radius: 50%;
      background: transparent; color: var(--text);
      cursor: pointer;
      display: flex; align-items: center; justify-content: center;
      transition: background 0.12s;
    }
    .ctrl:hover { background: rgba(255,255,255,0.08); }
    .ctrl svg { width: 20px; height: 20px; fill: currentColor; }
    .ctrl-main {
      background: linear-gradient(135deg, var(--accent), #ff8e53);
      color: #fff;
      box-shadow: 0 2px 12px rgba(255,107,107,0.3);
    }
    .ctrl-main:hover { background: linear-gradient(135deg, #ff5252, #ff7b43); }
    .ctrl-main svg { width: 22px; height: 22px; }
    .empty { color: var(--text-secondary); text-align: center; padding: 4rem 1rem; font-size: 0.95rem; }
    @media (max-width: 480px) {
      header { padding: 2rem 1rem 0.75rem; }
      header h1 { font-size: 1.35rem; }
      .card-body { padding: 0.7rem 0.75rem; gap: 0.5rem; }
      .card-title { font-size: 0.88rem; }
      .player-main { padding: 0 0.75rem; }
    }
  </style>
</head>
<body>
  <header>
    <h1><span class="logo">\u{1F399}\uFE0F</span><span class="title-text">${escapeHtml(SITE_TITLE)}</span><span class="count-badge">${tracks.length}</span></h1>
    <p>${escapeHtml(SITE_SUBTITLE)}</p>
  </header>
  <div class="list">
    ${cards.length ? cards.join("") : '<p class="empty">\u5C1A\u7121 Podcast\uFF0C\u656C\u8ACB\u671F\u5F85 \u2728</p>'}
  </div>
  <div class="player-bar" id="playerBar">
    <div class="progress-wrap" id="progressWrap">
      <div class="progress-buffer" id="progressBuffer"></div>
      <div class="progress-fill" id="progressFill"></div>
    </div>
    <div class="player-main">
      <div class="player-controls">
        <button class="ctrl" id="btnPrev" aria-label="\u4E0A\u4E00\u9996">
          <svg viewBox="0 0 24 24"><path d="M6 6h2v12H6zm3.5 6 8.5 6V6z"/></svg>
        </button>
        <button class="ctrl ctrl-main" id="btnToggle" aria-label="\u64AD\u653E/\u66AB\u505C">
          <svg class="pp-play" viewBox="0 0 24 24"><polygon points="6,3 20,12 6,21"/></svg>
          <svg class="pp-pause" viewBox="0 0 24 24" style="display:none"><rect x="5" y="3" width="4" height="18"/><rect x="15" y="3" width="4" height="18"/></svg>
        </button>
        <button class="ctrl" id="btnNext" aria-label="\u4E0B\u4E00\u9996">
          <svg viewBox="0 0 24 24"><path d="M16 18h2V6h-2zM6 18l8.5-6L6 6z"/></svg>
        </button>
      </div>
      <div class="player-info">
        <div class="player-title" id="pTitle">\u2014</div>
        <div class="player-sub" id="pSub"></div>
      </div>
      <div class="player-time" id="pTime">0:00 / 0:00</div>
    </div>
  </div>
  <audio id="audio" preload="metadata"></audio>
  <script>
  (function(){
    const tracks = ${trackListJson};
    const audio = document.getElementById('audio');
    const bar = document.getElementById('playerBar');
    const fill = document.getElementById('progressFill');
    const buffer = document.getElementById('progressBuffer');
    const wrap = document.getElementById('progressWrap');
    const pTitle = document.getElementById('pTitle');
    const pSub = document.getElementById('pSub');
    const pTime = document.getElementById('pTime');
    const btnToggle = document.getElementById('btnToggle');
    const btnPrev = document.getElementById('btnPrev');
    const btnNext = document.getElementById('btnNext');
    const ppPlay = btnToggle.querySelector('.pp-play');
    const ppPause = btnToggle.querySelector('.pp-pause');
    const cards = document.querySelectorAll('.card');

    let current = -1;

    function fmtTime(s) {
      if (!s || !isFinite(s)) return '0:00';
      const m = Math.floor(s / 60);
      const sec = Math.floor(s % 60);
      return m + ':' + String(sec).padStart(2, '0');
    }

    function setPlaying(isPlaying) {
      ppPlay.style.display = isPlaying ? 'none' : '';
      ppPause.style.display = isPlaying ? '' : 'none';
      cards.forEach(c => c.classList.remove('playing'));
      if (isPlaying && current >= 0) cards[current]?.classList.add('playing');
    }

    function updatePlayCount(idx, plays) {
      const el = document.getElementById('plays-' + idx);
      if (el) el.textContent = plays > 0 ? '\u25B6\uFE0F ' + plays : '';
    }

    window.P = {
      play(idx) {
        if (idx < 0 || idx >= tracks.length) return;
        const same = idx === current;
        if (same && !audio.paused) { audio.pause(); return; }
        if (same && audio.paused) { audio.play(); return; }
        cards.forEach(c => c.classList.remove('active', 'playing'));
        current = idx;
        const t = tracks[idx];
        audio.src = t.url;
        audio.play();
        bar.classList.add('visible');
        cards[idx]?.classList.add('active');
        pTitle.textContent = t.title;
        pSub.textContent = t.topic || ('\u7B2C ' + (idx + 1) + ' \u96C6\uFF08\u5171 ' + tracks.length + ' \u96C6\uFF09');
        document.title = t.title + ' \u2014 ${escapeHtml(SITE_TITLE)}';
        cards[idx]?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });

        // 計數 +1（fire-and-forget）
        fetch('/play/' + encodeURIComponent(t.key), { method: 'POST' })
          .then(r => r.json())
          .then(d => { if (d.plays) updatePlayCount(idx, d.plays); })
          .catch(() => {});
      }
    };

    btnToggle.onclick = () => { if (current < 0) { P.play(0); return; } audio.paused ? audio.play() : audio.pause(); };
    btnPrev.onclick = () => { if (current > 0) P.play(current - 1); };
    btnNext.onclick = () => { if (current < tracks.length - 1) P.play(current + 1); };

    audio.addEventListener('play', () => setPlaying(true));
    audio.addEventListener('pause', () => setPlaying(false));
    audio.addEventListener('ended', () => { if (current < tracks.length - 1) P.play(current + 1); else setPlaying(false); });
    audio.addEventListener('timeupdate', () => {
      if (!audio.duration) return;
      fill.style.width = (audio.currentTime / audio.duration) * 100 + '%';
      pTime.textContent = fmtTime(audio.currentTime) + ' / ' + fmtTime(audio.duration);
    });
    audio.addEventListener('progress', () => {
      if (audio.buffered.length && audio.duration) {
        buffer.style.width = (audio.buffered.end(audio.buffered.length - 1) / audio.duration) * 100 + '%';
      }
    });
    wrap.addEventListener('click', (e) => {
      if (!audio.duration) return;
      const rect = wrap.getBoundingClientRect();
      audio.currentTime = ((e.clientX - rect.left) / rect.width) * audio.duration;
    });
    document.addEventListener('keydown', (e) => {
      if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
      if (e.code === 'Space') { e.preventDefault(); btnToggle.click(); }
      if (e.code === 'ArrowLeft' && audio.duration) audio.currentTime = Math.max(0, audio.currentTime - 10);
      if (e.code === 'ArrowRight' && audio.duration) audio.currentTime = Math.min(audio.duration, audio.currentTime + 10);
      if (e.code === 'KeyN' || e.code === 'ArrowDown') { e.preventDefault(); btnNext.click(); }
      if (e.code === 'KeyP' || e.code === 'ArrowUp') { e.preventDefault(); btnPrev.click(); }
    });
  })();
  </script>
</body>
</html>`;

      return new Response(html, {
        headers: {
          "Content-Type": "text/html; charset=utf-8",
          "Cache-Control": "public, max-age=60"
        }
      });
    } catch (e) {
      return new Response(`Error: ${e.message}`, {
        status: 500,
        headers: { "Content-Type": "text/plain; charset=utf-8" }
      });
    }
  }
};

export { index_default as default };
