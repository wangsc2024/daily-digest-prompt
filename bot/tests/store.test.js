import { describe, it, expect, beforeEach, afterEach } from 'vitest';
const fs = require('fs');
const path = require('path');

// M9: 每檔專用目錄，避免與 workflow.test.js 共用 data_test 造成 Windows EPERM/ENOENT
const DATA_DIR_STORE = path.join(__dirname, '..', 'data_test_store');
const TASKS_DIR_STORE = path.join(__dirname, '..', 'tasks_md_test_store');

describe('store — integration tests', () => {
    let store;

    function cleanTestRecords() {
        const testPrefix = 'test-';
        for (let i = store.records.length - 1; i >= 0; i--) {
            if (store.records[i].uid.startsWith(testPrefix)) {
                const filePath = path.join(store.TASKS_DIR, store.records[i].filename);
                try { fs.unlinkSync(filePath); } catch {}
                store.records.splice(i, 1);
            }
        }
        const recordsPath = path.join(store.DATA_DIR, 'records.json');
        fs.writeFileSync(recordsPath, JSON.stringify(store.records, null, 2), 'utf8');
    }

    beforeEach(() => {
        process.env.WSC_BOT_DATA_DIR = DATA_DIR_STORE;
        process.env.WSC_BOT_TASKS_DIR = TASKS_DIR_STORE;
        delete require.cache[require.resolve('../lib/store')];
        delete require.cache[require.resolve('../lib/fsm')];
        store = require('../lib/store');
        cleanTestRecords();
    });

    afterEach(() => {
        cleanTestRecords();
        delete require.cache[require.resolve('../lib/store')];
    });

    it('addRecord creates a record and .md file', () => {
        store.addRecord('test-uid-1', 'Test task content', false);
        const { records } = store.queryRecords({});
        const found = records.find(r => r.uid === 'test-uid-1');
        expect(found).toBeDefined();
        expect(found.state).toBe('pending');
        expect(found.is_research).toBe(false);
        expect(found.is_processed).toBe(false);
        expect(found.claim_generation).toBe(0);

        const filePath = path.join(store.TASKS_DIR, 'test-uid-1.md');
        expect(fs.existsSync(filePath)).toBe(true);
        expect(fs.readFileSync(filePath, 'utf8')).toBe('Test task content');
    });

    it('addRecord truncates oversized content (S11)', () => {
        const longContent = 'x'.repeat(60000);
        store.addRecord('test-uid-big', longContent, false);
        const filePath = path.join(store.TASKS_DIR, 'test-uid-big.md');
        const saved = fs.readFileSync(filePath, 'utf8');
        expect(saved.length).toBe(50000);
    });

    it('claimRecord transitions to claimed state', () => {
        store.addRecord('test-uid-2', 'content', false);
        const result = store.claimRecord('test-uid-2', 'worker-1');
        expect(result.status).toBe('claimed');
        expect(result.claim_generation).toBe(0);

        const { records } = store.queryRecords({});
        const rec = records.find(r => r.uid === 'test-uid-2');
        expect(rec.state).toBe('claimed');
        expect(rec.claimed_by).toBe('worker-1');
    });

    it('claimRecord rejects double claim', () => {
        store.addRecord('test-uid-3', 'content', false);
        store.claimRecord('test-uid-3', 'worker-1');
        const result = store.claimRecord('test-uid-3', 'worker-2');
        expect(result.status).toBe('already_claimed');
    });

    it('claimRecord returns not_found for missing uid', () => {
        const result = store.claimRecord('nonexistent', 'worker-1');
        expect(result.status).toBe('not_found');
    });

    it('transitionState works for valid transitions', () => {
        store.addRecord('test-uid-4', 'content', false);
        store.claimRecord('test-uid-4', 'worker-1');
        const rec = store.transitionState('test-uid-4', 'processing', { worker_id: 'worker-1' });
        expect(rec.state).toBe('processing');
    });

    it('transitionState rejects invalid worker', () => {
        store.addRecord('test-uid-5', 'content', false);
        store.claimRecord('test-uid-5', 'worker-1');
        expect(() => {
            store.transitionState('test-uid-5', 'processing', { worker_id: 'wrong-worker' });
        }).toThrow('Worker 不匹配');
    });

    it('transitionState returns null for missing uid', () => {
        const result = store.transitionState('nonexistent', 'claimed');
        expect(result).toBeNull();
    });

    it('transitionState clears claim fields on completed/failed', () => {
        store.addRecord('test-uid-clear', 'content', false);
        store.claimRecord('test-uid-clear', 'worker-1');
        store.transitionState('test-uid-clear', 'processing', { worker_id: 'worker-1' });
        const rec = store.transitionState('test-uid-clear', 'completed', { worker_id: 'worker-1' });
        expect(rec.claimed_by).toBeNull();
        expect(rec.claimed_at).toBeNull();
        expect(rec.is_processed).toBe(true);
    });

    it('markProcessed completes a task (only from processing)', () => {
        store.addRecord('test-uid-6', 'content', false);
        store.claimRecord('test-uid-6', 'worker-1');
        store.transitionState('test-uid-6', 'processing', { worker_id: 'worker-1' });
        const result = store.markProcessed('test-uid-6');
        expect(result).toBe('completed');

        const { records } = store.queryRecords({});
        const rec = records.find(r => r.uid === 'test-uid-6');
        expect(rec.state).toBe('completed');
        expect(rec.is_processed).toBe(true);
    });

    it('markProcessed returns invalid_state when not processing (H2)', () => {
        store.addRecord('test-uid-6b', 'content', false);
        const result = store.markProcessed('test-uid-6b');
        expect(result).toBe('invalid_state');
    });

    it('markProcessed rejects stale claim_generation', () => {
        store.addRecord('test-uid-7', 'content', false);
        store.claimRecord('test-uid-7', 'worker-1');
        store.transitionState('test-uid-7', 'processing', { worker_id: 'worker-1' });
        const result = store.markProcessed('test-uid-7', 999);
        expect(result).toBe('stale_claim');
    });

    it('removeRecord deletes pending tasks', () => {
        store.addRecord('test-uid-8', 'content', false);
        const result = store.removeRecord('test-uid-8');
        expect(result).toBe('removed');
        const { records } = store.queryRecords({});
        expect(records.find(r => r.uid === 'test-uid-8')).toBeUndefined();
    });

    it('removeRecord rejects non-pending tasks (S4)', () => {
        store.addRecord('test-uid-8b', 'content', false);
        store.claimRecord('test-uid-8b', 'worker-1');
        const result = store.removeRecord('test-uid-8b');
        expect(result).toBe('not_cancellable');
    });

    it('queryRecords returns { total, records } with correct total before pagination', () => {
        store.addRecord('test-uid-p1', 'c1', false);
        store.addRecord('test-uid-p2', 'c2', false);
        store.addRecord('test-uid-p3', 'c3', false);

        const result = store.queryRecords({ state: 'pending', limit: 2, offset: 0 });
        expect(result.total).toBeGreaterThanOrEqual(3); // total BEFORE pagination
        expect(result.records.length).toBeLessThanOrEqual(2); // page size
    });

    it('queryRecords filters by state', () => {
        store.addRecord('test-uid-9', 'content', false);
        store.addRecord('test-uid-10', 'content', true);
        store.claimRecord('test-uid-10', 'worker-1');
        store.transitionState('test-uid-10', 'processing', { worker_id: 'worker-1' });
        store.markProcessed('test-uid-10');

        const { records: pending } = store.queryRecords({ state: 'pending' });
        expect(pending.every(r => r.state === 'pending')).toBe(true);

        const { records: completed } = store.queryRecords({ state: 'completed' });
        expect(completed.some(r => r.uid === 'test-uid-10')).toBe(true);
    });

    it('queryRecords filters by is_research', () => {
        store.addRecord('test-uid-11', 'content', true);
        store.addRecord('test-uid-12', 'content', false);

        const { records: research } = store.queryRecords({ is_research: true });
        expect(research.some(r => r.uid === 'test-uid-11')).toBe(true);
        expect(research.some(r => r.uid === 'test-uid-12')).toBe(false);
    });

    it('getRecord returns single record by uid', () => {
        store.addRecord('test-uid-get', 'content', false);
        const rec = store.getRecord('test-uid-get');
        expect(rec).toBeDefined();
        expect(rec.uid).toBe('test-uid-get');
        expect(store.getRecord('nonexistent')).toBeNull();
    });

    it('releaseExpiredClaims releases timed-out claims', () => {
        store.addRecord('test-uid-13', 'content', false);
        store.claimRecord('test-uid-13', 'worker-1');

        const rec = store.records.find(r => r.uid === 'test-uid-13');
        rec.claimed_at = new Date(Date.now() - 11 * 60 * 1000).toISOString();

        const released = store.releaseExpiredClaims();
        expect(released).toBeGreaterThanOrEqual(1);
        expect(rec.state).toBe('pending');
        expect(rec.claim_generation).toBe(1);
    });

    it('addRecord skips duplicate UID', () => {
        store.addRecord('test-uid-dup', 'first content', false);
        store.addRecord('test-uid-dup', 'second content', true);
        const matches = store.records.filter(r => r.uid === 'test-uid-dup');
        expect(matches.length).toBe(1);
        expect(matches[0].is_research).toBe(false);
    });

    it('cron job CRUD works', () => {
        const job = { id: 'cron-test-1', cron_expression: '0 9 * * *', task_content: 'test' };
        store.addCronJob(job);
        expect(store.cronJobs.some(j => j.id === 'cron-test-1')).toBe(true);

        const removed = store.removeCronJob('cron-test-1');
        expect(removed).toBe(true);
        expect(store.cronJobs.some(j => j.id === 'cron-test-1')).toBe(false);
    });
});
