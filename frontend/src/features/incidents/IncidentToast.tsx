import { AnimatePresence, motion, useReducedMotion } from 'framer-motion';
import { Flag } from 'lucide-react';
import { useNavigate } from 'react-router';
import { Button } from '@/components/ui/button';
import { useIncidentStore } from '@/state';

const LABEL = { recon: 'Recon', credential: 'Credential attack', access: 'Access' } as const;

/** Shown once per incident when risk ≥ 90; stays until dismissed or opened (UI_UX_BRIEF.md §5.4). */
export function IncidentToast() {
  const navigate = useNavigate();
  const id = useIncidentStore((s) => s.toastQueue[0]);
  const incident = useIncidentStore((s) => (id ? s.byId[id] : undefined));
  const markToasted = useIncidentStore((s) => s.markToasted);
  const reduced = useReducedMotion();
  return (
    <AnimatePresence>
      {incident && (
        <motion.div key={incident.incident_id} role="status"
          initial={reduced ? { opacity: 0 } : { opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, transition: { duration: reduced ? 0.08 : 0.16, ease: [0.3, 0, 1, 1] } }}
          transition={{ duration: reduced ? 0.08 : 0.32, ease: [0.05, 0.7, 0.1, 1] }}
          className="fixed right-6 bottom-6 z-50 w-[460px] rounded-panel border border-rule border-l-4 border-l-sev-high bg-surface p-4 shadow-e2">
          <div className="flex items-start justify-between gap-4">
            <p className="flex items-center gap-2 text-body-lg font-semibold text-ink">
              <Flag className="size-5 text-sev-high" aria-hidden /> High-risk incident
            </p>
            <span className="text-body-lg font-semibold text-sev-high tabular">Risk {incident.risk}</span>
          </div>
          <p className="mt-1 font-mono text-mono-lg text-ink">
            {incident.attacker_ip} → {incident.target_ip ?? '—'} · {incident.devices.length} sources
          </p>
          <p className="mt-1 text-body-lg text-graphite">{incident.stages.map((s) => LABEL[s]).join(' → ')}</p>
          <div className="mt-3 flex justify-end gap-2">
            <Button variant="ghost" onClick={() => markToasted(incident.incident_id)}>Dismiss</Button>
            <Button onClick={() => { markToasted(incident.incident_id); navigate(`/incidents/${incident.incident_id}`); }}>
              Open incident
            </Button>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
