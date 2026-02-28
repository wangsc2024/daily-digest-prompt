import { describe, it, expect, vi } from 'vitest';
const { createQueue } = require('../lib/queue');

describe('queue — basic operations', () => {
    it('processes items and calls onComplete', async () => {
        const results = [];
        const q = createQueue({
            concurrency: 1,
            processor: async (item) => item.value * 2,
            onComplete: (item, result) => results.push({ item, result }),
            onError: () => {},
        });

        q.push({ value: 5 });
        await new Promise(r => setTimeout(r, 50));
        expect(results).toHaveLength(1);
        expect(results[0].result).toBe(10);
    });

    it('calls onError when processor throws', async () => {
        const errors = [];
        const q = createQueue({
            concurrency: 1,
            processor: async () => { throw new Error('boom'); },
            onComplete: () => {},
            onError: (item, err) => errors.push(err.message),
        });

        q.push({ value: 1 });
        await new Promise(r => setTimeout(r, 50));
        expect(errors).toEqual(['boom']);
    });

    it('respects concurrency limit', async () => {
        let maxRunning = 0;
        let current = 0;

        const q = createQueue({
            concurrency: 2,
            processor: async () => {
                current++;
                if (current > maxRunning) maxRunning = current;
                await new Promise(r => setTimeout(r, 30));
                current--;
                return 'done';
            },
            onComplete: () => {},
            onError: () => {},
        });

        q.push({});
        q.push({});
        q.push({});
        q.push({});

        await new Promise(r => setTimeout(r, 200));
        expect(maxRunning).toBe(2);
    });

    it('reports stats correctly', () => {
        const q = createQueue({
            concurrency: 1,
            processor: async () => new Promise(r => setTimeout(r, 1000)),
            onComplete: () => {},
            onError: () => {},
        });

        expect(q.stats()).toEqual({ pending: 0, running: 0, dropped: 0 });
        q.push({});
        q.push({});
        expect(q.stats().running).toBe(1);
        expect(q.stats().pending).toBe(1);
    });

    it('survives onComplete callback exception', async () => {
        const results = [];
        const q = createQueue({
            concurrency: 1,
            processor: async (item) => item.value,
            onComplete: (item, result) => {
                if (result === 1) throw new Error('callback boom');
                results.push(result);
            },
            onError: () => {},
        });

        q.push({ value: 1 });
        q.push({ value: 2 });

        await new Promise(r => setTimeout(r, 100));
        expect(results).toEqual([2]);
    });

    // D1: Queue max size
    it('drops items when queue is full (D1)', () => {
        const q = createQueue({
            concurrency: 1,
            maxSize: 3,
            processor: async () => new Promise(r => setTimeout(r, 1000)),
            onComplete: () => {},
            onError: () => {},
        });

        expect(q.push({})).toBe(true); // starts running
        expect(q.push({})).toBe(true); // pending 1
        expect(q.push({})).toBe(true); // pending 2
        expect(q.push({})).toBe(true); // pending 3
        expect(q.push({})).toBe(false); // dropped — pending is full (3)
        expect(q.stats().dropped).toBe(1);
    });
});
