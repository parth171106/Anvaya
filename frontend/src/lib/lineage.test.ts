import { describe, expect, it } from 'vitest';
import { buildFields, fieldOrder, flattenOcsf, spanToPath } from './lineage';
import { tokenizeSql } from './sqlHighlight';
import type { LineageEntry } from './types';

const lineage: LineageEntry[] = [
  { path: 'time', spans: [[57, 88]], derived: true },
  { path: 'evidences[0].src_endpoint.ip', spans: [[166, 178]], derived: false },
  { path: 'finding_info.title', spans: [[328, 366]], derived: false },
  { path: 'unmapped.event_type', spans: [[149, 154]], derived: false },
  { path: 'activity_name', spans: [[149, 154]], derived: true },
  { path: 'outer', spans: [[100, 200]], derived: false },
];

describe('spanToPath', () => {
  it('picks the narrowest span containing the offset', () => {
    expect(spanToPath(lineage, 170)).toBe('evidences[0].src_endpoint.ip');
    expect(spanToPath(lineage, 150)).toBe('unmapped.event_type');
    expect(spanToPath(lineage, 120)).toBe('outer');
    expect(spanToPath(lineage, 5)).toBeNull();
  });
  it('treats spans as half-open [start, end)', () => {
    expect(spanToPath(lineage, 166)).toBe('evidences[0].src_endpoint.ip');
    expect(spanToPath(lineage, 178)).toBe('outer');
  });
});

describe('fieldOrder', () => {
  it('puts class fields first and unmapped last', () => {
    const order = fieldOrder(['unmapped.flow_id', 'finding_info.title', 'metadata.uid', 'time', 'class_uid',
      'evidences[0].src_endpoint.ip', 'severity']);
    expect(order[0]).toBe('class_uid');
    expect(order.at(-1)).toBe('unmapped.flow_id');
    expect(order.indexOf('time')).toBeLessThan(order.indexOf('evidences[0].src_endpoint.ip'));
    expect(order.indexOf('finding_info.title')).toBeLessThan(order.indexOf('metadata.uid'));
  });
});

describe('buildFields', () => {
  it('flattens with lineage notation and marks kinds', () => {
    const ocsf = { class_uid: 2004, time: 1, evidences: [{ src_endpoint: { ip: '198.51.100.9' } }], raw_data: 'x',
      unmapped: { event_type: 'alert' }, observables: [{ name: 'a' }] };
    expect(flattenOcsf(ocsf).map((f) => f.path)).toContain('evidences[0].src_endpoint.ip');
    const fields = buildFields(ocsf, lineage);
    const by = Object.fromEntries(fields.map((f) => [f.path, f]));
    expect(by['evidences[0].src_endpoint.ip'].kind).toBe('direct');
    expect(by.time.kind).toBe('derived');
    expect(by.class_uid.kind).toBe('none');
    expect(by['unmapped.event_type'].kind).toBe('unmapped');
    expect(by['unmapped.event_type'].colorIndex).toBe(-1);
    expect(fields.some((f) => f.path === 'raw_data' || f.path.startsWith('observables'))).toBe(false);
  });
});

describe('tokenizeSql', () => {
  it('classifies keywords, strings, numbers and the parameter', () => {
    const t = tokenizeSql("SELECT src_ip FROM events WHERE dst_ip = '10.2.4.18' AND time >= :now_ms - 3600000 LIMIT 200");
    const of = (type: string) => t.filter((x) => x.type === type).map((x) => x.text);
    expect(of('keyword')).toEqual(['SELECT', 'FROM', 'WHERE', 'AND', 'LIMIT']);
    expect(of('string')).toEqual(["'10.2.4.18'"]);
    expect(of('number')).toEqual(['3600000', '200']);
    expect(of('param')).toEqual([':now_ms']);
    expect(t.map((x) => x.text).join('')).toBe("SELECT src_ip FROM events WHERE dst_ip = '10.2.4.18' AND time >= :now_ms - 3600000 LIMIT 200");
  });
});
