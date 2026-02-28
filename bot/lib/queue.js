/**
 * queue.js — 背景任務佇列
 *
 * 遵循 learn-claude-code s08: "Fire and forget"
 * 訊息接收後立即入隊，分類在背景非同步執行，
 * 結果透過回呼通知主迴圈。
 *
 * 安全措施：
 * - onComplete / onError 回呼以 try-catch 保護，防止佇列卡死
 * - 提供 stats() 暴露佇列健康狀態供 /api/health 使用
 * - D1: 佇列最大長度限制，防止記憶體耗盡
 */

/**
 * 建立一個背景任務佇列
 * @param {object} opts
 * @param {number} [opts.concurrency=3] - 最大並行任務數
 * @param {number} [opts.maxSize=1000]  - 佇列最大長度
 * @param {number} [opts.maxRetries=0]  - 處理失敗時重試次數（M3：指數退避）
 * @param {function} opts.processor     - async (item) => result 處理函式
 * @param {function} opts.onComplete    - (item, result) => void 完成回呼
 * @param {function} opts.onError       - (item, error) => void 錯誤回呼
 */
function createQueue({ concurrency = 3, maxSize = 1000, maxRetries = 0, processor, onComplete, onError }) {
    const pending = [];
    let running = 0;
    let dropped = 0;

    function runWithRetry(item) {
        let attempt = 0;
        function run() {
            return processor(item).catch(err => {
                attempt++;
                if (attempt <= maxRetries) {
                    const delayMs = Math.min(1000 * Math.pow(2, attempt - 1), 30000);
                    return new Promise((resolve, reject) => setTimeout(() => run().then(resolve, reject), delayMs));
                }
                return Promise.reject(err);
            });
        }
        return run();
    }

    function drain() {
        while (running < concurrency && pending.length > 0) {
            const item = pending.shift();
            running++;
            runWithRetry(item)
                .then(result => {
                    running--;
                    try { onComplete(item, result); } catch (e) {
                        console.error('[queue] onComplete 回呼異常:', e.message);
                    }
                    drain();
                })
                .catch(err => {
                    running--;
                    try { onError(item, err); } catch (e) {
                        console.error('[queue] onError 回呼異常:', e.message);
                    }
                    drain();
                });
        }
    }

    return {
        /** 將項目加入佇列，超過上限時丟棄並回傳 false */
        push(item) {
            if (pending.length >= maxSize) {
                dropped++;
                console.error(`[queue] 佇列已滿 (${maxSize})，丟棄項目`);
                return false;
            }
            pending.push(item);
            drain();
            return true;
        },

        /** 佇列目前狀態 */
        stats() {
            return { pending: pending.length, running, dropped };
        }
    };
}

module.exports = { createQueue };
