import { useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { Database, Send } from 'lucide-react';
import { Bone, EmptyState, ErrorState, PageHeader, Panel, Skeleton } from '@/components/common/states';
import { Button } from '@/components/ui/button';
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet';
import { api } from '@/lib/api';
import { bytesLabel, dateTimeIST, int } from '@/lib/format';
import { qk } from '@/lib/queryKeys';
import type { DeliveryStatus, ParquetExport, RetentionReport } from '@/lib/types';

export const STATEMENT = "ANVAYA's tamper-evident retention supports CERT-In's 180-day log retention requirement.";

function SiemForwarderCard({ status }: { status: DeliveryStatus['siem'] }) {
  return (
    <Panel title="SIEM forwarder · file sink (demo)" className="h-full">
      {status.forwarded === 0 ? (
        <EmptyState icon={Send} title="Nothing forwarded yet" body="Each normalized event is written as an RFC 5424 line with a JSON payload." className="py-6" />
      ) : (
        <div className="space-y-2 text-body">
          <p className="text-body-lg">Forwarded {int(status.forwarded)} events</p>
          <p className="text-graphite">Target <span className="font-mono text-mono">{status.target}</span></p>
          <p className="text-graphite">Last payload</p>
          <div className="rounded-control bg-paper-sunk p-3">
            <pre className="line-clamp-3 font-mono text-mono break-all whitespace-pre-wrap">{status.last_payload}</pre>
          </div>
        </div>
      )}
    </Panel>
  );
}

function ParquetExportCard({ lastExport, onExport, pending, error }: { lastExport: ParquetExport | null; onExport: () => void; pending: boolean; error: boolean }) {
  return (
    <Panel title="Data lake export · Parquet" className="h-full">
      <Button onClick={onExport} disabled={pending}>{pending ? 'Exporting…' : 'Export to Parquet'}</Button>
      <div className="mt-4 min-h-[84px]">
        {error ? (
          <ErrorState title="Couldn't write to the data lake folder." body="Check that /data/lake is writable." onRetry={onExport} />
        ) : lastExport ? (
          <div className="space-y-1">
            <p className="text-body-lg">Exported {int(lastExport.rows)} events · verified by reading back {int(lastExport.duckdb_rows)} rows</p>
            <p className="text-body text-graphite tabular">{bytesLabel(lastExport.bytes)} · {lastExport.took_ms} ms</p>
            <p className="truncate font-mono text-mono text-graphite">{lastExport.file}</p>
          </div>
        ) : (
          <EmptyState icon={Database} title="No exports yet" body="Export writes every normalized event to a Parquet file in /data/lake." className="py-2" />
        )}
      </div>
    </Panel>
  );
}

function RetentionReportCard({ onView, onDownload, pending }: { onView: () => void; onDownload: () => void; pending: boolean }) {
  return (
    <Panel title="Retention report" className="h-full">
      <p className="text-body-lg">{STATEMENT}</p>
      <div className="mt-4 flex gap-2">
        <Button variant="outline" onClick={onView} disabled={pending}>View report</Button>
        <Button variant="outline" onClick={onDownload} disabled={pending}>Download JSON</Button>
      </div>
    </Panel>
  );
}

function download(report: RetentionReport) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' }));
  const a = Object.assign(document.createElement('a'), { href: url, download: `anvaya-retention-${report.generated}.json` });
  a.click();
  URL.revokeObjectURL(url);
}

function RetentionReportSheet({ report, open, onOpenChange }: { report: RetentionReport | undefined; open: boolean; onOpenChange: (o: boolean) => void }) {
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="w-[640px] sm:max-w-[640px] bg-surface p-6">
        <SheetHeader className="p-0">
          <SheetTitle className="font-display text-h1 font-semibold">Retention report</SheetTitle>
          <SheetDescription className="text-body-lg text-ink">{report?.statement ?? STATEMENT}</SheetDescription>
        </SheetHeader>
        {report && (
          <div className="mt-4 space-y-4 text-body">
            <p className="text-graphite">Retention target {report.retention_target_days} days · generated {dateTimeIST(report.generated)}</p>
            <table className="w-full border-collapse">
              <thead><tr className="text-left text-label font-medium text-graphite">
                {['Device', 'Oldest', 'Newest', 'Records', 'Sealed'].map((h) => <th key={h} scope="col" className="h-10 pr-3">{h}</th>)}
              </tr></thead>
              <tbody>
                {report.sources.map((s) => (
                  <tr key={s.device} className="h-11 border-t border-rule">
                    <td className="pr-3 font-mono text-mono">{s.device}</td>
                    <td className="pr-3">{dateTimeIST(s.oldest)}</td>
                    <td className="pr-3">{dateTimeIST(s.newest)}</td>
                    <td className="pr-3 tabular">{int(s.records)}</td>
                    <td className="pr-3">{s.sealed ? 'All sealed' : 'Sealing in progress'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p>Ledger: {report.ledger.verdict ? `${report.ledger.verdict} · last verified ${dateTimeIST(report.ledger.last_verified)}` : 'not verified yet'}</p>
            <p className="text-label text-graphite">{report.note}</p>
          </div>
        )}
      </SheetContent>
    </Sheet>
  );
}

export default function Delivery() {
  const status = useQuery({ queryKey: qk.delivery, queryFn: api.delivery.status, refetchInterval: 5000 });
  const report = useQuery({ queryKey: qk.retention, queryFn: api.delivery.retention, enabled: false });
  const [sheet, setSheet] = useState(false);
  const exp = useMutation({ mutationFn: () => api.delivery.exportParquet(), onSuccess: () => status.refetch() });
  const last = exp.data ?? null;
  return (
    <div>
      <PageHeader title="Delivery" subtitle="Outputs for the SIEM, the data lake and auditors" />
      {status.isPending ? (
        <Skeleton><div className="grid grid-cols-3 gap-6">{[0, 1, 2].map((i) => <Bone key={i} className="h-64" />)}</div></Skeleton>
      ) : status.isError ? (
        <ErrorState title="Couldn't load delivery status." body="Check that the api container is running." onRetry={() => status.refetch()} />
      ) : (
        <div className="grid grid-cols-3 gap-6">
          <SiemForwarderCard status={status.data.siem} />
          <ParquetExportCard lastExport={last} onExport={() => exp.mutate()} pending={exp.isPending} error={exp.isError} />
          <RetentionReportCard pending={report.isFetching}
            onView={() => { setSheet(true); void report.refetch(); }}
            onDownload={() => void report.refetch().then((r) => r.data && download(r.data))} />
        </div>
      )}
      <RetentionReportSheet report={report.data} open={sheet} onOpenChange={setSheet} />
    </div>
  );
}
