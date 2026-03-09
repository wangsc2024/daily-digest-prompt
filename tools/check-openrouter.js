/**
 * 一次性驗證 OpenRouter API 連線與 API Key
 * 使用方式：node tools/check-openrouter.js
 * 依賴：專案根目錄 .env 中的 OPENROUTER_API_KEY
 */
'use strict';

const path = require('path');
const fs = require('fs');
const { execSync } = require('child_process');

// 讀取 .env（不依賴 dotenv）
const envPath = path.join(__dirname, '..', '.env');
if (fs.existsSync(envPath)) {
    const content = fs.readFileSync(envPath, 'utf8');
    const m = content.match(/OPENROUTER_API_KEY=(.+)/m);
    if (m) process.env.OPENROUTER_API_KEY = m[1].trim();
}
const API_KEY = (process.env.OPENROUTER_API_KEY || '').trim();

if (!API_KEY) {
    console.error('OPENROUTER_API_KEY 未設定（請在 .env 中設定）');
    process.exit(1);
}

const body = JSON.stringify({
    model: process.env.OPENROUTER_MODEL || 'openrouter/free',
    messages: [{ role: 'user', content: 'Reply with exactly: OK' }],
    max_tokens: 20,
});

const tmpFile = path.join(require('os').tmpdir(), `or_check_${Date.now()}.json`);
fs.writeFileSync(tmpFile, body, 'utf8');

try {
    const raw = execSync(
        `curl -s -X POST https://openrouter.ai/api/v1/chat/completions ` +
        `-H "Authorization: Bearer ${API_KEY}" ` +
        `-H "Content-Type: application/json" ` +
        `-d @"${tmpFile}"`,
        { encoding: 'utf8', timeout: 20000 }
    );
    fs.unlinkSync(tmpFile);

    const json = JSON.parse(raw);
    if (json.error) {
        console.error('OpenRouter API 錯誤:', JSON.stringify(json.error));
        process.exit(1);
    }
    const content = json.choices?.[0]?.message?.content || '';
    console.log('OpenRouter 連線正常');
    console.log('模型:', json.model || process.env.OPENROUTER_MODEL || 'openrouter/free');
    console.log('回覆:', content.trim().slice(0, 200));
} catch (e) {
    try { fs.unlinkSync(tmpFile); } catch (_) {}
    console.error('連線失敗:', e.message);
    process.exit(1);
}
