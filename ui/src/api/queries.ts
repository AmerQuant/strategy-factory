/** Server state with TanStack Query (D-772). Start, resume and stop invalidate the run queries. */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from './client';
import type { RunListFilters, StartRunRequest } from './contract';

export const keys = {
  status: ['status'] as const,
  configs: ['configs'] as const,
  runs: ['runs'] as const,
  runList: (f: RunListFilters) => ['runs', 'list', f] as const,
  run: (id: string) => ['runs', 'one', id] as const,
};

export function useServerStatus() {
  return useQuery({ queryKey: keys.status, queryFn: api.status, refetchInterval: 15_000 });
}

export function useConfigs() {
  return useQuery({ queryKey: keys.configs, queryFn: api.configs, staleTime: 60_000 });
}

export function useRunList(filters: RunListFilters = {}) {
  return useQuery({
    queryKey: keys.runList(filters),
    queryFn: () => api.listRuns(filters),
    refetchInterval: (q) => (q.state.data?.some((r) => r.status === 'running') ? 3_000 : 15_000),
  });
}

export function useRun(id: string) {
  return useQuery({
    queryKey: keys.run(id),
    queryFn: () => api.run(id),
    // A failed or stopped run may be resumed elsewhere (another tab, the CLI): keep looking.
    refetchInterval: (q) => {
      const s = q.state.data?.status;
      return s === 'running' ? 3_000 : s === 'failed' || s === 'stopped' ? 10_000 : false;
    },
  });
}

function useInvalidateRuns() {
  const qc = useQueryClient();
  return () => qc.invalidateQueries({ queryKey: keys.runs });
}

export function useStartRun() {
  const invalidate = useInvalidateRuns();
  return useMutation({
    mutationFn: (req: StartRunRequest) => api.start(req),
    onSuccess: invalidate,
  });
}

export function useResumeRun() {
  const invalidate = useInvalidateRuns();
  return useMutation({ mutationFn: (id: string) => api.resume(id), onSuccess: invalidate });
}

export function useStopRun() {
  const invalidate = useInvalidateRuns();
  return useMutation({ mutationFn: (id: string) => api.stop(id), onSuccess: invalidate });
}
