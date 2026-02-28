/**
 * skills.js — 集中式 Skill 載入與管理
 *
 * 職責：
 * - 從 skills/ 目錄載入 .md 模板，支援 {{key}} 變數替換
 * - 提供 listSkills() 供動態發現可用技能
 * - 快取模板，支援 clearCache() 以便開發時熱重載
 *
 * 安全：使用者輸入以 JSON.stringify 逃脫後插入，防止 prompt injection
 */
const fs = require('fs');
const path = require('path');

const SKILLS_DIR = process.env.WSC_BOT_SKILLS_DIR || path.join(__dirname, '..', 'skills');
const skillCache = new Map();

/**
 * 列出所有可用 skill 名稱（不含 .md）
 * @returns {string[]}
 */
function listSkills() {
    if (!fs.existsSync(SKILLS_DIR)) return [];
    const names = fs.readdirSync(SKILLS_DIR, { withFileTypes: true })
        .filter(f => f.isFile() && f.name.endsWith('.md'))
        .map(f => f.name.slice(0, -3));
    return names.sort();
}

/**
 * 載入 skill 模板並替換佔位符
 * @param {string} skillName - 不含副檔名的 skill 名稱
 * @param {Record<string, string|number|boolean>} vars - {{key}} → value 對照，會轉成字串並逃脫
 * @returns {string} 替換後的 prompt 字串
 */
function loadSkill(skillName, vars = {}) {
    let template = skillCache.get(skillName);
    if (!template) {
        const filePath = path.join(SKILLS_DIR, `${skillName}.md`);
        if (!fs.existsSync(filePath)) {
            throw new Error(`Skill 檔案不存在: ${skillName}.md`);
        }
        template = fs.readFileSync(filePath, 'utf8');
        skillCache.set(skillName, template);
    }
    let result = template;
    for (const [key, value] of Object.entries(vars)) {
        const str = value === undefined || value === null ? '' : String(value);
        const safe = JSON.stringify(str).slice(1, -1);
        result = result.replace(new RegExp(`\\{\\{${key}\\}\\}`, 'g'), safe);
    }
    return result;
}

/**
 * 清除 skill 快取（開發時熱重載用）
 * @param {string} [skillName] - 若提供則只清除該 skill，否則清除全部
 */
function clearCache(skillName) {
    if (skillName) skillCache.delete(skillName);
    else skillCache.clear();
}

/**
 * 取得 skill 原始內容（不替換變數），用於除錯或預覽
 * @param {string} skillName
 * @returns {string|null} 檔案內容，不存在則 null
 */
function getSkillRaw(skillName) {
    const filePath = path.join(SKILLS_DIR, `${skillName}.md`);
    if (!fs.existsSync(filePath)) return null;
    return fs.readFileSync(filePath, 'utf8');
}

module.exports = {
    SKILLS_DIR,
    listSkills,
    loadSkill,
    clearCache,
    getSkillRaw
};
