/**
 * workflow.js — 工作流引擎
 *
 * 多步驟任務編排：使用者發送複合任務（如「先查天氣再寫穿搭建議」）
 * 時，AI 將其拆解為有依賴關係的步驟，引擎負責自動推進。
 *
 * 設計原則：
 * - 工作流建立在既有 task record 之上，每個步驟 = 一筆 task record
 * - 依賴追蹤：步驟完成後自動建立下游任務
 * - 失敗傳播：步驟失敗時跳過所有下游步驟，工作流標記失敗
 * - 循環檢測：建立時即拒絕含循環依賴的步驟定義
 */
const crypto = require('crypto');
const store = require('./store');

const WF_STATES = {
    PENDING:   'pending',
    RUNNING:   'running',
    COMPLETED: 'completed',
    FAILED:    'failed',
    CANCELLED: 'cancelled'  // H4: 手動取消，與步驟失敗區分
};

const STEP_STATES = {
    PENDING:   'pending',
    ACTIVE:    'active',
    COMPLETED: 'completed',
    FAILED:    'failed',
    SKIPPED:   'skipped'
};

const MAX_STEPS = 20;

function generateWfId() {
    return `wf_${crypto.randomUUID().slice(0, 12)}`;
}

// ---- 核心 API ----

/**
 * 建立工作流並自動啟動無依賴的步驟
 * @param {string} name - 工作流名稱
 * @param {object[]} steps - 步驟定義 [{ id, name?, task_content, is_research?, depends_on? }]
 * @param {string} [sourceId] - 來源訊息 ID
 * @returns {object} 建立後的工作流（含已啟動的步驟）
 */
function createWorkflow(name, steps, sourceId) {
    if (!Array.isArray(steps) || steps.length === 0) {
        throw new Error('工作流必須至少包含一個步驟');
    }
    if (steps.length > MAX_STEPS) {
        throw new Error(`工作流步驟不可超過 ${MAX_STEPS} 個`);
    }

    // 驗證步驟 ID 唯一性與依賴參照
    const stepIds = new Set(steps.map(s => s.id));
    if (stepIds.size !== steps.length) {
        throw new Error('步驟 ID 必須唯一');
    }
    for (const step of steps) {
        if (!step.id || !step.task_content) {
            throw new Error('每個步驟必須有 id 和 task_content');
        }
        for (const dep of (step.depends_on || [])) {
            if (!stepIds.has(dep)) {
                throw new Error(`步驟 ${step.id} 的依賴 ${dep} 不存在`);
            }
        }
    }
    if (hasCircularDeps(steps)) {
        throw new Error('工作流步驟存在循環依賴');
    }

    const wfId = generateWfId();
    const now = new Date().toISOString();

    const workflow = {
        id: wfId,
        name: name || '未命名工作流',
        status: WF_STATES.RUNNING,
        source_id: sourceId || null,
        created_at: now,
        updated_at: now,
        steps: steps.map(s => ({
            id: s.id,
            name: s.name || s.task_content.slice(0, 30),
            task_content: s.task_content,
            is_research: !!s.is_research,
            status: STEP_STATES.PENDING,
            task_uid: null,
            depends_on: s.depends_on || []
        }))
    };

    store.addWorkflow(workflow);
    console.log(`[workflow] 建立工作流 ${wfId}：${workflow.name}（${steps.length} 步驟）`);

    // 自動啟動無依賴步驟
    advanceWorkflow(wfId);
    return store.getWorkflow(wfId);
}

/**
 * 推進工作流：為依賴已滿足的步驟建立 task record
 * @param {string} workflowId
 * @returns {string[]} 新啟動的步驟 ID
 */
function advanceWorkflow(workflowId) {
    const wf = store.getWorkflow(workflowId);
    if (!wf || wf.status !== WF_STATES.RUNNING) return [];

    const completedSteps = new Set(
        wf.steps.filter(s => s.status === STEP_STATES.COMPLETED).map(s => s.id)
    );

    const started = [];
    for (const step of wf.steps) {
        if (step.status !== STEP_STATES.PENDING) continue;
        const depsReady = step.depends_on.every(dep => completedSteps.has(dep));
        if (!depsReady) continue;

        // H6: 將前置步驟的 result 注入到 task_content，供下游步驟使用
        let content = step.task_content;
        for (const depId of step.depends_on) {
            const depStep = wf.steps.find(s => s.id === depId);
            if (depStep && depStep.task_uid) {
                const depRec = store.getRecord(depStep.task_uid);
                if (depRec && depRec.result) {
                    content = content + "\n\n[前置步驟 " + depId + " 的結果]\n" + depRec.result;
                }
            }
        }

        const taskUid = `${workflowId}_${step.id}`;
        store.addRecord(taskUid, content, step.is_research);

        step.status = STEP_STATES.ACTIVE;
        step.task_uid = taskUid;
        started.push(step.id);
        console.log(`[workflow] 啟動步驟 ${step.id}（${step.name}）→ 任務 ${taskUid}`);
    }

    if (started.length > 0) {
        wf.updated_at = new Date().toISOString();
        store.saveWorkflows();
    }
    return started;
}

/**
 * 任務完成回呼：標記步驟完成，推進下游步驟
 * @param {string} taskUid
 * @returns {{ workflowId: string, completed: boolean, stepsStarted: string[] } | null}
 */
