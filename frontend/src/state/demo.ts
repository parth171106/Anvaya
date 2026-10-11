import { create } from 'zustand';
import { toast } from 'sonner';
import { api, ApiError } from '@/lib/api';
import type { DemoPhase, DemoState } from '@/lib/types';
import { useIntegrityStore } from './slices';

const SPEEDS = [10, 20, 40] as const;
type Speed = (typeof SPEEDS)[number];

interface DemoStore {
  demoMode: boolean; phase: DemoPhase; speed: Speed; silenced: string[]; tampered: boolean; resealed: boolean;
  unknownInjected: boolean; sendErrors: number; panelOpen: boolean; resetArmedUntil: number; startPending: boolean;
  hydrate: (s: DemoState) => void;
  togglePanel: () => void;
  startScenario: () => Promise<boolean>;
  injectUnknown: () => Promise<void>;
  toggleSilence: (device: string) => Promise<void>;
  tamper: () => Promise<void>;
  reseal: () => Promise<void>;
  cycleSpeed: () => Promise<void>;
  armOrReset: () => Promise<void>;
  reset: () => void;
}

function failToast(e: unknown, fallback: string) {
  toast(e instanceof ApiError && e.status === 409 ? e.message : fallback);
}

export const useDemoStore = create<DemoStore>((set, get) => ({
  demoMode: false, phase: 'idle', speed: 20, silenced: [], tampered: false, resealed: false, unknownInjected: false,
  sendErrors: 0, panelOpen: false, resetArmedUntil: 0, startPending: false,

  hydrate: (s) => set({
    demoMode: s.demo_mode ?? get().demoMode, phase: s.phase ?? get().phase, speed: (s.speed as Speed) ?? get().speed,
    silenced: s.silenced ?? get().silenced, tampered: s.tampered ?? get().tampered, resealed: s.resealed ?? get().resealed,
    unknownInjected: s.unknown_injected ?? get().unknownInjected, sendErrors: s.send_errors ?? get().sendErrors,
  }),
  togglePanel: () => set((s) => ({ panelOpen: !s.panelOpen })),

  startScenario: async () => {
    if (get().phase !== 'idle' || get().startPending) return false;
    set({ startPending: true });
    try {
      const r = await api.demo.start(get().speed);
      set({ phase: 'scripted', speed: r.speed as Speed });
      return true;
    } catch (e) {
      failToast(e, "Couldn't start the simulation. Check that the api container is running.");
      return false;
    } finally {
      set({ startPending: false });
    }
  },
  injectUnknown: async () => {
    try {
      await api.demo.injectUnknown();
      set({ unknownInjected: true });
      toast('20 records from an unknown source received');
    } catch (e) {
      failToast(e, "Couldn't inject the unknown source.");
    }
  },
  toggleSilence: async (device) => {
    const silent = !get().silenced.includes(device);
    try {
      await api.demo.silence(device, silent); // no toast on purpose: the silence alert itself is the moment
      set((s) => ({ silenced: silent ? [...s.silenced, device] : s.silenced.filter((d) => d !== device) }));
    } catch (e) {
      failToast(e, "Couldn't change the device state.");
    }
  },
  tamper: async () => {
    try {
      const t = await api.demo.tamper();
      useIntegrityStore.getState().setTamper(t);
      set({ tampered: true });
      toast(`Raw record ${t.raw_id} altered on disk (demo)`);
    } catch (e) {
      failToast(e, 'Wait for the firewall allow event to be sealed, then try again.');
    }
  },
  reseal: async () => {
    try {
      const r = await api.demo.reseal();
      set({ resealed: true });
      toast(`Ledger re-signed with the primary key from batch ${r.resealed_batches[0]} (demo insider)`);
    } catch (e) {
      failToast(e, 'Simulate tamper first.');
    }
  },
  cycleSpeed: async () => {
    const next = SPEEDS[(SPEEDS.indexOf(get().speed) + 1) % SPEEDS.length];
    try {
      await api.demo.speed(next);
      set({ speed: next });
    } catch (e) {
      failToast(e, "Couldn't change the speed.");
    }
  },
  armOrReset: async () => {
    if (Date.now() > get().resetArmedUntil) {
      set({ resetArmedUntil: Date.now() + 2000, panelOpen: true });
      return;
    }
    set({ resetArmedUntil: 0 });
    try {
      await api.demo.reset(); // the stream's demo.state {reset:true} clears the stores and navigates
    } catch {
      toast('Reset failed. Run: docker compose restart api');
    }
  },
  reset: () => set({ phase: 'idle', silenced: [], tampered: false, resealed: false, unknownInjected: false,
    sendErrors: 0, resetArmedUntil: 0, startPending: false }),
}));
