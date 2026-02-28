/**
 * M9: 測試使用隔離的 data / tasks_md 目錄，避免與生產資料互相干擾
 */
const path = require('path');

const root = path.join(__dirname, '..');
process.env.WSC_BOT_DATA_DIR = path.join(root, 'data_test');
process.env.WSC_BOT_TASKS_DIR = path.join(root, 'tasks_md_test');
