/**
 * Run history (UI_spec §2.3): every funnel run; filters (source, status, date — server side), search
 * (client side), sortable columns, column chooser, CSV export. The URL holds all of it (D-781).
 * Row actions open report, reproduce and compare are phase 2 (D-796).
 */
import { ActionIcon, Button, Checkbox, Menu, Select, TextInput, Tooltip } from '@mantine/core';
import {
  IconArrowDown,
  IconArrowUp,
  IconColumns3,
  IconDots,
  IconDownload,
  IconSearch,
} from '@tabler/icons-react';
import { getRouteApi, Link, useNavigate } from '@tanstack/react-router';
import type { ReactNode } from 'react';
import type { RunListItem } from '../api/contract';
import { useRunList } from '../api/queries';
import { Page } from '../app/Shell';
import { HISTORY_COLUMNS, type HistoryColumn, type HistorySearch } from '../app/search';
import { Card, SourceBadge, StatusBadge } from '../components/ui';
import {
  formatDateTime,
  formatDuration,
  secondsBetween,
  shortId,
  stageLabel,
  toCsv,
} from '../lib/format';
import { v } from '../theme/tokens';

const route = getRouteApi('/runs');

const LABELS: Record<HistoryColumn, string> = {
  id: 'Id',
  name: 'Name',
  source: 'Source',
  profile: 'Profile',
  config: 'Config',
  code: 'Code',
  started: 'Started',
  finished: 'Finished',
  wall: 'Wall time',
  counts: 'Passes real / control',
  status: 'Status',
};

function wall(r: RunListItem): number | null {
  return r.status === 'running' ? null : secondsBetween(r.started_at, r.finished_at);
}

function sortValue(r: RunListItem, col: HistoryColumn): string | number {
  switch (col) {
    case 'id':
      return r.funnel_run_id;
    case 'name':
      return r.name.toLowerCase();
    case 'source':
      return r.source;
    case 'profile':
      return r.profile_hash ?? '';
    case 'config':
      return r.config_id;
    case 'code':
      return r.code_version.git_sha;
    case 'started':
      return r.started_at ?? '';
    case 'finished':
      return r.finished_at ?? '';
    case 'wall':
      return wall(r) ?? -1;
    case 'counts':
      return r.stage_counts[r.stage_counts.length - 1]?.real ?? -1;
    case 'status':
      return r.status;
  }
}

function countsText(r: RunListItem): string {
  return r.stage_counts
    .map(
      (c) =>
        `${stageLabel(c.stage_id).split(' ')[0]} ${c.real ?? '—'}/${r.control ? (c.control ?? '—') : 'off'}`,
    )
    .join('  ');
}

function Counts({ r }: { r: RunListItem }) {
  return (
    <span style={{ display: 'inline-flex', gap: 10 }} className="num">
      {r.stage_counts.map((c) => (
        <span
          key={c.stage_id}
          title={`${c.stage_id}: real ${c.real ?? '—'}, control ${r.control ? (c.control ?? '—') : 'off'}`}
        >
          <span style={{ color: v('text-faint') }}>{stageLabel(c.stage_id).split(' ')[0]} </span>
          <span style={{ color: v('blue-fg') }}>{c.real ?? '—'}</span>
          <span style={{ color: v('text-faint') }}>/</span>
          <span style={{ color: v('amber-fg') }}>{r.control ? (c.control ?? '—') : 'off'}</span>
        </span>
      ))}
    </span>
  );
}

