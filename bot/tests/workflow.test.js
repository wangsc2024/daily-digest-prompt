import { describe, it, expect, beforeEach, afterEach } from 'vitest';
const fs = require('fs');
const path = require('path');

// M9: 每檔專用目錄，避免與 store.test.js 共用 data_test 造成 Windows EPERM/ENOENT
const DATA_DIR_WF = path.join(__dirname, '..', 'data_test_workflow');
const TASKS_DIR_WF = path.join(__dirname, '..', 'tasks_md_test_workflow');

describe('workflow — engine tests', () => {
    let store, workflow;

    function cleanTestData() {
        // 清理 test workflow
        for (let i = store.workflows.length - 1; i >= 0; i--) {
            if (store.workflows[i].id.startsWith('wf_') || store.workflows[i].name.startsWith('test-')) {
                store.workflows.splice(i, 1);
            }
        }
        const wfPath = path.join(store.DATA_DIR, 'workflows.json');
        fs.writeFileSync(wfPath, JSON.stringify(store.workflows, null, 2), 'utf8');

        // 清理 test records
        const testPrefix = 'wf_';
        for (let i = store.records.length - 1; i >= 0; i--) {
            if (store.records[i].uid.startsWith(testPrefix) || store.records[i].uid.startsWith('test-')) {
                const filePath = path.join(store.TASKS_DIR, store.records[i].filename);
                try { fs.unlinkSync(filePath); } catch {}
                store.records.splice(i, 1);
            }
        }
        const recordsPath = path.join(store.DATA_DIR, 'records.json');
        fs.writeFileSync(recordsPath, JSON.stringify(store.records, null, 2), 'utf8');
    }

    beforeEach(() => {
        process.env.WSC_BOT_DATA_DIR = DATA_DIR_WF;
        process.env.WSC_BOT_TASKS_DIR = TASKS_DIR_WF;
        delete require.cache[require.resolve('../lib/store')];
        delete require.cache[require.resolve('../lib/fsm')];
        delete require.cache[require.resolve('../lib/workflow')];
        store = require('../lib/store');
        workflow = require('../lib/workflow');
        cleanTestData();
    });

    afterEach(() => {
        cleanTestData();
        delete require.cache[require.resolve('../lib/store')];
        delete require.cache[require.resolve('../lib/workflow')];
    });

    // ---- createWorkflow ----

    it('creates a linear workflow and auto-starts first step', () => {
        const steps = [
            { id: 's1', task_content: '步驟一', is_research: false, depends_on: [] },
            { id: 's2', task_content: '步驟二', is_research: true, depends_on: ['s1'] }
        ];
        const wf = workflow.createWorkflow('test-linear', steps);

        expect(wf.status).toBe('running');
        expect(wf.steps.length).toBe(2);
        expect(wf.steps[0].status).toBe('active');
        expect(wf.steps[0].task_uid).toContain('_s1');
        expect(wf.steps[1].status).toBe('pending');
        expect(wf.steps[1].task_uid).toBeNull();

        // 應建立第一步的 task record
        const rec = store.getRecord(wf.steps[0].task_uid);
        expect(rec).toBeDefined();
        expect(rec.state).toBe('pending');
    });

    it('starts multiple steps with no dependencies in parallel', () => {
        const steps = [
            { id: 's1', task_content: '平行一', depends_on: [] },
            { id: 's2', task_content: '平行二', depends_on: [] },
            { id: 's3', task_content: '彙整', depends_on: ['s1', 's2'] }
        ];
        const wf = workflow.createWorkflow('test-parallel', steps);

        expect(wf.steps[0].status).toBe('active');
        expect(wf.steps[1].status).toBe('active');
        expect(wf.steps[2].status).toBe('pending');
    });

    it('rejects empty steps', () => {
        expect(() => workflow.createWorkflow('test', [])).toThrow('至少包含一個步驟');
    });

    it('rejects steps exceeding max limit', () => {
        const steps = Array.from({ length: 21 }, (_, i) => ({
            id: `s${i}`, task_content: `步驟${i}`, depends_on: []
        }));
        expect(() => workflow.createWorkflow('test', steps)).toThrow('不可超過');
    });

    it('rejects duplicate step IDs', () => {
        const steps = [
            { id: 's1', task_content: 'a', depends_on: [] },
            { id: 's1', task_content: 'b', depends_on: [] }
        ];
        expect(() => workflow.createWorkflow('test', steps)).toThrow('唯一');
    });

    it('rejects invalid dependency references', () => {
        const steps = [
            { id: 's1', task_content: 'a', depends_on: ['s99'] }
        ];
        expect(() => workflow.createWorkflow('test', steps)).toThrow('不存在');
    });

    it('rejects circular dependencies', () => {
        const steps = [
            { id: 's1', task_content: 'a', depends_on: ['s2'] },
            { id: 's2', task_content: 'b', depends_on: ['s1'] }
        ];
        expect(() => workflow.createWorkflow('test', steps)).toThrow('循環依賴');
    });

    it('rejects steps without task_content', () => {
        const steps = [{ id: 's1', depends_on: [] }];
        expect(() => workflow.createWorkflow('test', steps)).toThrow('task_content');
    });

    // ---- onTaskCompleted ----

    it('advances workflow when step completes', () => {
        const steps = [
            { id: 's1', task_content: '步驟一', depends_on: [] },
            { id: 's2', task_content: '步驟二', depends_on: ['s1'] }
        ];
        const wf = workflow.createWorkflow('test-advance', steps);
        const s1Uid = wf.steps[0].task_uid;

        const result = workflow.onTaskCompleted(s1Uid);
        expect(result).not.toBeNull();
        expect(result.completed).toBe(false);
        expect(result.stepsStarted).toContain('s2');

        // 檢查步驟二已啟動
        const updated = store.getWorkflow(wf.id);
        expect(updated.steps[0].status).toBe('completed');
        expect(updated.steps[1].status).toBe('active');
        expect(updated.steps[1].task_uid).toBeTruthy();
    });

    it('completes workflow when all steps done', () => {
        const steps = [
            { id: 's1', task_content: '唯一步驟', depends_on: [] }
        ];
        const wf = workflow.createWorkflow('test-done', steps);
        const s1Uid = wf.steps[0].task_uid;

        const result = workflow.onTaskCompleted(s1Uid);
        expect(result.completed).toBe(true);

        const updated = store.getWorkflow(wf.id);
        expect(updated.status).toBe('completed');
    });

    it('completes workflow after parallel merge', () => {
        const steps = [
            { id: 's1', task_content: '平行一', depends_on: [] },
            { id: 's2', task_content: '平行二', depends_on: [] },
            { id: 's3', task_content: '彙整', depends_on: ['s1', 's2'] }
        ];
        const wf = workflow.createWorkflow('test-merge', steps);

        // 完成 s1 → s3 還不能啟動（s2 未完成）
        workflow.onTaskCompleted(wf.steps[0].task_uid);
        let updated = store.getWorkflow(wf.id);
        expect(updated.steps[2].status).toBe('pending');

        // 完成 s2 → s3 啟動
        workflow.onTaskCompleted(wf.steps[1].task_uid);
        updated = store.getWorkflow(wf.id);
        expect(updated.steps[2].status).toBe('active');

        // 完成 s3 → 工作流完成
        const result = workflow.onTaskCompleted(updated.steps[2].task_uid);
        expect(result.completed).toBe(true);
    });

    it('returns null for non-workflow tasks', () => {
        const result = workflow.onTaskCompleted('nonexistent_uid');
        expect(result).toBeNull();
    });

    // ---- onTaskFailed ----

    it('marks workflow failed and skips downstream on step failure', () => {
        const steps = [
            { id: 's1', task_content: '步驟一', depends_on: [] },
            { id: 's2', task_content: '步驟二', depends_on: ['s1'] },
            { id: 's3', task_content: '步驟三', depends_on: ['s2'] }
        ];
        const wf = workflow.createWorkflow('test-fail', steps);

        const result = workflow.onTaskFailed(wf.steps[0].task_uid);
        expect(result).not.toBeNull();

        const updated = store.getWorkflow(wf.id);
        expect(updated.status).toBe('failed');
        expect(updated.steps[0].status).toBe('failed');
        expect(updated.steps[1].status).toBe('skipped');
        expect(updated.steps[2].status).toBe('skipped');
    });

    it('returns null for non-workflow task failures', () => {
        expect(workflow.onTaskFailed('nonexistent')).toBeNull();
    });

    // ---- cancelWorkflow ----

    it('cancels a running workflow', () => {
        const steps = [
            { id: 's1', task_content: '步驟一', depends_on: [] },
            { id: 's2', task_content: '步驟二', depends_on: ['s1'] }
        ];
        const wf = workflow.createWorkflow('test-cancel', steps);

        const result = workflow.cancelWorkflow(wf.id);
        expect(result).toBe('cancelled');

        const updated = store.getWorkflow(wf.id);
        expect(updated.status).toBe('cancelled');  // H4: 手動取消用 CANCELLED 與步驟失敗區分
        expect(updated.steps[0].status).toBe('skipped');
        expect(updated.steps[1].status).toBe('skipped');
    });

    it('returns not_found for missing workflow', () => {
        expect(workflow.cancelWorkflow('wf_nonexistent')).toBe('not_found');
    });

    it('returns not_cancellable for completed workflow', () => {
        const steps = [{ id: 's1', task_content: '步驟', depends_on: [] }];
        const wf = workflow.createWorkflow('test-nc', steps);
        workflow.onTaskCompleted(wf.steps[0].task_uid);
        expect(workflow.cancelWorkflow(wf.id)).toBe('not_cancellable');
    });

    // ---- queryWorkflows ----

    it('queries workflows with status filter', () => {
        const steps = [{ id: 's1', task_content: 'a', depends_on: [] }];
        workflow.createWorkflow('test-q1', steps);
        const wf2 = workflow.createWorkflow('test-q2', steps);
        workflow.onTaskCompleted(wf2.steps[0].task_uid);

        const running = workflow.queryWorkflows({ status: 'running' });
        expect(running.workflows.every(w => w.status === 'running')).toBe(true);

        const completed = workflow.queryWorkflows({ status: 'completed' });
        expect(completed.workflows.some(w => w.name === 'test-q2')).toBe(true);
    });

    it('supports pagination', () => {
        const steps = [{ id: 's1', task_content: 'a', depends_on: [] }];
        workflow.createWorkflow('test-p1', steps);
        workflow.createWorkflow('test-p2', steps);
        workflow.createWorkflow('test-p3', steps);

        const page = workflow.queryWorkflows({ limit: 2, offset: 0 });
        expect(page.total).toBeGreaterThanOrEqual(3);
        expect(page.workflows.length).toBeLessThanOrEqual(2);
    });

    // ---- hasCircularDeps ----

    it('detects no cycle in linear chain', () => {
        const steps = [
            { id: 's1', depends_on: [] },
            { id: 's2', depends_on: ['s1'] },
            { id: 's3', depends_on: ['s2'] }
        ];
        expect(workflow.hasCircularDeps(steps)).toBe(false);
    });

    it('detects direct cycle', () => {
        const steps = [
            { id: 's1', depends_on: ['s2'] },
            { id: 's2', depends_on: ['s1'] }
        ];
        expect(workflow.hasCircularDeps(steps)).toBe(true);
    });

    it('detects indirect cycle', () => {
        const steps = [
            { id: 's1', depends_on: ['s3'] },
            { id: 's2', depends_on: ['s1'] },
            { id: 's3', depends_on: ['s2'] }
        ];
        expect(workflow.hasCircularDeps(steps)).toBe(true);
    });
});

