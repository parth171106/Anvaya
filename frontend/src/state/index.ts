import { useDemoStore } from './demo';
import { useFeedStore } from './feed';
import {
  useIncidentStore, useIntegrityStore, useLineageStore, useReplayStore, useSourcesStore, useStatsStore, useStreamStore,
} from './slices';

export { useDemoStore, useFeedStore, useIncidentStore, useIntegrityStore, useLineageStore, useReplayStore,
  useSourcesStore, useStatsStore, useStreamStore };

/** Called on SSE demo.state {reset: true}: every slice back to its initial state. */
export function resetAllStores() {
  useFeedStore.getState().reset();
  useStatsStore.getState().reset();
  useIncidentStore.getState().reset();
  useSourcesStore.getState().reset();
  useIntegrityStore.getState().reset();
  useReplayStore.getState().reset();
  useLineageStore.getState().clear();
  useStreamStore.getState().reset();
  useDemoStore.getState().reset();
}