function cell(r: RunListItem, col: HistoryColumn): ReactNode {
  switch (col) {
    case 'id':
      return (
        <span className="mono" title={r.funnel_run_id}>
          {shortId(r.funnel_run_id)}
        </span>
      );
    case 'name':
      return (
        <Link
          to="/runs/$runId"
          params={{ runId: r.funnel_run_id }}
          className="sf-link"
          style={{ fontWeight: 700 }}
        >
          {r.name}
        </Link>
      );
    case 'source':
      return <SourceBadge source={r.source} seed={r.seed} />;
    case 'profile':
      return r.profile_hash === null ? (
        <span style={{ color: v('text-faint') }}>defaults</span>
      ) : (
        <span className="mono">{r.profile_hash.slice(0, 12)}</span>
      );
    case 'config':
      return (
        <span className="mono" title={r.config_hash}>
          {r.config_id} · {r.config_hash.slice(0, 8)}
        </span>
      );
    case 'code':
      return (
        <span className="mono">
          {r.code_version.git_sha.slice(0, 7)}
          {r.code_version.dirty ? (
            <span
              className="sf-badge"
              style={{
                marginLeft: 6,
                padding: '2px 6px',
                fontSize: 9,
                background: v('amber-bg'),
                color: v('amber-fg'),
              }}
            >
              dirty
            </span>
          ) : null}
        </span>
      );
    case 'started':
      return <span className="num">{formatDateTime(r.started_at)}</span>;
    case 'finished':
      return <span className="num">{formatDateTime(r.finished_at)}</span>;
    case 'wall':
      return <span className="num">{formatDuration(wall(r))}</span>;
    case 'counts':
      return <Counts r={r} />;
    case 'status':
      return <StatusBadge status={r.status} />;
  }
}

function csvValue(r: RunListItem, col: HistoryColumn): string | number | null {
  switch (col) {
    case 'id':
      return r.funnel_run_id;
    case 'name':
      return r.name;
    case 'source':
      return r.seed === null ? r.source : `${r.source} seed ${r.seed}`;
    case 'profile':
      return r.profile_hash ?? 'defaults';
    case 'config':
      return `${r.config_id} ${r.config_hash}`;
    case 'code':
      return `${r.code_version.git_sha}${r.code_version.dirty ? ' dirty' : ''}`;
    case 'started':
      return r.started_at;
    case 'finished':
      return r.finished_at;
    case 'wall':
      return wall(r);
    case 'counts':
      return countsText(r);
    case 'status':
      return r.status;
  }
}

export function filterAndSort(rows: RunListItem[], s: HistorySearch): RunListItem[] {
  const q = s.q?.trim().toLowerCase();
  const out = q
    ? rows.filter((r) =>
        [r.name, r.funnel_run_id, r.config_id, r.config_hash, r.code_version.git_sha].some((x) =>
          x.toLowerCase().includes(q),
        ),
      )
    : [...rows];
  const col = s.sort ?? 'started';
  const sign = (s.dir ?? (s.sort ? 'asc' : 'desc')) === 'asc' ? 1 : -1;
  out.sort((a, b) => {
    const x = sortValue(a, col);
    const y = sortValue(b, col);
    return (x < y ? -1 : x > y ? 1 : 0) * sign;
  });
  return out;
}

function download(name: string, text: string) {
  const url = URL.createObjectURL(new Blob([text], { type: 'text/csv;charset=utf-8' }));
  const a = document.createElement('a');
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}

