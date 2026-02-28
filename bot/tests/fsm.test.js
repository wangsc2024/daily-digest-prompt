import { describe, it, expect } from 'vitest';
const { STATES, canTransition, transition, isClaimExpired, isValidState, CLAIM_TIMEOUT_MS } = require('../lib/fsm');

describe('fsm — STATES', () => {
    it('should define all five states', () => {
        expect(STATES.PENDING).toBe('pending');
        expect(STATES.CLAIMED).toBe('claimed');
        expect(STATES.PROCESSING).toBe('processing');
        expect(STATES.COMPLETED).toBe('completed');
        expect(STATES.FAILED).toBe('failed');
    });
});

describe('fsm — canTransition', () => {
    const valid = [
        ['pending', 'claimed'],
        ['pending', 'completed'],
        ['claimed', 'processing'],
        ['claimed', 'pending'],
        ['claimed', 'completed'],
        ['processing', 'completed'],
        ['processing', 'failed'],
        ['failed', 'pending'],
    ];

    valid.forEach(([from, to]) => {
        it(`allows ${from} → ${to}`, () => {
            expect(canTransition(from, to)).toBe(true);
        });
    });

    const invalid = [
        ['pending', 'processing'],
        ['pending', 'failed'],
        ['claimed', 'failed'],
        ['processing', 'pending'],
        ['processing', 'claimed'],
        ['completed', 'pending'],
        ['completed', 'claimed'],
        ['completed', 'processing'],
        ['completed', 'failed'],
        ['failed', 'claimed'],
        ['failed', 'completed'],
        ['failed', 'processing'],
    ];

    invalid.forEach(([from, to]) => {
        it(`rejects ${from} → ${to}`, () => {
            expect(canTransition(from, to)).toBe(false);
        });
    });

    it('rejects unknown source state', () => {
        expect(canTransition('unknown', 'pending')).toBe(false);
    });
});

describe('fsm — transition', () => {
    it('returns target state on valid transition', () => {
        expect(transition('pending', 'claimed')).toBe('claimed');
    });

    it('throws on invalid transition', () => {
        expect(() => transition('pending', 'failed')).toThrow('不合法的狀態轉換');
    });
});

describe('fsm — isClaimExpired', () => {
    it('returns true when claimedAt is null', () => {
        expect(isClaimExpired(null)).toBe(true);
    });

    it('returns false for recent claim', () => {
        const recent = new Date().toISOString();
        expect(isClaimExpired(recent)).toBe(false);
    });

    it('returns true for expired claim', () => {
        const old = new Date(Date.now() - CLAIM_TIMEOUT_MS - 1000).toISOString();
        expect(isClaimExpired(old)).toBe(true);
    });

    it('respects custom timeout', () => {
        const fiveSecsAgo = new Date(Date.now() - 5000).toISOString();
        expect(isClaimExpired(fiveSecsAgo, 3000)).toBe(true);
        expect(isClaimExpired(fiveSecsAgo, 10000)).toBe(false);
    });
});

describe('fsm — isValidState', () => {
    it('accepts valid states', () => {
        Object.values(STATES).forEach(s => {
            expect(isValidState(s)).toBe(true);
        });
    });

    it('rejects invalid states', () => {
        expect(isValidState('unknown')).toBe(false);
        expect(isValidState('')).toBe(false);
        expect(isValidState(null)).toBe(false);
        expect(isValidState(undefined)).toBe(false);
    });
});

describe('fsm — isClaimExpired NaN safety', () => {
    it('treats invalid date string as expired (safe default)', () => {
        expect(isClaimExpired('not-a-date')).toBe(true);
    });

    it('treats corrupted timestamp as expired', () => {
        expect(isClaimExpired('2024-13-45T99:99:99Z')).toBe(true);
    });
});

describe('fsm — COMPLETED is terminal', () => {
    it('completed has no valid transitions', () => {
        expect(canTransition('completed', 'pending')).toBe(false);
        expect(canTransition('completed', 'claimed')).toBe(false);
        expect(canTransition('completed', 'processing')).toBe(false);
        expect(canTransition('completed', 'failed')).toBe(false);
        expect(canTransition('completed', 'completed')).toBe(false);
    });
});
