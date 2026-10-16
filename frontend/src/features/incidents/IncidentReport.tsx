import { useState } from 'react';
import { Download } from 'lucide-react';
import { api } from '@/lib/api';
import { Button } from '@/components/ui/button';

export default function IncidentReport({ incidentId }: { incidentId: string }) {
  const [verify, setVerify] = useState(true);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  async function download() {
    setBusy(true); setMessage('');
    try {
      const blob = await api.incidents.report(incidentId, verify);
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url; link.download = `anvaya-${incidentId.replace(/[^a-zA-Z0-9_-]/g, '_')}-report.pdf`;
      document.body.appendChild(link); link.click(); link.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
      setMessage('Report ready. Check your browser downloads.');
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Could not download the report. Please retry.');
    } finally { setBusy(false); }
  }
  return <section className="mt-4 rounded-panel border border-rule bg-surface p-5" aria-labelledby="incident-report-title">
    <h2 id="incident-report-title" className="text-h3 font-semibold">Incident report</h2>
    <p className="mt-2 text-body text-graphite">Download a PDF with the timeline, linked evidence, and saved investigation notes.
      Includes up to 200 events and the latest 100 activity entries; omissions are disclosed. Save any note edits first.</p>
    <label className="my-3 flex items-start gap-2 text-body">
      <input type="checkbox" className="mt-1 shrink-0" checked={verify} disabled={busy} onChange={(e) => setVerify(e.target.checked)} />
      <span>Verify included raw records now. Uncheck to export with integrity marked Not checked.</span>
    </label>
    <Button onClick={download} disabled={busy}><Download className="size-4" aria-hidden />
      {busy ? 'Preparing report…' : 'Download PDF report'}</Button>
    <p className="mt-2 text-label text-graphite">Contains account evidence and notes. Share only with intended recipients.</p>
    <p role="status" aria-live="polite" className="mt-2 break-words text-body">{message}</p>
  </section>;
}
