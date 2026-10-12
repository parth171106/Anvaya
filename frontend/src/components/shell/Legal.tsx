import { useEffect, useState } from 'react';
import { api, type LegalNotice } from '@/lib/api';

export function LegalLinks() {
  return <span className="inline-flex flex-wrap gap-3 text-label text-graphite">
    <a href="/terms" target="_blank" rel="noopener noreferrer" className="underline">Terms & conditions</a>
    <a href="/privacy" target="_blank" rel="noopener noreferrer" className="underline">Privacy notice</a>
  </span>;
}

export function LegalPage({ privacy }: { privacy: boolean }) {
  const [notice, setNotice] = useState<LegalNotice>();
  const [error, setError] = useState(false);
  useEffect(() => { api.legal().then(setNotice).catch(() => setError(true)); }, []);
  return <main className="min-h-screen overflow-y-auto bg-paper px-6 py-12">
    <article className="mx-auto max-w-[760px] rounded-panel border border-rule bg-surface p-8">
      <a href="/overview" className="text-label font-semibold text-seal">ANVAYA · Back to console</a>
      <h1 className="mt-6 text-h1 font-semibold">{privacy ? 'Privacy notice' : 'Terms & conditions'}</h1>
      {!notice && <p className="my-6" role={error ? 'alert' : undefined}>{error ? 'Could not load this notice. Reload the page to try again.' : 'Loading…'}</p>}
      {notice && <>
        <p className="mt-3 text-label text-graphite">Version {notice.version} · Educational pilot</p>
        <p className="mt-6 text-body"><strong>Operator:</strong> {notice.operator}<br /><strong>Contact:</strong> {notice.contact}</p>
        {(privacy ? notice.privacy : notice.terms).map(section => <section key={section.title} className="mt-8">
          <h2 className="text-h3 font-semibold">{section.title}</h2>
          <p className="mt-2 text-body leading-relaxed text-graphite">{section.text}</p>
        </section>)}
        <div className="mt-8 border-t border-rule pt-6"><LegalLinks /></div>
      </>}
    </article>
  </main>;
}

export function TermsCheckbox({ checked, onChange }: { checked: boolean; onChange: (value: boolean) => void }) {
  return <div className="space-y-3 text-label">
    <LegalLinks />
    <label className="flex items-start gap-3 leading-relaxed">
      <input type="checkbox" required checked={checked} onChange={event => onChange(event.target.checked)} className="mt-1 shrink-0" />
      <span>I am at least 18, agree to the Terms & conditions and acknowledge the Privacy notice. I will only upload logs I am authorized to share.</span>
    </label>
  </div>;
}
