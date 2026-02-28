import { describe, it, expect, beforeEach, afterEach } from 'vitest';
const fs = require('fs');
const path = require('path');
const { DateTime } = require('luxon');

const DATA_DIR_SCHED = path.join(__dirname, '..', 'data_test_scheduled');
const TASKS_DIR_SCHED = path.join(__dirname, '..', 'tasks_md_test_scheduled');

describe('scheduled tasks — store CRUD', () => {
    let store;
    const scheduledPath = () => path.join(DATA_DIR_SCHED, 'scheduled_tasks.json');

    beforeEach(() => {
        if (!fs.existsSync(DATA_DIR_SCHED)) fs.mkdirSync(DATA_DIR_SCHED, { recursive: true });
        fs.writeFileSync(scheduledPath(), '[]', 'utf8');
        process.env.WSC_BOT_DATA_DIR = DATA_DIR_SCHED;
        process.env.WSC_BOT_TASKS_DIR = TASKS_DIR_SCHED;
        delete require.cache[require.resolve('../lib/store')];
        delete require.cache[require.resolve('../lib/fsm')];
        store = require('../lib/store');
    });

    afterEach(() => {
        try {
            if (fs.existsSync(scheduledPath())) fs.unlinkSync(scheduledPath());
        } catch {}
        delete require.cache[require.resolve('../lib/store')];
    });

    it('addScheduledTask persists task and getScheduledTask returns it', () => {
        const task = {
            id: 'sched_abc',
            task_content: 'Remind me at 3pm',
            is_research: false,
            is_workflow: false,
            workflow_data: null,
            scheduled_at: '2026-03-01T15:00:00+08:00',
            created_at: new Date().toISOString(),
            source_id: 'msg_1',
            status: 'waiting'
        };
        store.addScheduledTask(task);
        const got = store.getScheduledTask('sched_abc');
        expect(got).toBeDefined();
        expect(got.task_content).toBe('Remind me at 3pm');
        expect(got.status).toBe('waiting');
    });

    it('queryScheduledTasks filters by status and supports pagination', () => {
        store.addScheduledTask({ id: 's1', task_content: 'A', status: 'waiting', scheduled_at: '2026-03-01T10:00:00+08:00', created_at: new Date().toISOString(), source_id: 'm1', is_research: false, is_workflow: false, workflow_data: null });
        store.addScheduledTask({ id: 's2', task_content: 'B', status: 'waiting', scheduled_at: '2026-03-02T10:00:00+08:00', created_at: new Date().toISOString(), source_id: 'm2', is_research: false, is_workflow: false, workflow_data: null });
        store.addScheduledTask({ id: 's3', task_content: 'C', status: 'triggered', scheduled_at: '2026-03-03T10:00:00+08:00', created_at: new Date().toISOString(), source_id: 'm3', is_research: false, is_workflow: false, workflow_data: null });
        const { total, scheduledTasks } = store.queryScheduledTasks({ status: 'waiting' });
        expect(total).toBe(2);
        expect(scheduledTasks.length).toBe(2);
        const page = store.queryScheduledTasks({ status: 'waiting', limit: 1, offset: 0 });
        expect(page.total).toBe(2);
        expect(page.scheduledTasks.length).toBe(1);
    });

    it('getDueScheduledTasks returns only waiting tasks with scheduled_at <= now', () => {
        const now = new Date().toISOString();
        const past = new Date(Date.now() - 60 * 60 * 1000).toISOString();
        const future = new Date(Date.now() + 60 * 60 * 1000).toISOString();
        store.addScheduledTask({ id: 'due1', task_content: 'Due', status: 'waiting', scheduled_at: past, created_at: new Date().toISOString(), source_id: 'm1', is_research: false, is_workflow: false, workflow_data: null });
        store.addScheduledTask({ id: 'due2', task_content: 'Future', status: 'waiting', scheduled_at: future, created_at: new Date().toISOString(), source_id: 'm2', is_research: false, is_workflow: false, workflow_data: null });
        store.addScheduledTask({ id: 'due3', task_content: 'Triggered', status: 'triggered', scheduled_at: past, created_at: new Date().toISOString(), source_id: 'm3', is_research: false, is_workflow: false, workflow_data: null });
        const due = store.getDueScheduledTasks(now);
        expect(due.length).toBe(1);
        expect(due[0].id).toBe('due1');
    });

    it('markScheduledTaskTriggered updates status', () => {
        store.addScheduledTask({ id: 'trig1', task_content: 'T', status: 'waiting', scheduled_at: '2026-03-01T10:00:00+08:00', created_at: new Date().toISOString(), source_id: 'm1', is_research: false, is_workflow: false, workflow_data: null });
        const ok = store.markScheduledTaskTriggered('trig1');
        expect(ok).toBe(true);
        expect(store.getScheduledTask('trig1').status).toBe('triggered');
    });

    it('cancelScheduledTask sets status to cancelled only when waiting', () => {
        store.addScheduledTask({ id: 'cancel1', task_content: 'C', status: 'waiting', scheduled_at: '2026-03-01T10:00:00+08:00', created_at: new Date().toISOString(), source_id: 'm1', is_research: false, is_workflow: false, workflow_data: null });
        expect(store.cancelScheduledTask('cancel1')).toBe(true);
        expect(store.getScheduledTask('cancel1').status).toBe('cancelled');
        expect(store.cancelScheduledTask('cancel1')).toBe(false);
    });

    it('removeScheduledTask removes by id', () => {
        store.addScheduledTask({ id: 'rem1', task_content: 'R', status: 'waiting', scheduled_at: '2026-03-01T10:00:00+08:00', created_at: new Date().toISOString(), source_id: 'm1', is_research: false, is_workflow: false, workflow_data: null });
        expect(store.removeScheduledTask('rem1')).toBe(true);
        expect(store.getScheduledTask('rem1')).toBeNull();
        expect(store.removeScheduledTask('rem1')).toBe(false);
    });
});