function onTaskCompleted(taskUid) {
    const result = findWorkflowByTaskUid(taskUid);
    if (!result) return null;

    const { workflow, step } = result;
    // C3: 工作流已取消時不再推進
    if (workflow.status !== WF_STATES.RUNNING) return null;
    step.status = STEP_STATES.COMPLETED;
    workflow.updated_at = new Date().toISOString();

    // 檢查是否所有步驟都已完成/跳過
    const allDone = workflow.steps.every(
        s => s.status === STEP_STATES.COMPLETED || s.status === STEP_STATES.SKIPPED
    );

    if (allDone) {
        workflow.status = WF_STATES.COMPLETED;
        store.saveWorkflows();
        console.log(`[workflow] 工作流 ${workflow.id} 已全部完成`);
        return { workflowId: workflow.id, completed: true, stepsStarted: [] };
    }

    store.saveWorkflows();
    const stepsStarted = advanceWorkflow(workflow.id);
    return { workflowId: workflow.id, completed: false, stepsStarted };
}

/**
 * 任務失敗回呼：標記步驟失敗，跳過下游步驟
 * @param {string} taskUid
 * @returns {{ workflowId: string } | null}
 */
function onTaskFailed(taskUid) {
    const result = findWorkflowByTaskUid(taskUid);
    if (!result) return null;

    const { workflow, step } = result;
    step.status = STEP_STATES.FAILED;
    workflow.status = WF_STATES.FAILED;
    workflow.updated_at = new Date().toISOString();

    skipDownstream(workflow, step.id);
    store.saveWorkflows();
    console.log(`[workflow] 工作流 ${workflow.id} 因步驟 ${step.id} 失敗而終止`);
    return { workflowId: workflow.id };
}

/**
 * 取消工作流（僅限 running/pending 狀態）
 * @param {string} workflowId
 * @returns {'cancelled'|'not_found'|'not_cancellable'}
 */
function cancelWorkflow(workflowId) {
    const wf = store.getWorkflow(workflowId);
    if (!wf) return 'not_found';
    if (wf.status !== WF_STATES.RUNNING && wf.status !== WF_STATES.PENDING) {
        return 'not_cancellable';
    }

    for (const step of wf.steps) {
        if (step.status === STEP_STATES.ACTIVE && step.task_uid) {
            store.forceTaskFailed(step.task_uid);
        }
        if (step.status === STEP_STATES.PENDING || step.status === STEP_STATES.ACTIVE) {
            step.status = STEP_STATES.SKIPPED;
        }
    }

    wf.status = WF_STATES.CANCELLED;
    wf.updated_at = new Date().toISOString();
    store.saveWorkflows();
    console.log(`[workflow] 工作流 ${workflowId} 已取消`);
    return 'cancelled';
}

// ---- 查詢 ----

/**
 * 查詢工作流列表
 * @param {{ status?: string }} [filters]
 * @returns {{ total: number, workflows: object[] }}
 */
function queryWorkflows(filters = {}) {
    let results = store.workflows;
    if (filters.status) {
        results = results.filter(w => w.status === filters.status);
    }
    const total = results.length;
    if (filters.limit !== undefined) {
        const limit = Math.max(1, Math.min(filters.limit, 100));
        const offset = filters.offset || 0;
        results = results.slice(offset, offset + limit);
    }
    return { total, workflows: results };
}

// ---- 內部輔助函式 ----

function findWorkflowByTaskUid(taskUid) {
    for (const wf of store.workflows) {
        if (wf.status !== WF_STATES.RUNNING) continue;
        for (const step of wf.steps) {
            if (step.task_uid === taskUid) {
                return { workflow: wf, step };
            }
        }
    }
    return null;
}

/** BFS 跳過所有間接依賴 failedStepId 的步驟 */
function skipDownstream(workflow, failedStepId) {
    const toSkip = new Set();
    const queue = [failedStepId];
    while (queue.length > 0) {
        const current = queue.shift();
        for (const step of workflow.steps) {
            if (step.depends_on.includes(current) && !toSkip.has(step.id)) {
                toSkip.add(step.id);
                queue.push(step.id);
            }
        }
    }
    for (const step of workflow.steps) {
        if (toSkip.has(step.id) && step.status === STEP_STATES.PENDING) {
            step.status = STEP_STATES.SKIPPED;
        }
    }
}

/** DFS 檢測循環依賴 */
function hasCircularDeps(steps) {
    const visited = new Set();
    const visiting = new Set();
    const stepMap = new Map(steps.map(s => [s.id, s]));

    function dfs(stepId) {
        if (visiting.has(stepId)) return true;
        if (visited.has(stepId)) return false;
        visiting.add(stepId);
        const step = stepMap.get(stepId);
        if (step) {
            for (const dep of (step.depends_on || [])) {
                if (dfs(dep)) return true;
            }
        }
        visiting.delete(stepId);
        visited.add(stepId);
        return false;
    }

    return steps.some(s => dfs(s.id));
}

module.exports = {
    WF_STATES,
    STEP_STATES,
    MAX_STEPS,
    createWorkflow,
    advanceWorkflow,
    onTaskCompleted,
    onTaskFailed,
    cancelWorkflow,
    queryWorkflows,
    findWorkflowByTaskUid,
    hasCircularDeps
};
