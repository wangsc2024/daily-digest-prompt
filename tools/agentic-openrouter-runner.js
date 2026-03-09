/**
 * tools/agentic-openrouter-runner.js
 *
 * OpenRouter Agentic Runner — Todoist 多後端分派優化 v3
 *
 * 介面：stdin → stdout（與 claude -p 管道介面相同）
 * 用途：作為 Codex fallback 及維護任務的 OpenRouter 後端執行器
 *
 * 工具支援（白名單）：
 *   - Read      → 讀取本地檔案
 *   - Write     → 寫入本地檔案
 *   - Bash      → 執行 shell 命令（受限白名單）
 *   - Grep      → 搜尋檔案內容
 *   - WebFetch  → 取得網頁內容（curl）
 *
 * 環境變數：
 *   OPENROUTER_API_KEY  - 必填
 *   OPENROUTER_MODEL    - 選填（預設 openrouter/free，free tier 自動路由）
 *   AGENT_NAME          - 選填（日誌識別）
 *
 * 啟動：echo "prompt" | node tools/agentic-openrouter-runner.js
 */

'use strict';

const fs   = require('fs');
const path = require('path');
const {execSync, execFileSync} = require('child_process');

// ─── 設定 ───────────────────────────────────────────────
const API_KEY   = (process.env.OPENROUTER_API_KEY || '').trim();
const MODEL     = process.env.OPENROUTER_MODEL || 'openrouter/free';
const FALLBACK_MODEL = 'openrouter/free'; // free tier 自動路由，重試時同樣走 free
const MAX_TURNS = 15;
const AGENT_NAME = process.env.AGENT_NAME || 'openrouter-runner';
const WORKING_DIR = process.cwd();

// bash 白名單（防止危險操作）
const BASH_ALLOWLIST = [
    /^(git|uv|node|python|pwsh|ls|dir|cat|type|grep|find|mkdir|cp|mv|rm|curl|echo|Get-Content)/i,
    /^(Get-ChildItem|Select-String|ConvertFrom-Json|Set-Content|Test-Path|New-Item)/i,
];
const BASH_BLOCKLIST = [
    />\s*nul\b/i,
    />\s*NUL\b/,
    /rm\s+-rf\s+\//,
    /format\s+[a-z]:/i,
    /del\s+\/[sf]/i,
    /shutdown/i,
    /OPENAI_API_KEY|ANTHROPIC_API_KEY|TODOIST_API_TOKEN/,
];

if (!API_KEY) {
    process.stderr.write('[openrouter-runner] ERROR: OPENROUTER_API_KEY not set\n');
    process.exit(1);
}

// ─── Tool 實作 ────────────────────────────────────────────

function toolRead({file_path}) {
    try {
        const resolved = path.isAbsolute(file_path)
            ? file_path
            : path.resolve(WORKING_DIR, file_path);
        if (!fs.existsSync(resolved)) return `Error: File not found: ${file_path}`;
        const content = fs.readFileSync(resolved, 'utf8');
        return content.length > 50000
            ? content.slice(0, 50000) + '\n[...truncated at 50000 chars]'
            : content;
    } catch (e) {
        return `Error reading file: ${e.message}`;
    }
}

function toolWrite({file_path, content}) {
    try {
        const resolved = path.isAbsolute(file_path)
            ? file_path
            : path.resolve(WORKING_DIR, file_path);
        // 防止寫入 nul 或敏感路徑
        if (/\\nul$|\/nul$/i.test(resolved)) return 'Error: Cannot write to nul';
        if (/\.env$/.test(resolved) && !resolved.includes('.env.example')) {
            return 'Error: Cannot write to .env files';
        }
        fs.mkdirSync(path.dirname(resolved), {recursive: true});
        fs.writeFileSync(resolved, content, 'utf8');
        return `OK: Written ${content.length} chars to ${file_path}`;
    } catch (e) {
        return `Error writing file: ${e.message}`;
    }
}

function toolBash({command}) {
    // 安全白名單檢查
    const isAllowed = BASH_ALLOWLIST.some(r => r.test(command.trim()));
    const isBlocked = BASH_BLOCKLIST.some(r => r.test(command));
    if (isBlocked || !isAllowed) {
        return `Error: Command blocked by security policy: ${command.slice(0, 80)}`;
    }
    try {
        const output = execSync(command, {
            cwd: WORKING_DIR,
            encoding: 'utf8',
            timeout: 30000,
            maxBuffer: 1024 * 1024,
        });
        return output || '(no output)';
    } catch (e) {
        return `Error (exit ${e.status}): ${(e.stderr || e.stdout || e.message).slice(0, 2000)}`;
    }
}

