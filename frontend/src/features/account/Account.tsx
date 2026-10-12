import { useEffect, useState } from 'react';
import { api } from '@/lib/api';
import { useAuth } from '@/components/shell/AuthGate';
import { LegalLinks } from '@/components/shell/Legal';
import { Button } from '@/components/ui/button';

function downloadKey(key: string) {
  const url = URL.createObjectURL(new Blob([key + '\n'], { type: 'text/plain' }));
  const anchor = document.createElement('a');
  anchor.href = url; anchor.download = 'collector.key'; anchor.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export default function Account() {
  const auth = useAuth();
  const [profile, setProfile] = useState<Awaited<ReturnType<typeof api.account.profile>>>();
  const [members, setMembers] = useState<Awaited<ReturnType<typeof api.account.list>>>();
  const [key, setKey] = useState('');
  const [invitation, setInvitation] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function refresh() {
    setProfile(await api.account.profile());
    if (auth.role === 'admin') setMembers(await api.account.list());
  }
  useEffect(() => { if (auth.multiUser) void refresh().catch(e => setError(e.message)); }, [auth.multiUser, auth.role]); // eslint-disable-line react-hooks/exhaustive-deps
  async function action(run: () => Promise<void>) {
    setBusy(true); setError('');
    try { await run(); await refresh(); } catch (e) { setError(e instanceof Error ? e.message : 'Request failed'); }
    finally { setBusy(false); }
  }
  if (!auth.multiUser) return <p>Private accounts are available on the hosted deployment. <LegalLinks /></p>;
  return <div className="max-w-[1000px] space-y-6">
    <header><h1 className="text-h1 font-semibold">Your workspace</h1><p className="mt-2 text-body text-graphite">Signed in as {auth.username}. Your logs are separate from other accounts; the server operator can access hosted data.</p></header>
    {error && <p role="alert" className="rounded-panel border border-rule bg-surface p-4 text-int-tampered">{error}</p>}
    <section className="space-y-4 rounded-panel border border-rule bg-surface p-6">
      <h2 className="text-h2 font-semibold">Connect a Windows computer</h2>
      <p className="text-body text-graphite">Only connect computers you own or are authorized to monitor. This sends sign-in event XML, including usernames, device names and IP addresses, to this server. The collector initially includes the last 15 minutes.</p>
      <ol className="list-decimal space-y-3 pl-5 text-body">
        <li><a className="font-medium text-seal underline" href="/api/account/collector-download">Download the Windows collector</a> and extract it into a private folder. Python 3.11 or newer is required.</li>
        <li>Generate a collector key below, download it as <code>collector.key</code>, and put it in the extracted folder.</li>
        <li>Open PowerShell as Administrator, change to that folder and run <code>powershell -NoProfile -ExecutionPolicy Bypass -File .\start.ps1</code>.</li>
      </ol>
      <p className="text-label text-graphite">Keep the collector window open. Ctrl+C stops collection. Use a separate folder for each computer and account.</p>
      <Button disabled={busy || !profile} onClick={() => {
        if (profile?.has_collector_key && !window.confirm('Replace your collector key? Existing collectors will stop until you install the new key.')) return;
        void action(async () => setKey((await api.account.rotateKey()).key));
      }}>{profile?.has_collector_key ? 'Replace collector key' : 'Generate collector key'}</Button>
      {key && <div className="space-y-3 rounded-control border border-rule bg-paper p-4"><p className="text-body">Your new key is ready. Download it now; it cannot be retrieved after you leave this page. Keep it private.</p><Button variant="outline" onClick={() => downloadKey(key)}>Download collector.key</Button></div>}
      {profile && <p className="text-label text-graphite">Pilot limit: {Math.round(profile.raw_limit_bytes / 1024 / 1024)} MiB or 50,000 raw logs per workspace, whichever comes first. This is not a backup service.</p>}
    </section>
    {auth.role === 'admin' && <section className="space-y-4 rounded-panel border border-rule bg-surface p-6">
      <h2 className="text-h2 font-semibold">Manage accounts</h2>
      <p className="text-body text-graphite">Share <a href="/join" className="text-seal underline">{window.location.origin}/join</a> for public signup. Each user gets a private workspace. This small pilot allows {members?.limit ?? 10} accounts, including yours. Disabled accounts still occupy a slot until the operator removes them.</p>
      <p className="text-label text-graphite">You can also create a private invitation that expires after 24 hours.</p>
      <Button disabled={busy} onClick={() => void action(async () => setInvitation((await api.account.invite()).url))}>Create invitation</Button>
      {invitation && <div><label htmlFor="invite-url" className="mb-2 block text-label">Private invitation link — copy and share it yourself</label><input id="invite-url" readOnly value={invitation} onFocus={e => e.target.select()} className="h-11 w-full rounded-control border border-rule bg-paper px-3 text-label" /></div>}
      {members && <ul className="divide-y divide-rule">{members.items.map(member => <li key={member.id} className="flex flex-wrap items-center justify-between gap-3 py-3 text-body"><span>{member.username} · {member.role}{member.disabled ? ' · disabled' : ''}</span>{member.role !== 'admin' && !member.disabled && <Button variant="outline" disabled={busy} onClick={() => {
        if (window.confirm(`Disable ${member.username}? Sign-in and collection will stop. Their stored logs will remain.`)) void action(async () => { await api.account.disable(member.id); });
      }}>Disable account</Button>}</li>)}</ul>}
      {!!members?.invitations.length && <div><h3 className="mb-2 text-label font-semibold">Pending invitations</h3>{members.invitations.map((inv, index) => <div key={inv.id} className="flex items-center justify-between gap-3 py-2 text-label"><span>Invitation {index + 1} · expires {new Date(inv.expires_at * 1000).toLocaleString()}</span><Button variant="outline" disabled={busy} onClick={() => void action(async () => { await api.account.revoke(inv.id); setInvitation(''); })}>Revoke</Button></div>)}</div>}
    </section>}
    <footer className="space-y-3 rounded-panel border border-rule bg-surface p-6"><h2 className="text-h3 font-semibold">Terms and privacy</h2><p className="text-body text-graphite">To request an export, correction, account closure or deletion, use the operator contact in the Privacy notice. Stopping collection or disabling an account does not delete stored logs.</p><LegalLinks /></footer>
  </div>;
}
