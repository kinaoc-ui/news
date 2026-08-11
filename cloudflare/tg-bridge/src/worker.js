/**
 * Free Telegram → GitHub bridge (Cloudflare Workers).
 * - run  → workflow_dispatch FS Digest
 * - more N → fetch data/last_fs_digest.json from GitHub + reply on Telegram
 *
 * Secrets (wrangler secret put):
 *   TELEGRAM_BOT_TOKEN
 *   TELEGRAM_CHAT_ID
 *   GITHUB_TOKEN   (PAT with actions:write + contents:read)
 *   WEBHOOK_SECRET (optional shared secret in URL ?key=)
 */

const REPO = "kinaoc-ui/news";
const WORKFLOW_FILE = "fs_digest.yml";
const DIGEST_URL = `https://raw.githubusercontent.com/${REPO}/main/data/last_fs_digest.json`;

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (request.method === "GET" && url.pathname === "/") {
      return json({ ok: true, service: "tg-bridge", repo: REPO });
    }

    if (request.method === "POST" && url.pathname === "/telegram") {
      if (env.WEBHOOK_SECRET && url.searchParams.get("key") !== env.WEBHOOK_SECRET) {
        return json({ ok: false, error: "unauthorized" }, 401);
      }
      const update = await request.json();
      return handleTelegram(update, env);
    }

    return json({ ok: false, error: "not found" }, 404);
  },
};

async function handleTelegram(update, env) {
  const msg = update.message || {};
  const chatId = String(msg.chat?.id || "");
  const text = String(msg.text || "").trim();
  if (!chatId || chatId !== String(env.TELEGRAM_CHAT_ID)) {
    return json({ ok: true, ignored: "wrong chat" });
  }

  if (/^run$/i.test(text)) {
    await tgSend(env, "收到 run — 即刻喺 GitHub 開跑，完成會再推。");
    await dispatchWorkflow(env);
    return json({ ok: true, action: "run" });
  }

  const more = text.match(/^more\s+(\d+)$/i);
  if (more) {
    const n = Number(more[1]);
    await replyMore(env, n);
    return json({ ok: true, action: "more", n });
  }

  return json({ ok: true, ignored: "unknown command" });
}

async function dispatchWorkflow(env) {
  const res = await fetch(
    `https://api.github.com/repos/${REPO}/actions/workflows/${WORKFLOW_FILE}/dispatches`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${env.GITHUB_TOKEN}`,
        Accept: "application/vnd.github+json",
        "User-Agent": "tg-bridge-worker",
        "X-GitHub-Api-Version": "2022-11-28",
      },
      body: JSON.stringify({ ref: "main" }),
    }
  );
  if (!res.ok) {
    const body = await res.text();
    await tgSend(env, `GitHub 開跑失敗（${res.status}）。可能係 GITHUB_TOKEN 權限唔夠。`);
    throw new Error(`dispatch failed: ${res.status} ${body}`);
  }
}

async function replyMore(env, n) {
  const res = await fetch(`${DIGEST_URL}?t=${Date.now()}`, {
    headers: { "User-Agent": "tg-bridge-worker", Accept: "application/json" },
  });
  if (!res.ok) {
    await tgSend(env, "未有上次摘要（可能未跑過 digest）。先打 run。");
    return;
  }
  const data = await res.json();
  const items = Object.fromEntries((data.items || []).map((it) => [Number(it.n), it]));
  const item = items[n];
  if (!item) {
    const max = Math.max(0, ...Object.keys(items).map(Number));
    await tgSend(env, `冇第 ${n} 項。而家只有 1–${max}。`);
    return;
  }
  const lines = [`詳情 #${n}`, item.detail || item.short || ""];
  if (item.source) lines.push(`來源名：${item.source}`);
  if (item.url) lines.push(`連結：${item.url}`);
  await tgSend(env, lines.filter(Boolean).join("\n"));
}

async function tgSend(env, text) {
  const res = await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/sendMessage`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      chat_id: env.TELEGRAM_CHAT_ID,
      text: String(text).slice(0, 4000),
      disable_web_page_preview: true,
    }),
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`telegram send failed: ${res.status} ${body}`);
  }
}

function json(obj, status = 200) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}