describe('scheduled tasks — classifier validateDecision', () => {
    let validateDecision;

    beforeEach(() => {
        process.env.TIMEZONE = 'Asia/Taipei';
        process.env.SCHEDULED_MAX_DAYS = '7';
        delete require.cache[require.resolve('../lib/classifier')];
        const classifier = require('../lib/classifier');
        validateDecision = classifier.validateDecision;
    });

    afterEach(() => {
        delete require.cache[require.resolve('../lib/classifier')];
    });

    it('accepts valid decision with is_scheduled and future scheduled_at', () => {
        const future = DateTime.now().setZone('Asia/Taipei').plus({ days: 1 }).toISO();
        const parsed = {
            task_content: 'Do this tomorrow',
            is_periodic: false,
            cron_expression: '',
            is_scheduled: true,
            scheduled_at: future,
            is_research: false,
            is_workflow: false
        };
        expect(validateDecision(parsed)).toBe(true);
    });

    it('rejects is_scheduled with past scheduled_at', () => {
        const past = DateTime.now().setZone('Asia/Taipei').minus({ hours: 1 }).toISO();
        const parsed = {
            task_content: 'Done',
            is_periodic: false,
            cron_expression: '',
            is_scheduled: true,
            scheduled_at: past,
            is_research: false,
            is_workflow: false
        };
        expect(validateDecision(parsed)).toBe(false);
    });

    it('rejects is_periodic and is_scheduled both true', () => {
        const future = DateTime.now().setZone('Asia/Taipei').plus({ days: 1 }).toISO();
        const parsed = {
            task_content: 'Both',
            is_periodic: true,
            cron_expression: '0 9 * * *',
            is_scheduled: true,
            scheduled_at: future,
            is_research: false,
            is_workflow: false
        };
        expect(validateDecision(parsed)).toBe(false);
    });

    it('rejects is_scheduled with invalid scheduled_at', () => {
        const parsed = {
            task_content: 'Bad',
            is_periodic: false,
            cron_expression: '',
            is_scheduled: true,
            scheduled_at: 'not-a-date',
            is_research: false,
            is_workflow: false
        };
        expect(validateDecision(parsed)).toBe(false);
    });

    it('accepts decision without is_scheduled (defaults)', () => {
        const parsed = {
            task_content: 'Immediate',
            is_periodic: false,
            cron_expression: '',
            is_research: false,
            is_workflow: false
        };
        expect(validateDecision(parsed)).toBe(true);
    });
});
