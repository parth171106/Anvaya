import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { api } from '@/lib/api';
import type { IncidentDetail } from '@/lib/types';
import { Button } from '@/components/ui/button';

export default function SSHResponse({ incident }: { incident: IncidentDetail }) {
  const [device, setDevice] = useState(incident.devices[0] ?? '');
  const [minutes, setMinutes] = useState<5 | 15>(5);
  const prepare = useMutation({ mutationFn: () => api.incidents.blockPlan(incident.incident_id, device, minutes) });
  const allowed = incident.workflow?.assessment === 'suspicious' && !incident.workflow?.controlled_test && incident.workflow?.state !== 'resolved';
  const current = prepare.data && prepare.data.device === device && prepare.data.minutes === minutes;
  function download() {
    if (!prepare.data) return;
    const url = URL.createObjectURL(new Blob([JSON.stringify(prepare.data, null, 2)], { type: 'application/json' }));
    const anchor = document.createElement('a');
    anchor.href = url; anchor.download = 'anvaya-block-plan.json'; anchor.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  return <section className="mt-4 min-w-0 space-y-3 rounded-panel border border-rule bg-surface p-5 [overflow-wrap:anywhere]">
    <h2 className="text-h3 font-semibold">Temporary SSH response</h2>
    <p className="text-body text-graphite">Prepare a plan to block new SSH connections from {incident.attacker_ip}. Applying it requires a separate approval on the affected Linux server. Preparing or downloading a plan does not block anything.</p>
    <p className="text-body text-graphite">Existing sessions remain open. The server helper rejects protected addresses and connected SSH clients, and the kernel expires the block automatically. This console cannot verify whether a downloaded plan was applied.</p>
    {!allowed && <p className="text-body">Review the evidence, save the assessment as Suspicious, and keep the investigation open. Controlled tests cannot prepare block plans.</p>}
    <div className="flex flex-wrap items-end gap-3">
      <label className="flex min-w-0 flex-col gap-1 text-label">Affected device
        <select value={device} onChange={e => { setDevice(e.target.value); prepare.reset(); }} className="min-h-11 max-w-full rounded-control border border-rule bg-surface px-3 text-body text-ink">
          {incident.devices.map(d => <option key={d} value={d}>{d}</option>)}
        </select>
      </label>
      <label className="flex flex-col gap-1 text-label">Duration
        <select value={minutes} onChange={e => { setMinutes(Number(e.target.value) as 5 | 15); prepare.reset(); }} className="min-h-11 rounded-control border border-rule bg-surface px-3 text-body text-ink">
          <option value={5}>5 minutes</option><option value={15}>15 minutes</option>
        </select>
      </label>
      <Button disabled={!allowed || prepare.isPending} onClick={() => prepare.mutate()}>Prepare block plan</Button>
    </div>
    {prepare.isError && <p role="alert" className="text-body text-sev-high">{prepare.error.message}</p>}
    {current && allowed && <div role="status" className="space-y-3 rounded-control bg-paper-sunk p-4">
      <p className="text-body">Plan prepared, not applied: {prepare.data!.source_ip} → {device}, new SSH connections only, {minutes} minutes. Approval deadline: {new Date(prepare.data!.expires_at * 1000).toLocaleTimeString()}.</p>
      <Button variant="outline" onClick={download}>Download plan</Button>
      <p className="text-body">Transfer the plan to the affected server. Follow docs/SSH-RESPONSE.md to preview it with collectors/ssh_response.py, specify your protected management IPs, and approve locally. Never test a block against your own management IP.</p>
    </div>}
  </section>;
}