export function HistoryPage() {
  const search = route.useSearch();
  const navigate = useNavigate({ from: '/runs' });
  const runs = useRunList({
    source: search.source,
    status: search.status,
    started_from: search.from,
    started_to: search.to,
  });
  const hidden = new Set((search.hide ?? '').split(',').filter(Boolean));
  const cols = HISTORY_COLUMNS.filter((c) => !hidden.has(c));
  const rows = filterAndSort(runs.data ?? [], search);
  const set = (patch: Partial<HistorySearch>) =>
    navigate({ search: (prev: HistorySearch) => ({ ...prev, ...patch }), replace: true });

  const toggleSort = (c: HistoryColumn) => {
    if (search.sort !== c) set({ sort: c, dir: 'asc' });
    else set({ dir: search.dir === 'asc' ? 'desc' : 'asc' });
  };
  const toggleCol = (c: HistoryColumn) => {
    const next = new Set(hidden);
    if (next.has(c)) next.delete(c);
    else next.add(c);
    set({ hide: next.size ? [...next].join(',') : undefined });
  };
  const exportCsv = () =>
    download(
      'funnel-runs.csv',
      toCsv(
        cols.map((c) => LABELS[c]),
        rows.map((r) => cols.map((c) => csvValue(r, c))),
      ),
    );

  return (
    <Page>
      <Card testId="history" padding={0}>
        <div
          style={{
            display: 'flex',
            gap: 10,
            alignItems: 'flex-end',
            padding: 16,
            flexWrap: 'wrap',
          }}
        >
          <TextInput
            label="Search"
            placeholder="name, id, config, commit"
            leftSection={<IconSearch size={15} />}
            value={search.q ?? ''}
            onChange={(e) => set({ q: e.currentTarget.value || undefined })}
            w={240}
            data-testid="history-search"
          />
          <Select
            label="Source"
            placeholder="any"
            clearable
            data={['real', 'null', 'planted']}
            value={search.source ?? null}
            onChange={(x) => set({ source: (x ?? undefined) as HistorySearch['source'] })}
            w={130}
            data-testid="filter-source"
          />
          <Select
            label="Status"
            placeholder="any"
            clearable
            data={['queued', 'running', 'finished', 'failed', 'stopped']}
            value={search.status ?? null}
            onChange={(x) => set({ status: (x ?? undefined) as HistorySearch['status'] })}
            w={140}
            data-testid="filter-status"
          />
          <TextInput
            label="Started from"
            type="date"
            value={search.from ?? ''}
            onChange={(e) => set({ from: e.currentTarget.value || undefined })}
            w={160}
            data-testid="filter-from"
          />
          <TextInput
            label="to"
            type="date"
            value={search.to ?? ''}
            onChange={(e) => set({ to: e.currentTarget.value || undefined })}
            w={160}
            data-testid="filter-to"
          />
          <div style={{ flex: 1 }} />
          <Menu closeOnItemClick={false} position="bottom-end">
            <Menu.Target>
              <Button
                variant="default"
                leftSection={<IconColumns3 size={16} />}
                data-testid="column-chooser"
              >
                Columns
              </Button>
            </Menu.Target>
            <Menu.Dropdown>
              {HISTORY_COLUMNS.map((c) => (
                <Menu.Item key={c} onClick={() => toggleCol(c)}>
                  <Checkbox checked={!hidden.has(c)} readOnly label={LABELS[c]} size="xs" />
                </Menu.Item>
              ))}
            </Menu.Dropdown>
          </Menu>
          <Button
            variant="default"
            leftSection={<IconDownload size={16} />}
            onClick={exportCsv}
            data-testid="export-csv"
          >
            CSV
          </Button>
        </div>
        <div style={{ overflowX: 'auto', padding: '0 8px 8px' }}>
          <table className="sf-table" data-testid="history-table">
            <thead>
              <tr>
                {cols.map((c) => (
                  <th
                    key={c}
                    onClick={() => toggleSort(c)}
                    style={{ cursor: 'pointer' }}
                    aria-sort={
                      search.sort === c
                        ? search.dir === 'desc'
                          ? 'descending'
                          : 'ascending'
                        : undefined
                    }
                  >
                    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                      {LABELS[c]}
                      {search.sort === c ? (
                        search.dir === 'desc' ? (
                          <IconArrowDown size={12} />
                        ) : (
                          <IconArrowUp size={12} />
                        )
                      ) : null}
                    </span>
                  </th>
                ))}
                <th />
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.funnel_run_id} data-testid="history-row">
                  {cols.map((c) => (
                    <td key={c}>{cell(r, c)}</td>
                  ))}
                  <td>
                    <Menu position="bottom-end">
                      <Menu.Target>
                        <ActionIcon variant="subtle" aria-label="Row actions">
                          <IconDots size={16} />
                        </ActionIcon>
                      </Menu.Target>
                      <Menu.Dropdown>
                        <Menu.Item
                          onClick={() =>
                            navigate({ to: '/runs/$runId', params: { runId: r.funnel_run_id } })
                          }
                        >
                          Open
                        </Menu.Item>
                        <Tooltip label="phase 2" position="left">
                          <div>
                            <Menu.Item disabled>Open report</Menu.Item>
                            <Menu.Item disabled>Reproduce</Menu.Item>
                            <Menu.Item disabled>Compare with…</Menu.Item>
                          </div>
                        </Tooltip>
                      </Menu.Dropdown>
                    </Menu>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {runs.data && rows.length === 0 ? (
            <div
              style={{ padding: 24, textAlign: 'center', color: v('text-faint') }}
              data-testid="history-empty"
            >
              No funnel run matches.
            </div>
          ) : null}
        </div>
        <div className="cap" style={{ padding: '10px 20px 16px' }} data-testid="history-count">
          {rows.length} of {runs.data?.length ?? 0} runs
        </div>
      </Card>
    </Page>
  );
}
