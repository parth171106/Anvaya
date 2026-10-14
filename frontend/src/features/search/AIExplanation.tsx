import { useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { Link } from 'react-router';
import { Button } from '@/components/ui/button';
import { api } from '@/lib/api';

export function AIExplanation({ kind, target }: { kind: 'search' | 'incident'; target: string }) {
  const [consent, setConsent] = useState(false);
  const status = useQuery({ queryKey: ['ai-status'], queryFn: api.ai.status, staleTime: 60_000 });
  const preview = useMutation({ mutationFn: () => api.ai.preview(kind, target) });
  const explanation = useMutation({ mutationFn: () => api.ai.explain(kind, target, consent, preview.data!.preview_id) });
  const enabled = status.data?.evidence_enabled;
  return <section className="mt-5 space-y-3 rounded-panel border border-rule bg-surface p-5">
    <h2 className="text-h3 font-semibold">{kind === 'search' ? 'Explain these results' : 'Explain this incident'} with AI</h2>
    <p className="text-body text-graphite">Get a summary with evidence references and suggested investigation steps. AI can be wrong; verify each claim. This does not perform an integrity check or change your system.</p>
    {!enabled ? <p className="text-body">{status.isPending ? 'Checking AI availability…' : status.isError ? 'Could not check AI availability.' : 'Evidence explanations are not enabled by the operator.'}</p> : <>
      <p className="text-body text-graphite">Google Gemini receives the context and up to {kind === 'search' ? '30 result rows' : '20 linked events'} shown in the preview. This can include IP addresses, usernames and device names. Free-tier data may be used to improve Google products; use only synthetic or non-sensitive data unless your operator has arranged suitable paid processing.</p>
      <Button variant="outline" disabled={preview.isPending || explanation.isPending} onClick={() => { setConsent(false); preview.mutate(); }}>Preview data to be shared</Button>
      {preview.error && <p role="alert" className="text-body">{preview.error.message}</p>}
      {preview.data && <>
        <details className="text-body" open><summary>Preview: {preview.data.sample_count} of {preview.data.returned_count} returned rows</summary>
          <pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap break-all rounded-control bg-paper-sunk p-3 text-mono">{JSON.stringify(preview.data, null, 2)}</pre>
        </details>
        <label className="flex items-start gap-2 text-body"><input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} className="mt-1" />I authorize sending this evidence and context to Google Gemini for this explanation.</label>
        <Button disabled={!consent || explanation.isPending} onClick={() => explanation.mutate()}>{explanation.isPending ? 'Reviewing evidence…' : 'Explain and suggest next steps'}</Button>
      </>}
    </>}
    {explanation.error && <p role="alert" className="text-body">{explanation.error.message}</p>}
    {explanation.data && <div className="space-y-3" aria-live="polite">
      <p className="text-label text-graphite">AI-generated · {explanation.data.model} · {explanation.data.sample_count} of {explanation.data.returned_count} returned rows reviewed. Text fields capped at 256 characters. References identify source records, not proof that every claim is correct.</p>
      <ul className="list-disc space-y-3 pl-5">{explanation.data.claims.map((claim, i) => <li key={i} className="text-body">
        {claim.text}{' '}{claim.citations.map((id) => {
          const ref = explanation.data.references[id];
          return ref.href.startsWith('#') ? <a className="mr-2 text-seal underline" key={id} href={ref.href}>{ref.label}</a>
            : <Link className="mr-2 text-seal underline" key={id} to={ref.href}>{ref.label}</Link>;
        })}
      </li>)}</ul>
      <h3 className="font-semibold">Suggested investigation</h3>
      <ol className="list-decimal space-y-2 pl-5">{explanation.data.steps.map((step, i) => <li key={i} className="text-body">{step}</li>)}</ol>
    </div>}
  </section>;
}
