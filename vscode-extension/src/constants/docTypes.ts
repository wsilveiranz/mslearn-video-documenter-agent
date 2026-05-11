export const DOC_TYPES = [
    { label: '📘 Tutorial', value: 'tutorial', description: 'Step-by-step learning exercise with checklist' },
    { label: '⚡ Quickstart', value: 'quickstart', description: 'Get started quickly with a focused task' },
    { label: '🔧 How-to', value: 'how-to', description: 'Task-oriented guide for a specific goal' },
    { label: '💡 Concept', value: 'concept', description: 'Explain what something is and how it works' },
    { label: '🔍 Overview', value: 'overview', description: 'High-level product or service introduction' },
];

const DOC_TYPE_ALIASES: Array<{ alias: string; value: string }> = [
    { alias: 'quickstart', value: 'quickstart' },
    { alias: 'quick start', value: 'quickstart' },
    { alias: 'quick-start', value: 'quickstart' },
    { alias: 'tutorial', value: 'tutorial' },
    { alias: 'tutorials', value: 'tutorial' },
    { alias: 'how-to', value: 'how-to' },
    { alias: 'how to', value: 'how-to' },
    { alias: 'howto', value: 'how-to' },
    { alias: 'concept', value: 'concept' },
    { alias: 'concepts', value: 'concept' },
    { alias: 'overview', value: 'overview' },
];

export const DOC_TYPE_PATTERNS: Array<{ value: string; patterns: RegExp[] }> = [
    { value: 'quickstart', patterns: [/\bquick\s*-?\s*start\b/] },
    { value: 'tutorial', patterns: [/\btutorial\b/] },
    { value: 'how-to', patterns: [/\bhow[\s-]*to\b/] },
    { value: 'concept', patterns: [/\bconcept\b/] },
    { value: 'overview', patterns: [/\boverview\b/] },
];

function levenshtein(a: string, b: string): number {
    const m = a.length;
    const n = b.length;
    const dp: number[][] = Array.from({ length: m + 1 }, (_, i) =>
        Array.from({ length: n + 1 }, (_, j) => (i === 0 ? j : j === 0 ? i : 0))
    );
    for (let i = 1; i <= m; i++) {
        for (let j = 1; j <= n; j++) {
            dp[i][j] = a[i - 1] === b[j - 1]
                ? dp[i - 1][j - 1]
                : 1 + Math.min(dp[i - 1][j], dp[i][j - 1], dp[i - 1][j - 1]);
        }
    }
    return dp[m][n];
}

export function fuzzyMatchDocType(input: string): string | undefined {
    const words = input.split(/\s+/).filter(Boolean);
    const candidates: string[] = [];
    for (let i = 0; i < words.length; i++) {
        candidates.push(words[i]);
        if (i + 1 < words.length) { candidates.push(`${words[i]} ${words[i + 1]}`); }
        if (i + 2 < words.length) { candidates.push(`${words[i]} ${words[i + 1]} ${words[i + 2]}`); }
    }

    let bestValue: string | undefined;
    let bestDist = Infinity;

    for (const candidate of candidates) {
        for (const { alias, value } of DOC_TYPE_ALIASES) {
            const dist = levenshtein(candidate, alias);
            if (dist < bestDist) {
                bestDist = dist;
                bestValue = value;
            }
        }
    }

    return bestDist <= 2 ? bestValue : undefined;
}
