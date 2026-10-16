import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Button } from '@/components/ui/button';
import { api, ApiError } from '@/lib/api';
import { qk } from '@/lib/queryKeys';
import type { IncidentDetail, IncidentWorkflow } from '@/lib/types';

export const WORKFLOW_LABELS = { new: 'New', investigating: 'Investigating', resolved: 'Resolved' };

export default function Investigation({ incident }: { incident: IncidentDetail }) {
  const client = useQueryClient();
  const [draft, setDraft] = useState<IncidentWorkflow>(incident.workflow ?? { state: 'new', controlled_test: false, version: 0 });
  const [note, setNote] = useState('');
  const [message, setMessage] = useState('');
  const save = useMutation({
    mutationFn: () => api.incidents.investigate(incident.incident_id, { ...draft, note }),
    onSuccess: (updated) => {
      setDraft(updated.workflow!);
      setNote('');
      setMessage('Investigation saved.');
      client.setQueryData(qk.incident(incident.incident_id), updated);
      void client.invalidateQueries({ queryKey: qk.incidents });
      void client.invalidateQueries({ queryKey: qk.stats });
    },
  });
  const reload = useMutation({
    mutationFn: () => api.incidents.get(incident.incident_id),
    onSuccess: (updated) => {
      setDraft(updated.workflow!);
      client.setQueryData(qk.incident(incident.incident_id), updated);
      save.reset();
      setMessage('Latest status loaded. Your unsaved note has been kept.');
    },
  });
  const changed = note.trim() || draft.state !== incident.workflow?.state || draft.controlled_test !== incident.workflow?.controlled_test;
  const pending = save.isPending || reload.isPending;
  return <section className="mt-5 min-w-0 rounded-panel border border-rule bg-surface p-4 sm:p-5" aria-labelledby="investigation-heading">
    <h2 id="investigation-heading" className="text-h3 font-semibold">Investigation</h2>
    <p className="mt-1 text-body text-graphite">Track your review here. Notes and labels do not change the original logs or their integrity proofs.</p>
    <form className="mt-4 space-y-4" onSubmit={(event) => { event.preventDefault(); setMessage(''); save.mutate(); }}>
      <fieldset disabled={pending} className="min-w-0 space-y-4">
        <div className="flex flex-wrap items-end gap-4">
          <label className="flex min-w-0 flex-col gap-1 text-label font-medium">Status
            <select className="min-h-11 max-w-full rounded-chip border border-rule bg-surface px-3 text-body text-ink" value={draft.state}
              onChange={(event) => setDraft({ ...draft, state: event.target.value as IncidentWorkflow['state'] })}>
              {Object.entries(WORKFLOW_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
          </label>
          <label className="flex min-h-11 items-center gap-2 text-body">
            <input type="checkbox" checked={draft.controlled_test} onChange={(event) => setDraft({ ...draft, controlled_test: event.target.checked })} />
            Controlled test
          </label>
        </div>
        <label className="block text-label font-medium" htmlFor="investigation-note">Add investigation note</label>
        <textarea id="investigation-note" rows={3} maxLength={5000} value={note} onChange={(event) => setNote(event.target.value)}
          className="block w-full min-w-0 resize-y rounded-chip border border-rule bg-surface p-3 text-body text-ink"
          placeholder="What did you check, and what did you find?" aria-describedby="note-help" />
        <p id="note-help" className="text-label text-graphite">Optional · {note.length}/5,000 characters. Saved notes remain in the activity history.</p>
        <Button type="submit" disabled={!changed || pending}>{save.isPending ? 'Saving…' : 'Save investigation'}</Button>
      </fieldset>
      {save.isError && <p role="alert" className="break-words text-body text-sev-high">{save.error.message}</p>}
      {save.error instanceof ApiError && save.error.status === 409 && <Button type="button" variant="outline" disabled={pending} onClick={() => reload.mutate()}>Load latest status; keep my note</Button>}
      {reload.isError && <p role="alert" className="text-body text-sev-high">{reload.error.message}</p>}
      <p role="status" className="text-body text-graphite">{message}</p>
    </form>
    <details className="mt-3 border-t border-rule pt-3" open={(incident.activity?.length ?? 0) > 0}>
      <summary className="cursor-pointer text-label font-semibold">Activity · latest 100 updates</summary>
      {!incident.activity?.length && <p className="mt-2 text-body text-graphite">No investigation updates yet.</p>}
      <ol className="mt-3 max-h-96 space-y-3 overflow-y-auto" aria-label="Investigation activity">
        {incident.activity?.map((entry) => <li key={entry.id} className="min-w-0 rounded-chip bg-paper-sunk p-3">
          <p className="break-words text-label text-graphite">{entry.actor} · {new Date(entry.at).toLocaleString()} · {WORKFLOW_LABELS[entry.state]}{entry.controlled_test ? ' · Controlled test' : ''}</p>
          {entry.note && <p className="mt-1 whitespace-pre-wrap break-words text-body [overflow-wrap:anywhere]">{entry.note}</p>}
        </li>)}
      </ol>
    </details>
  </section>;
}
