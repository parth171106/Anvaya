// A tiny SQL tokenizer for the Search SQL block (UI_UX_BRIEF.md §5.5): keywords in --seal, strings in --dev-vpn01,
// numbers in --dev-fw01, everything else in --ink.
export type SqlTokenType = 'keyword' | 'string' | 'number' | 'param' | 'ident' | 'punct' | 'space';
export interface SqlToken { type: SqlTokenType; text: string; }

const KEYWORDS = new Set([
  'SELECT', 'FROM', 'WHERE', 'AND', 'OR', 'NOT', 'IN', 'IS', 'NULL', 'AS', 'ORDER', 'BY', 'GROUP', 'HAVING', 'LIMIT',
  'DESC', 'ASC', 'COUNT', 'SUM', 'MIN', 'MAX', 'AVG', 'LIKE', 'BETWEEN', 'DISTINCT', 'WITH', 'ON', 'JOIN', 'CASE',
  'WHEN', 'THEN', 'ELSE', 'END', 'LOWER', 'UPPER', 'SUBSTR', 'LENGTH', 'COALESCE', 'STRFTIME', 'DATETIME', 'OFFSET',
]);
const RX = /(\s+)|('(?:[^']|'')*')|(:[A-Za-z_]\w*)|(\d+(?:\.\d+)?)|([A-Za-z_]\w*)|([^\s\w])/g;

export function tokenizeSql(sql: string): SqlToken[] {
  const out: SqlToken[] = [];
  for (const m of sql.matchAll(RX)) {
    const [text, space, str, param, num, word] = m;
    if (space) out.push({ type: 'space', text });
    else if (str) out.push({ type: 'string', text });
    else if (param) out.push({ type: 'param', text });
    else if (num) out.push({ type: 'number', text });
    else if (word) out.push({ type: KEYWORDS.has(word.toUpperCase()) ? 'keyword' : 'ident', text });
    else out.push({ type: 'punct', text });
  }
  return out;
}

export const SQL_COLOR: Record<SqlTokenType, string> = {
  keyword: 'var(--seal)', string: 'var(--dev-vpn01)', number: 'var(--dev-fw01)', param: 'var(--dev-ids01)',
  ident: 'var(--ink)', punct: 'var(--graphite)', space: 'inherit',
};
