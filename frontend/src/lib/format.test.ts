import { describe, expect, it } from 'vitest';
import { DASH, formatEventSummary, formatSrcDst, timeIST } from './format';
import type { EventSummary } from './types';

const base: EventSummary = {
  event_id: 'e-1', raw_id: 'r-1', seq: 1, time: 1790743032000, device: 'fw01', vendor: 'Cisco', format: 'cisco-asa-syslog',
  class_uid: 4001, class_name: 'Network Activity', activity_name: 'Open', src_ip: '198.51.100.9', src_port: 40133,
  dst_ip: '10.2.4.18', dst_port: 443, protocol: 'tcp', direction: 'Inbound', user_name: null, action: 'Allowed', status: null,
  severity: 'Informational', title: null, parse_confidence: 91, batch_id: 11, flags: [],
};
const e = (over: Partial<EventSummary>): EventSummary => ({ ...base, ...over });

describe('formatEventSummary (UI_UX_BRIEF.md §4.4)', () => {
  it.each([
    [e({}), 'Connection opened · inbound TCP'],
    [e({ activity_name: 'Close' }), 'Connection closed'],
    [e({ activity_name: 'Refuse', action: 'Denied' }), 'Connection refused'],
    [e({ activity_name: 'Traffic', action: 'Allowed', device: 'br01' }), 'Session allowed'],
    [e({ class_uid: 2004, title: 'ANVAYA-LAB SCAN Inbound TCP port sweep' }), 'ANVAYA-LAB SCAN Inbound TCP port sweep'],
    [e({ class_uid: 3002, status: 'Failure', user_name: 'admin' }), 'Login failed · admin'],
    [e({ class_uid: 3002, status: 'Success', user_name: 'a.sharma' }), 'Login succeeded · a.sharma'],
  ])('%#', (input, want) => expect(formatEventSummary(input)).toBe(want));

  it('returns a dash for missing values', () => {
    expect(formatEventSummary(e({ class_uid: 2004, title: null }))).toBe(DASH);
    expect(formatEventSummary(e({ class_uid: 3002, status: 'Failure', user_name: null }))).toBe(`Login failed · ${DASH}`);
  });
});

describe('formatSrcDst and timeIST', () => {
  it('shows destination port, and the device for authentication', () => {
    expect(formatSrcDst(base)).toBe('198.51.100.9 → 10.2.4.18:443');
    expect(formatSrcDst(e({ class_uid: 3002, device: 'vpn01', dst_ip: null, dst_port: null }))).toBe('198.51.100.9 → vpn01');
  });
  it('formats IST and never renders undefined', () => {
    expect(timeIST(1790743032000)).toBe('10:07:12');
    expect(timeIST(null)).toBe(DASH);
  });
});
