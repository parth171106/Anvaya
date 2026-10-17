import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Bell } from 'lucide-react';
import { Link } from 'react-router';
import { Button } from '@/components/ui/button';
import { EmptyState, ErrorState, PageHeader } from '@/components/common/states';
import { api } from '@/lib/api';
import { qk } from '@/lib/queryKeys';

const date = (ms: number) => new Date(ms).toLocaleString();
const DELIVERY: Record<string, string> = {
  pending: 'Telegram queued / retrying', sent: 'Accepted by Telegram', failed: 'Telegram delivery failed',
  disabled: 'Telegram was not enabled', historical: 'Not sent: old or future-dated event',
  suppressed: 'Not sent: demo, controlled test, or expected activity', expired: 'Not sent: delivery window expired',
  cancelled: 'Not sent: connection changed or disconnected',
};

function TelegramSettings() {
  const client = useQueryClient();
  const q = useQuery({ queryKey: qk.telegram, queryFn: api.alerts.telegram });
  const [token, setToken] = useState('');
  const [chat, setChat] = useState('');
  const [consent, setConsent] = useState(false);
  const [message, setMessage] = useState('');
  const action = useMutation({
    mutationFn: async (kind: 'connect' | 'test' | 'disable') => {
      if (kind === 'connect') await api.alerts.configure(token.trim(), chat.trim(), consent);
      else if (kind === 'test') await api.alerts.test();
      else await api.alerts.disable();
      return kind;
    },
    onSuccess: (kind) => {
      setToken(''); setConsent(false);
      setMessage(kind === 'connect' ? 'Connected. New eligible findings will send Telegram alerts. Use Send test message to check delivery.'
        : kind === 'test' ? 'Test message accepted by Telegram. Check your private chat.' : 'Disconnected. Saved credentials removed and pending deliveries cancelled.');
      void client.invalidateQueries({ queryKey: qk.telegram });
      void client.invalidateQueries({ queryKey: qk.alerts });
    },
  });
  return <section className="rounded-panel border border-rule bg-surface p-4 sm:p-5 [overflow-wrap:anywhere]">
    <h2 className="text-h3 font-semibold">Telegram direct messages</h2>
    {q.isError ? <p role="alert">Could not load Telegram settings. <button className="underline" onClick={() => void q.refetch()}>Retry</button></p>
      : <p className="mt-2 text-body">{q.isPending ? 'Loading settings…' : q.data.enabled ? `Connected to @${q.data.bot_username ?? 'your bot'} · private chat ${q.data.chat_id}` : 'Not connected. Alerts are still saved in your private inbox.'}</p>}
    <p className="mt-2 text-body text-graphite">New SSH threshold findings and success-after-failure escalations are grouped by incident. Older imports, demo data, and findings marked controlled or expected are not sent. Delivery can fail; the inbox shows the outcome.</p>
    <details className="mt-4" open={!q.isPending && !q.data?.enabled}>
      <summary className="cursor-pointer text-body font-medium">{q.data?.enabled ? 'Replace connection' : 'Set up your bot'}</summary>
      <ol className="mt-3 list-decimal space-y-2 pl-5 text-body text-graphite">
        <li>In Telegram, open @BotFather, send /newbot, and follow its instructions. Use a dedicated ANVAYA bot.</li>
        <li>Open your new bot and press Start. Enter the token below, not in a public issue or an AI chat.</li>
        <li>Enter your numeric private chat ID. The repository guide docs/SSH-ALERTS.md includes a local helper to find it without putting your token in a browser URL.</li>
      </ol>
      <form className="mt-4 space-y-3" onSubmit={e => { e.preventDefault(); setMessage(''); action.mutate('connect'); }}>
        <label className="block text-label font-medium">Bot token
          <input type="password" autoComplete="off" maxLength={150} required value={token} onChange={e => setToken(e.target.value)}
            className="mt-1 min-h-11 w-full rounded-control border border-rule bg-surface px-3 text-body text-ink" />
        </label>
        <label className="block text-label font-medium">Private chat ID
          <input inputMode="numeric" autoComplete="off" maxLength={19} required value={chat} onChange={e => setChat(e.target.value)}
            className="mt-1 min-h-11 w-full rounded-control border border-rule bg-surface px-3 text-body text-ink" />
        </label>
        <label className="flex items-start gap-2 text-body">
          <input className="mt-1 shrink-0" type="checkbox" checked={consent} onChange={e => setConsent(e.target.checked)} />
          <span>I control this bot and private chat. Send alert titles, source IPs, device names, counts, timestamps and incident links to Telegram. Store this bot token privately on the ANVAYA server for delivery.</span>
        </label>
        <p className="text-label text-graphite">Raw logs, passwords, analyst notes and AI explanations are not included. The server operator can access the saved token. Disconnecting removes it; messages already sent remain in Telegram.</p>
        <Button type="submit" disabled={action.isPending || !consent || !token.trim() || !chat.trim()}>Connect Telegram</Button>
      </form>
    </details>
    {q.data?.enabled && <div className="mt-4 flex flex-wrap gap-3">
      <Button disabled={action.isPending} onClick={() => { setMessage(''); action.mutate('test'); }}>Send test message</Button>
      <Button variant="outline" disabled={action.isPending} onClick={() => { setMessage(''); action.mutate('disable'); }}>Disconnect and forget token</Button>
    </div>}
    {action.isError && <p role="alert" className="mt-3 text-body text-sev-high">{action.error.message}</p>}
    <p role="status" className="mt-3 text-body text-graphite">{action.isPending ? 'Working…' : message}</p>
  </section>;
}

