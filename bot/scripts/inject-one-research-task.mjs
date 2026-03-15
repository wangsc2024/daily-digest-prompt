/**
 * 注入一筆研究型任務到 bot/data/records.json 與 bot/tasks_md/，供單次測試用。
 * 使用方式：
 *   1. node bot/scripts/inject-one-research-task.mjs [任務內容]
 *   2. 重啟 bot（讓 store 重新載入 records.json）
 *   3. 執行 bot/process_messages.ps1（會處理第一筆 pending）
 *
 * 範例：node bot/scripts/inject-one-research-task.mjs "提出八識規矩頌的深入研究報告"
 */
import fs from 'fs';
import path from 'path';

const botDir = path.join(process.cwd(), 'bot');
const dataDir = path.join(botDir, 'data');
const tasksDir = path.join(botDir, 'tasks_md');
const recordsPath = path.join(dataDir, 'records.json');

const taskContent = process.argv[2] || '提出八識規矩頌的深入研究報告';
const uid = 'line_test_bashi_' + Date.now();

const record = {
  uid,
  filename: uid + '.md',
  time: new Date().toISOString(),
  state: 'pending',
  is_processed: false,
  is_research: true,
  task_type: null,
  claimed_by: null,
  claimed_at: null,
  claim_generation: 0,
  result: null,
  retry_count: 0
};

if (!fs.existsSync(dataDir)) fs.mkdirSync(dataDir, { recursive: true });
if (!fs.existsSync(tasksDir)) fs.mkdirSync(tasksDir, { recursive: true });

let records = [];
if (fs.existsSync(recordsPath)) {
  records = JSON.parse(fs.readFileSync(recordsPath, 'utf8'));
}
if (records.some(r => r.uid === uid)) {
  console.log('UID 已存在，跳過:', uid);
  process.exit(0);
}

records.push(record);
fs.writeFileSync(recordsPath, JSON.stringify(records, null, 2), 'utf8');
fs.writeFileSync(path.join(tasksDir, record.filename), taskContent, 'utf8');
console.log('已注入研究型任務:', uid);
console.log('內容:', taskContent.slice(0, 60) + (taskContent.length > 60 ? '…' : ''));
console.log('');
console.log('請重啟 bot 後執行: pwsh -ExecutionPolicy Bypass -File bot/process_messages.ps1');