describe('workflow — classifier integration', () => {
    it('validateWorkflowDecomposition accepts valid decomposition', () => {
        const { validateWorkflowDecomposition } = require('../lib/classifier');
        const valid = {
            name: '測試工作流',
            steps: [
                { id: 's1', task_content: '步驟一', is_research: false, depends_on: [] },
                { id: 's2', task_content: '步驟二', is_research: true, depends_on: ['s1'] }
            ]
        };
        expect(validateWorkflowDecomposition(valid)).toBe(true);
    });

    it('validateWorkflowDecomposition rejects single step', () => {
        const { validateWorkflowDecomposition } = require('../lib/classifier');
        const single = {
            name: '單步驟',
            steps: [{ id: 's1', task_content: 'only one', depends_on: [] }]
        };
        expect(validateWorkflowDecomposition(single)).toBe(false);
    });

    it('validateWorkflowDecomposition rejects missing name', () => {
        const { validateWorkflowDecomposition } = require('../lib/classifier');
        expect(validateWorkflowDecomposition({ steps: [{ id: 's1', task_content: 'a' }, { id: 's2', task_content: 'b' }] })).toBe(false);
    });

    it('validateWorkflowDecomposition rejects null', () => {
        const { validateWorkflowDecomposition } = require('../lib/classifier');
        expect(validateWorkflowDecomposition(null)).toBe(false);
    });

    it('validateWorkflowDecomposition rejects duplicate IDs', () => {
        const { validateWorkflowDecomposition } = require('../lib/classifier');
        const dup = {
            name: 'dup',
            steps: [
                { id: 's1', task_content: 'a', depends_on: [] },
                { id: 's1', task_content: 'b', depends_on: [] }
            ]
        };
        expect(validateWorkflowDecomposition(dup)).toBe(false);
    });
});