export default function Alerts() {
  const client = useQueryClient();
  const [before, setBefore] = useState<number>();
  const q = useQuery({ queryKey: [...qk.alerts, before ?? null], queryFn: () => api.alerts.list(before), refetchInterval: 15_000 });
  const ack = useMutation({ mutationFn: api.alerts.acknowledge, onSuccess: () => { void client.invalidateQueries({ queryKey: qk.alerts }); } });
  return <div className="min-w-0 space-y-5">
    <PageHeader title="Alert inbox" subtitle="SSH findings that need a decision. Alerts do not block traffic." />
    <TelegramSettings />
    <div className="flex flex-wrap items-center justify-between gap-3">
      <h2 className="text-h2 font-semibold">{q.data?.unread ?? 0} unread alerts</h2>
      <Button variant="outline" onClick={() => { setBefore(undefined); void q.refetch(); }}>Refresh latest</Button>
    </div>
    {ack.isError && <p role="alert" className="text-sev-high">{ack.error.message}</p>}
    {q.isPending ? <p>Loading alerts…</p> : q.isError ? <ErrorState title="Couldn't load alerts" onRetry={() => void q.refetch()} />
      : !q.data.items.length ? <EmptyState icon={Bell} title="No SSH alerts yet" body="Ten distinct failed SSH connections from one IP to one device in a 10-minute correlation window create a finding. A later successful login can escalate it. Ordinary successful logins do not trigger alerts." />
      : <div className="space-y-3">{q.data.items.map(a => <article key={a.id} className="min-w-0 rounded-panel border border-rule bg-surface p-4 sm:p-5 [overflow-wrap:anywhere]">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <h3 className="text-h3 font-semibold"><Link to={`/incidents/${a.incident_id}`} className="text-seal hover:underline">{a.payload.title}</Link></h3>
          <span className="text-label font-medium">{a.payload.level} · {a.seen_at ? 'Read' : 'Unread'}</span>
        </div>
        <p className="mt-2 text-body">{a.payload.source_ip} · {a.payload.devices.join(', ')} · {a.payload.failure_count} failed connections at detection</p>
        <p className="mt-2 text-label text-graphite">Event: {date(a.event_time)} · Detected: {date(a.created_at)} · {a.incident_id}</p>
        <p className="mt-2 text-body">{DELIVERY[a.delivery] ?? a.delivery}{a.historical ? ' · Historical / future-dated evidence' : ''}{a.payload.controlled_test ? ' · Controlled test' : ''}{a.payload.demo ? ' · Demo' : ''}</p>
        {a.last_error && <p className="mt-1 text-label text-sev-high">Delivery: {a.last_error.replaceAll('_', ' ')} · Attempts: {a.attempts}</p>}
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <Button asChild><Link to={`/incidents/${a.incident_id}`}>Review evidence</Link></Button>
          {!a.seen_at && <Button variant="outline" disabled={ack.isPending} onClick={() => ack.mutate(a.id)}>Mark read</Button>}
        </div>
      </article>)}</div>}
    {q.data?.next_before != null && <Button variant="outline" onClick={() => setBefore(q.data!.next_before!)}>Older alerts</Button>}
  </div>;
}
