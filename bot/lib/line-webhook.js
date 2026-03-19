/**
 * line-webhook.js — LINE Messaging API Webhook 整合
 *
 * 前置需求：
 *   npm install @line/bot-sdk
 *   .env 設定：
 *     LINE_CHANNEL_SECRET=xxx
 *     LINE_CHANNEL_ACCESS_TOKEN=xxx
 *
 * 掛載方式（bot.js 中）：
 *   const lineWebhook = require('./lib/line-webhook');
 *   lineWebhook.mount(app, { store, generateId, sendReply });
 */

let lineClient = null;
let lineSdk = null;

/**
 * 嘗試載入 @line/bot-sdk，若未安裝則 graceful degrade
 */
function tryLoadLineSdk() {
    try {
        lineSdk = require('@line/bot-sdk');
        return true;
    } catch {
        return false;
    }
}

/**
 * 掛載 LINE Webhook 路由至 Express app
 * @param {import('express').Application} app
 * @param {{ store, generateId, sendReply }} deps
 */
function mount(app, { store, generateId, sendReply }) {
    const channelSecret = process.env.LINE_CHANNEL_SECRET;
    const channelAccessToken = process.env.LINE_CHANNEL_ACCESS_TOKEN;

    if (!channelSecret || !channelAccessToken) {
        console.log('[LINE] LINE_CHANNEL_SECRET / LINE_CHANNEL_ACCESS_TOKEN 未設定，LINE Webhook 已停用');
        return;
    }

    if (!tryLoadLineSdk()) {
        console.warn('[LINE] @line/bot-sdk 未安裝，LINE Webhook 已停用。請執行：cd bot && npm install @line/bot-sdk');
        return;
    }

    lineClient = new lineSdk.messagingApi.MessagingApiClient({ channelAccessToken });
    const lineConfig = { channelSecret };

    // Webhook 簽章驗證 + 接收訊息
    app.post('/api/line-webhook',
        lineSdk.middleware(lineConfig),
        async (req, res) => {
            res.status(200).end(); // LINE 要求立即回應 200
            for (const event of req.body.events) {
                try {
                    await handleLineEvent(event, { store, generateId, sendReply });
                } catch (err) {
                    console.error('[LINE] 處理 event 失敗:', err.message);
                }
            }
        }
    );

    console.log('[LINE] Webhook 已掛載於 POST /api/line-webhook');
}

async function handleLineEvent(event, { store, generateId, sendReply }) {
    if (event.type !== 'message' || event.message.type !== 'text') return;

    const userId = event.source.userId;
    const text = event.message.text.trim();
    if (!text) return;

    // 所有 LINE 訊息一律作為任務處理（由 Groq 分類後交 Worker 執行）
    // 注意：本 webhook 掛載在 bot 本地端，實際 LINE Webhook 由 my-gun-relay 處理
    const taskId = generateId('line');
    store.addRecord(taskId, text, false, undefined, userId);
    console.log(`[LINE] 使用者 ${userId} 任務已建立：${taskId}`);
    if (lineClient && event.replyToken) {
        await lineClient.replyMessage({
            replyToken: event.replyToken,
            messages: [{
                type: 'text',
                text: `✅ 任務已收到：「${text.slice(0, 50)}${text.length > 50 ? '…' : ''}」\n等待 Worker 處理中，完成後會回報至 LINE。`
            }]
        });
    }
}

/** LINE 單則訊息長度上限 */
const LINE_TEXT_MAX = 5000;

/**
 * 任務完成時推播結果至 LINE 用戶（由 routes /processed 呼叫）
 * @param {string} userId - LINE userId (event.source.userId)
 * @param {string} text - 要送出的內容（超過 5000 字會自動截斷）
 * @returns {Promise<void>}
 */
async function pushMessage(userId, text) {
    if (!lineClient || !userId) return;
    const str = typeof text === 'string' ? text : String(text);
    const body = str.length > LINE_TEXT_MAX ? str.slice(0, LINE_TEXT_MAX) + '\n...[內容過長已截斷]' : str;
    await lineClient.pushMessage({
        to: userId,
        messages: [{ type: 'text', text: body }]
    });
}

/**
 * 僅初始化 LINE Client（不掛載 Webhook 路由）
 * 供已有外部 Webhook（如 my-gun-relay）但需直接推播功能的場景使用
 * @returns {boolean} 是否初始化成功
 */
function initClient() {
    const channelAccessToken = process.env.LINE_CHANNEL_ACCESS_TOKEN;
    if (!channelAccessToken) return false;
    if (!tryLoadLineSdk()) return false;
    if (!lineClient) {
        lineClient = new lineSdk.messagingApi.MessagingApiClient({ channelAccessToken });
        console.log('[LINE] LINE Client 已初始化（推播模式，不掛載 Webhook 路由）');
    }
    return true;
}

module.exports = { mount, pushMessage, initClient };