function toolGrep({pattern, path: searchPath, glob}) {
    try {
        const target = searchPath
            ? path.resolve(WORKING_DIR, searchPath)
            : WORKING_DIR;
        const args = ['--no-heading', '-n', pattern];
        if (glob) args.push('--glob', glob);
        args.push(target);
        const output = execFileSync('rg', args, {
            cwd: WORKING_DIR,
            encoding: 'utf8',
            timeout: 15000,
            maxBuffer: 512 * 1024,
        });
        return output || '(no matches)';
    } catch (e) {
        if (e.status === 1) return '(no matches)';
        // fallback to grep
        try {
            const grepCmd = `grep -rn ${JSON.stringify(pattern)} ${searchPath || '.'}`;
            return execSync(grepCmd, {cwd: WORKING_DIR, encoding: 'utf8', timeout: 15000});
        } catch (e2) {
            return e2.status === 1 ? '(no matches)' : `Error: ${e2.message}`;
        }
    }
}

function toolWebFetch({url, prompt}) {
    try {
        // 只允許 http/https
        if (!/^https?:\/\//i.test(url)) return 'Error: Only http/https URLs allowed';
        const output = execSync(
            `curl -s -L --max-time 15 --user-agent "Mozilla/5.0 (research-bot)" "${url}"`,
            {encoding: 'utf8', timeout: 20000, maxBuffer: 512 * 1024}
        );
        // 簡單 HTML 清理
        const text = output
            .replace(/<style[^>]*>[\s\S]*?<\/style>/gi, '')
            .replace(/<script[^>]*>[\s\S]*?<\/script>/gi, '')
            .replace(/<[^>]+>/g, ' ')
            .replace(/\s{3,}/g, '\n\n')
            .trim();
        const summary = prompt ? `[WebFetch: ${url}]\n${text.slice(0, 8000)}` : text.slice(0, 8000);
        return summary;
    } catch (e) {
        return `Error fetching ${url}: ${e.message}`;
    }
}

// ─── Tool 分派 ───────────────────────────────────────────

const TOOLS = {
    Read:     toolRead,
    Write:    toolWrite,
    Bash:     toolBash,
    Grep:     toolGrep,
    WebFetch: toolWebFetch,
};

const TOOL_SCHEMAS = [
    {
        type: 'function',
        function: {
            name: 'Read',
            description: 'Read a file from the local filesystem',
            parameters: {
                type: 'object',
                properties: {
                    file_path: {type: 'string', description: 'Absolute or relative path to the file'},
                },
                required: ['file_path'],
            },
        },
    },
    {
        type: 'function',
        function: {
            name: 'Write',
            description: 'Write content to a file',
            parameters: {
                type: 'object',
                properties: {
                    file_path: {type: 'string'},
                    content:   {type: 'string'},
                },
                required: ['file_path', 'content'],
            },
        },
    },
    {
        type: 'function',
        function: {
            name: 'Bash',
            description: 'Execute a shell command (allowlisted commands only)',
            parameters: {
                type: 'object',
                properties: {
                    command: {type: 'string'},
                },
                required: ['command'],
            },
        },
    },
    {
        type: 'function',
        function: {
            name: 'Grep',
            description: 'Search file contents using regex pattern',
            parameters: {
                type: 'object',
                properties: {
                    pattern: {type: 'string'},
                    path:    {type: 'string', description: 'Directory or file to search'},
                    glob:    {type: 'string', description: 'File glob pattern, e.g. *.yaml'},
                },
                required: ['pattern'],
            },
        },
    },
    {
        type: 'function',
        function: {
            name: 'WebFetch',
            description: 'Fetch a web page and return its text content',
            parameters: {
                type: 'object',
                properties: {
                    url:    {type: 'string'},
                    prompt: {type: 'string', description: 'Optional extraction hint'},
                },
                required: ['url'],
            },
        },
    },
];

// ─── OpenRouter API 呼叫 ──────────────────────────────────

async function callOpenRouter(messages, model) {
    const body = JSON.stringify({
        model,
        messages,
        tools: TOOL_SCHEMAS,
        tool_choice: 'auto',
        max_tokens: 4096,
    });

    // 使用 curl 呼叫（避免 npm 依賴）
    const tmpFile = path.join(require('os').tmpdir(), `or_req_${Date.now()}.json`);
    fs.writeFileSync(tmpFile, body, 'utf8');
    try {
        const raw = execSync(
            `curl -s -X POST https://openrouter.ai/api/v1/chat/completions ` +
            `-H "Authorization: Bearer ${API_KEY}" ` +
            `-H "Content-Type: application/json" ` +
            `-H "HTTP-Referer: https://github.com/daily-digest-prompt" ` +
            `-H "X-Title: daily-digest-prompt" ` +
            `-d @"${tmpFile}"`,
            {encoding: 'utf8', timeout: 120000, maxBuffer: 4 * 1024 * 1024}
        );
        fs.unlinkSync(tmpFile);
        return JSON.parse(raw);
    } catch (e) {
        try { fs.unlinkSync(tmpFile); } catch {}
        throw new Error(`OpenRouter API error: ${e.message}`);
    }
}

// ─── Agentic 主循環 ───────────────────────────────────────

async function run(prompt) {
    const messages = [
        {role: 'system', content: '你是一個能讀寫檔案、搜尋程式碼、取得網頁內容的 Agent。請以正體中文輸出分析報告。執行任務後，輸出清晰的結構化報告。'},
        {role: 'user', content: prompt},
    ];

    let currentModel = MODEL;
    let turns = 0;

    process.stderr.write(`[${AGENT_NAME}] Starting (model=${currentModel}, max_turns=${MAX_TURNS})\n`);

    while (turns < MAX_TURNS) {
        turns++;
        let resp;
        try {
            resp = await callOpenRouter(messages, currentModel);
        } catch (e) {
            process.stderr.write(`[${AGENT_NAME}] API error: ${e.message}, trying fallback model\n`);
            if (currentModel !== FALLBACK_MODEL) {
                currentModel = FALLBACK_MODEL;
                try {
                    resp = await callOpenRouter(messages, currentModel);
                } catch (e2) {
                    process.stderr.write(`[${AGENT_NAME}] Fallback also failed: ${e2.message}\n`);
                    process.exit(1);
                }
            } else {
                process.exit(1);
            }
        }

        if (resp.error) {
            process.stderr.write(`[${AGENT_NAME}] API responded with error: ${JSON.stringify(resp.error)}\n`);
            process.exit(1);
        }

        const choice  = resp.choices?.[0];
        const message = choice?.message;
        if (!message) {
            process.stderr.write(`[${AGENT_NAME}] No message in response\n`);
            break;
        }

        messages.push({role: 'assistant', content: message.content || '', tool_calls: message.tool_calls});

        // 完成：沒有 tool_calls
        if (!message.tool_calls || message.tool_calls.length === 0) {
            const finalText = message.content || '';
            process.stdout.write(finalText + '\n');
            process.stderr.write(`[${AGENT_NAME}] Done after ${turns} turns\n`);
            return;
        }

        // 並行執行所有 tool_calls
        const toolResults = await Promise.all(
            message.tool_calls.map(async (tc) => {
                const toolName = tc.function.name;
                let args;
                try {
                    args = JSON.parse(tc.function.arguments || '{}');
                } catch {
                    args = {};
                }
                const toolFn = TOOLS[toolName];
                let result;
                if (toolFn) {
                    try {
                        result = String(toolFn(args));
                    } catch (e) {
                        result = `Error executing ${toolName}: ${e.message}`;
                    }
                } else {
                    result = `Error: Unknown tool ${toolName}`;
                }
                process.stderr.write(`[${AGENT_NAME}] Tool ${toolName} -> ${result.length} chars\n`);
                return {
                    role: 'tool',
                    tool_call_id: tc.id,
                    content: result,
                };
            })
        );

        messages.push(...toolResults);
    }

    process.stderr.write(`[${AGENT_NAME}] Max turns (${MAX_TURNS}) reached\n`);
    // 輸出最後一條 assistant 訊息（若有）
    const lastAssistant = [...messages].reverse().find(m => m.role === 'assistant');
    if (lastAssistant?.content) process.stdout.write(lastAssistant.content + '\n');
}

// ─── 入口：讀取 stdin ─────────────────────────────────────

let inputChunks = [];
process.stdin.setEncoding('utf8');
process.stdin.on('data', chunk => inputChunks.push(chunk));
process.stdin.on('end', () => {
    const prompt = inputChunks.join('').trim();
    if (!prompt) {
        process.stderr.write('[openrouter-runner] ERROR: No input from stdin\n');
        process.exit(1);
    }
    run(prompt).catch(e => {
        process.stderr.write(`[openrouter-runner] FATAL: ${e.message}\n`);
        process.exit(1);
    });
});
