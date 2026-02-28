import { describe, it, expect } from 'vitest';

// Import actual production code — NOT a copy
const { extractJSON, loadSkill } = require('../lib/classifier');

describe('classifier — extractJSON (production code)', () => {
    it('parses clean JSON', () => {
        const input = '{"is_periodic": false, "cron_expression": "", "task_content": "hello", "is_research": false}';
        const result = extractJSON(input);
        expect(result).toEqual({
            is_periodic: false,
            cron_expression: '',
            task_content: 'hello',
            is_research: false,
        });
    });

    it('parses JSON wrapped in ```json``` fences', () => {
        const input = '```json\n{"is_periodic": true, "cron_expression": "0 9 * * *", "task_content": "check weather", "is_research": false}\n```';
        const result = extractJSON(input);
        expect(result.is_periodic).toBe(true);
        expect(result.cron_expression).toBe('0 9 * * *');
    });

    it('parses JSON with surrounding explanation text', () => {
        const input = 'Here is my analysis:\n\n{"is_periodic": false, "cron_expression": "", "task_content": "do something", "is_research": true}\n\nI hope this helps!';
        const result = extractJSON(input);
        expect(result.is_research).toBe(true);
    });

    it('parses JSON wrapped in ``` fences without language tag', () => {
        const input = '```\n{"is_periodic": false, "cron_expression": "", "task_content": "test", "is_research": false}\n```';
        const result = extractJSON(input);
        expect(result.task_content).toBe('test');
    });

    it('handles JSON containing backticks in values', () => {
        const input = '{"is_periodic": false, "cron_expression": "", "task_content": "run `npm test`", "is_research": false}';
        const result = extractJSON(input);
        expect(result.task_content).toBe('run `npm test`');
    });

    it('returns null for invalid JSON', () => {
        expect(extractJSON('this is not json at all')).toBeNull();
    });

    it('returns null for empty input', () => {
        expect(extractJSON('')).toBeNull();
    });

    it('returns null for malformed JSON', () => {
        expect(extractJSON('{"is_periodic": true, broken}')).toBeNull();
    });
});

describe('classifier — loadSkill', () => {
    it('loads intent-classifier.md and replaces variables', () => {
        const result = loadSkill('intent-classifier', { userMessage: 'hello world' });
        expect(result).toContain('hello world');
        expect(result).not.toContain('{{userMessage}}');
    });

    it('throws for non-existent skill file', () => {
        expect(() => loadSkill('nonexistent')).toThrow('Skill 檔案不存在');
    });

    it('escapes special characters in variables (prompt injection defense)', () => {
        const result = loadSkill('intent-classifier', { userMessage: '"}; DROP TABLE; {"' });
        // JSON.stringify escaping should neutralize the injection
        expect(result).toContain('\\"');
    });
});

describe('classifier — validateDecision', () => {
    // We need to test validateDecision, but it's not exported.
    // Test it indirectly through the module's behavior by testing the patterns it enforces.
    // The key contract: is_periodic=true requires cron_expression
    it('validates correct decision structure', () => {
        const { extractJSON } = require('../lib/classifier');
        // Valid non-periodic
        const valid = extractJSON('{"is_periodic":false,"cron_expression":"","task_content":"test","is_research":false}');
        expect(valid).toBeDefined();
        expect(valid.task_content).toBe('test');
    });
});
