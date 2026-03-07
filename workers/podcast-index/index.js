/**
 * Podcast 列表網頁 Worker
 * 部署於 podcast.pdoont.us.kg，動態讀取 R2 podcasts bucket 並渲染 HTML + 內嵌播放器
 */

const AUDIO_BASE_URL = "https://podcasts.pdoont.us.kg";
const PAGE_TITLE = "Podcast 列表";

function formatSize(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDate(date) {
  if (!(date instanceof Date)) date = new Date(date);
  return date.toISOString().slice(0, 10);
}

const META_KEY = "_meta/podcast-titles.json";

/** 從 key 推導顯示標題（無 metadata 時使用） */
function titleFromKey(key) {
  const base = key.replace(/\.(mp3|m4a|mp4)$/i, "");
  const match = base.match(/^(.+)_(\d{8})_(\d{6})$/);
  if (match) return `${match[1]} · ${match[2].slice(0, 4)}-${match[2].slice(4, 6)}-${match[2].slice(6, 8)}`;
  return base;
}

/** 從 R2 讀取標題/主題 manifest，回傳 { [key]: { title?, topic? } } */
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

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    if (url.pathname !== "/" && url.pathname !== "/index.html") {
      return new Response("Not Found", { status: 404 });
    }

    try {
      const [listed, titlesMeta] = await Promise.all([
        env.PODCASTS.list({ limit: 1000, include: ["customMetadata"] }),
        loadTitlesMeta(env),
      ]);

      let objects = (listed.objects || []).filter(
        (o) => /\.(mp3|m4a)$/i.test(o.key) && !o.key.startsWith("_meta/")
      );
      objects.sort((a, b) => {
        const ta = (a.uploaded && new Date(a.uploaded).getTime()) || 0;
        const tb = (b.uploaded && new Date(b.uploaded).getTime()) || 0;
        return tb - ta;
      });

      const cards = objects.map((o) => {
        const meta = titlesMeta[o.key] || {};
        const title = meta.title || o.customMetadata?.title || titleFromKey(o.key);
        const topic = meta.topic || "";
        const dateStr = o.uploaded ? formatDate(o.uploaded) : "—";
        const sizeStr = formatSize(o.size ?? 0);
        const audioUrl = `${AUDIO_BASE_URL}/${encodeURIComponent(o.key)}`;

        return `
        <article class="card">
          <h2 class="card-title">${escapeHtml(title)}</h2>
          ${topic ? `<p class="card-topic">${escapeHtml(topic)}</p>` : ""}
          <p class="card-meta">${escapeHtml(dateStr)} · ${sizeStr}</p>
          <audio class="player" controls preload="metadata" src="${escapeHtml(audioUrl)}">
            您的瀏覽器不支援 audio 播放。
          </audio>
          <a class="link" href="${escapeHtml(audioUrl)}" target="_blank" rel="noopener">直接開啟</a>
        </article>`;
      });

      const html = `<!DOCTYPE html>
<html lang="zh-Hant">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>${PAGE_TITLE}</title>
  <style>
    :root { --bg: #1a1a2e; --card: #16213e; --text: #e8e8e8; --muted: #a0a0a0; --accent: #0f3460; }
    * { box-sizing: border-box; }
    body { margin: 0; font-family: system-ui, -apple-system, sans-serif; background: var(--bg); color: var(--text); min-height: 100vh; padding: 1.5rem; }
    h1 { font-size: 1.5rem; margin: 0 0 1.5rem; color: var(--text); }
    .cards { display: grid; gap: 1.25rem; max-width: 42rem; margin: 0 auto; }
    .card { background: var(--card); border-radius: 0.5rem; padding: 1.25rem; border: 1px solid rgba(255,255,255,0.06); }
    .card-title { font-size: 1.1rem; margin: 0 0 0.25em; font-weight: 600; word-break: break-word; }
    .card-topic { font-size: 0.9rem; color: var(--muted); margin: 0 0 0.35em; }
    .card-meta { font-size: 0.85rem; color: var(--muted); margin: 0 0 0.75rem; }
    .player { width: 100%; height: 2.5rem; margin: 0 0 0.5rem; }
    .link { font-size: 0.85rem; color: #7eb8da; text-decoration: none; }
    .link:hover { text-decoration: underline; }
    .empty { color: var(--muted); text-align: center; padding: 2rem; }
  </style>
</head>
<body>
  <h1>${PAGE_TITLE}</h1>
  <div class="cards">
    ${cards.length ? cards.join("") : '<p class="empty">尚無 Podcast</p>'}
  </div>
</body>
</html>`;

      return new Response(html, {
        headers: {
          "Content-Type": "text/html; charset=utf-8",
          "Cache-Control": "public, max-age=60",
        },
      });
    } catch (e) {
      return new Response(`Error: ${e.message}`, {
        status: 500,
        headers: { "Content-Type": "text/plain; charset=utf-8" },
      });
    }
  },
};

function escapeHtml(s) {
  if (typeof s !== "string") return "";
  const m = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
  return s.replace(/[&<>"']/g, (c) => m[c]);
}
