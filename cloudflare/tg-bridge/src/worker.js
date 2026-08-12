/**
 * Free Telegram → Cursor Automation + GitHub bridge (Cloudflare Workers).
 * - run  → Cursor Automation webhook (agent digest) + GitHub FS Digest (git compare)
 * - more N → prefer agent digest, else git digest
 *
 * Secrets (wrangler secret put):
 *   TELEGRAM_BOT_TOKEN
 *   TELEGRAM_CHAT_ID
 *   GITHUB_TOKEN                  (PAT with actions:write + contents:read)
 *   CURSOR_AUTOMATION_WEBHOOK_URL (Automations webhook URL)
 *   CURSOR_AUTOMATION_AUTH        (full header value, e.g. "Bearer crsr_...")
 *   WEBHOOK_SECRET                (optional shared secret in URL ?key=)
 */

const REPO = "kinaoc-ui/news";
const WORKFLOW_FILE = "fs_digest.yml";
const DIGEST_URL = `https://raw.githubusercontent.com/${REPO}/main/data/last_fs_digest.json`;
const AGENT_DIGEST_URL = `https://raw.githubusercontent.com/${REPO}/main/data/agent_last_fs_digest.json`;

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (request.method === "GET" && url.pathname === "/") {
      return json({
        ok: true,
        service: "tg-bridge",
        repo: REPO,
        agent_webhook: Boolean(env.CURSOR_AUTOMATION_WEBHOOK_URL),
        agent_auth: Boolean(env.CURSOR_AUTOMATION_AUTH),
      });
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
    await tgSend(env, "收到 run — 開跑 agent 版（中文）；Git 版會背景對照。");
    const agent = await dispatchCursorAutomation(env);
    await dispatchWorkflow(env);
    if (!agent.ok) {
      await tgSend(
        env,
        `Agent webhook 失敗（${agent.status || "no-auth"}）。請檢查 CURSOR_AUTOMATION_WEBHOOK_URL + CURSOR_AUTOMATION_AUTH（Bearer crsr_…）。仍會出 Git 版。`
      );
    }
    return json({ ok: true, action: "run", agent: agent.ok, agentStatus: agent.status });
  }

  const more = text.match(/^more\s+(\d+)$/i);
  if (more) {
    const n = Number(more[1]);
    await replyMore(env, n);
    return json({ ok: true, action: "more", n });
  }

  return json({ ok: true, ignored: "unknown command" });
}

async function dispatchCursorAutomation(env) {
  const hook = String(env.CURSOR_AUTOMATION_WEBHOOK_URL || "").trim();
  const auth = String(env.CURSOR_AUTOMATION_AUTH || "").trim();
  if (!hook) return { ok: false, status: "missing-url" };
  if (!auth) return { ok: false, status: "missing-auth" };

  const authorization = auth.toLowerCase().startsWith("bearer ") ? auth : `Bearer ${auth}`;
  const res = await fetch(hook, {
    method: "POST",
    headers: {
      Authorization: authorization,
      "Content-Type": "application/json",
      "User-Agent": "tg-bridge-worker",
    },
    body: JSON.stringify({
      source: "telegram",
      command: "run",
      repo: REPO,
      requested_at: new Date().toISOString(),
    }),
  });
  if (!res.ok) {
    const body = await res.text();
    console.error(`cursor webhook failed: ${res.status} ${body}`);
    return { ok: false, status: res.status };
  }
  return { ok: true, status: res.status };
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
    await tgSend(env, `GitHub 對照版開跑失敗（${res.status}）。可能係 GITHUB_TOKEN 權限唔夠。`);
    throw new Error(`dispatch failed: ${res.status} ${body}`);
  }
}

async function replyMore(env, n) {
  const data = (await fetchDigestJson(AGENT_DIGEST_URL)) || (await fetchDigestJson(DIGEST_URL));
  if (!data) {
    await tgSend(env, "未有上次摘要（可能未跑過 digest）。先打 run。");
    return;
  }
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

async function fetchDigestJson(url) {
  const res = await fetch(`${url}?t=${Date.now()}`, {
    headers: { "User-Agent": "tg-bridge-worker", Accept: "application/json" },
  });
  if (!res.ok) return null;
  try {
    return await res.json();
  } catch {
    return null;
  }
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
