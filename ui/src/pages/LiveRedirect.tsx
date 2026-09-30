/** "Live monitor" in the navigation: the running run, else the most recent one. */
import { Navigate } from '@tanstack/react-router';
import { Page } from '../app/Shell';
import { useRunList } from '../api/queries';
import { Card } from '../components/ui';
import { v } from '../theme/tokens';

export function LiveRedirect() {
  const runs = useRunList();
  if (!runs.data) return null;
  const target =
    runs.data.find((r) => r.status === 'running') ??
    [...runs.data].sort((a, b) => (b.started_at ?? '').localeCompare(a.started_at ?? ''))[0];
  if (target)
    return <Navigate to="/runs/$runId" params={{ runId: target.funnel_run_id }} replace />;
  return (
    <Page>
      <Card title="No funnel runs yet">
        <span style={{ color: v('text-muted') }}>Start one with “New funnel run”.</span>
      </Card>
    </Page>
  );
}
