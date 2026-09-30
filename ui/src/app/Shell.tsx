/**
 * The app shell (UI_spec §0): sidebar with all three phases' navigation (later phases disabled with the
 * phase that brings them), top bar with title, breadcrumb and "New funnel run", the banners of
 * `GET /api/status`, the server status, the theme switch (remembered).
 */
import { ActionIcon, Tooltip, useComputedColorScheme, useMantineColorScheme } from '@mantine/core';
import {
  IconActivity,
  IconBell,
  IconChartBar,
  IconDatabase,
  IconHistory,
  IconLayoutDashboard,
  IconMoon,
  IconPlayerPlay,
  IconPlus,
  IconSearch,
  IconServer,
  IconSettings,
  IconStack2,
  IconSun,
  type Icon,
} from '@tabler/icons-react';
import { Link, Outlet, useRouterState } from '@tanstack/react-router';
import type { ReactNode } from 'react';
import { useServerStatus } from '../api/queries';
import { Banner, PhaseTag } from '../components/ui';
import { v } from '../theme/tokens';

interface NavItem {
  label: string;
  icon: Icon;
  to?: string;
  /** Exact match for the active state. */
  exact?: boolean;
  phase?: string;
  testId: string;
}

interface NavGroup {
  label: string;
  items: NavItem[];
}

export const NAV: NavGroup[] = [
  {
    label: 'Overview',
    items: [
      {
        label: 'Overview',
        icon: IconLayoutDashboard,
        to: '/',
        exact: true,
        testId: 'nav-overview',
      },
    ],
  },
  {
    label: 'Runs',
    items: [
      {
        label: 'New funnel run',
        icon: IconPlayerPlay,
        to: '/runs/new',
        exact: true,
        testId: 'nav-new',
      },
      { label: 'Live monitor', icon: IconActivity, to: '/runs/live', testId: 'nav-live' },
      { label: 'History', icon: IconHistory, to: '/runs', exact: true, testId: 'nav-history' },
    ],
  },
  {
    label: 'Results',
    items: [
      { label: 'Funnel explorer', icon: IconChartBar, phase: 'phase 2', testId: 'nav-funnel' },
      { label: 'Candidates', icon: IconChartBar, phase: 'phase 2', testId: 'nav-candidates' },
      { label: 'Compare runs', icon: IconChartBar, phase: 'phase 2', testId: 'nav-compare' },
      { label: 'Calibration', icon: IconChartBar, phase: 'phase 2', testId: 'nav-calibration' },
    ],
  },
  {
    label: 'Strategies',
    items: [{ label: 'Library', icon: IconStack2, phase: 'phase 2', testId: 'nav-library' }],
  },
  {
    label: 'Data',
    items: [
      { label: 'Universe', icon: IconDatabase, phase: 'phase 2', testId: 'nav-universe' },
      { label: 'Symbol explorer', icon: IconDatabase, phase: 'phase 2', testId: 'nav-symbols' },
      { label: 'Data store', icon: IconDatabase, phase: 'phase 2', testId: 'nav-store' },
      { label: 'Costs', icon: IconDatabase, phase: 'phase 2', testId: 'nav-costs' },
      { label: 'Downloads', icon: IconDatabase, phase: 'T17a-BE', testId: 'nav-downloads' },
    ],
  },
  {
    label: 'Settings',
    items: [
      { label: 'Config profiles', icon: IconSettings, phase: 'phase 3', testId: 'nav-profiles' },
    ],
  },
  {
    label: 'System',
    items: [{ label: 'System', icon: IconServer, phase: 'phase 2', testId: 'nav-system' }],
  },
];

function isActive(item: NavItem, path: string): boolean {
  if (!item.to) return false;
  if (item.to === '/runs/live') return /^\/runs\/(?!new$)[^/]+$/.test(path);
  return item.exact ? path === item.to : path.startsWith(item.to);
}

function NavEntry({ item, path }: { item: NavItem; path: string }) {
  const active = isActive(item, path);
  const style = {
    display: 'flex',
    alignItems: 'center',
    gap: 10,
    height: 36,
    padding: '0 10px',
    borderRadius: 10,
    fontSize: 13,
    fontWeight: active ? 700 : 600,
    textDecoration: 'none',
    color: v(item.to ? (active ? 'text-strong' : 'text-tertiary') : 'text-disabled'),
    background: active ? v('nav-active-bg') : 'transparent',
    cursor: item.to ? 'pointer' : 'not-allowed',
  } as const;
  const content = (
    <>
      <item.icon size={17} stroke={1.8} color={active ? v('accent') : undefined} />
      <span style={{ flex: 1 }}>{item.label}</span>
      {item.phase ? <PhaseTag phase={item.phase} /> : null}
    </>
  );
  if (!item.to) {
    return (
      <div
        style={style}
        aria-disabled="true"
        data-testid={item.testId}
        title={`Comes with ${item.phase}`}
      >
        {content}
      </div>
    );
  }
  return (
    <Link
      to={item.to}
      style={style}
      data-testid={item.testId}
      aria-current={active ? 'page' : undefined}
    >
      {content}
    </Link>
  );
}

function Sidebar({ path }: { path: string }) {
  const status = useServerStatus();
  // The outer column carries the colour down the whole page; the inner one stays in view.
  return (
    <div
      style={{
        width: 248,
        flexShrink: 0,
        background: v('bg-sidebar'),
        borderRight: `1px solid ${v('border-sidebar')}`,
      }}
    >
      <aside
        style={{
          display: 'flex',
          flexDirection: 'column',
          height: '100vh',
          position: 'sticky',
          top: 0,
        }}
      >
        <div style={{ padding: '22px 20px 14px', display: 'flex', alignItems: 'center', gap: 10 }}>
          <div
            style={{
              width: 30,
              height: 30,
              borderRadius: 8,
              background: v('accent'),
              display: 'grid',
              placeItems: 'center',
            }}
          >
            <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden>
              <path
                d="M4 17 L10 10 L14 14 L20 6"
                stroke={v('on-accent')}
                strokeWidth="2.6"
                fill="none"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </div>
          <div>
            <div style={{ fontWeight: 800, fontSize: 14, color: v('text-strong') }}>
              Strategy Factory
            </div>
            <div className="cap" style={{ fontSize: 10 }}>
              Admin
            </div>
          </div>
        </div>
        <nav style={{ flex: 1, overflowY: 'auto', padding: '6px 12px' }} aria-label="Main">
          {NAV.map((g) => (
            <div key={g.label} style={{ marginBottom: 12 }}>
              <div className="cap" style={{ padding: '6px 10px', fontSize: 10 }}>
                {g.label}
              </div>
              {g.items.map((item) => (
                <NavEntry key={item.testId} item={item} path={path} />
              ))}
            </div>
          ))}
        </nav>
        <div
          style={{
            padding: 16,
            borderTop: `1px solid ${v('border-sidebar')}`,
            display: 'grid',
            gap: 10,
          }}
        >
          <div className="sf-inset" style={{ padding: '10px 12px' }}>
            <div className="cap" style={{ fontSize: 10 }}>
              Active profile
            </div>
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                marginTop: 4,
              }}
            >
              <span style={{ fontSize: 13, fontWeight: 700, color: v('text-secondary') }}>
                defaults
              </span>
              <PhaseTag phase="T17c" />
            </div>
          </div>
          <div
            data-testid="server-status"
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              fontSize: 12,
              padding: '0 4px',
            }}
          >
            <span
              style={{
                width: 8,
                height: 8,
                borderRadius: 4,
                background: v(status.isError ? 'danger' : status.data ? 'accent' : 'waiting'),
              }}
            />
            <span
              style={{ color: v(status.isError ? 'danger-fg' : 'accent-fg-2'), fontWeight: 700 }}
            >
              {status.isError ? 'server unreachable' : status.data ? 'server on' : 'connecting'}
            </span>
            <span
              className="mono"
              style={{ color: v('text-faint'), marginLeft: 'auto', fontSize: 11 }}
            >
              {status.data?.server.host ?? '127.0.0.1'}
            </span>
          </div>
          {status.data ? (
            <div
              className="mono"
              style={{ color: v('text-faint'), fontSize: 10, padding: '0 4px' }}
            >
              {status.data.server.version}
            </div>
          ) : null}
        </div>
      </aside>
    </div>
  );
}

function pageMeta(path: string): { title: string; crumbs: string[] } {
  if (path === '/') return { title: 'Overview', crumbs: ['Overview'] };
  if (path === '/runs') return { title: 'Run history', crumbs: ['Runs', 'History'] };
  if (path === '/runs/new') return { title: 'New funnel run', crumbs: ['Runs', 'New funnel run'] };
  if (path.startsWith('/runs/')) return { title: 'Live monitor', crumbs: ['Runs', 'Live monitor'] };
  return { title: 'Strategy Factory', crumbs: [] };
}

function ThemeSwitch() {
  const { setColorScheme } = useMantineColorScheme();
  const scheme = useComputedColorScheme('dark');
  const next = scheme === 'dark' ? 'light' : 'dark';
  return (
    <Tooltip label={`Switch to the ${next} theme`}>
      <ActionIcon
        variant="default"
        size={40}
        radius="md"
        aria-label={`Switch to the ${next} theme`}
        data-testid="theme-switch"
        onClick={() => setColorScheme(next)}
      >
        {scheme === 'dark' ? <IconSun size={18} /> : <IconMoon size={18} />}
      </ActionIcon>
    </Tooltip>
  );
}

function TopBar({ path }: { path: string }) {
  const { title, crumbs } = pageMeta(path);
  return (
    <header
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 12,
        padding: '22px 32px 0',
      }}
    >
      <div style={{ flex: 1, minWidth: 0 }}>
        <div className="cap" data-testid="breadcrumb">
          {crumbs.join('  /  ')}
        </div>
        <h1 className="page-title" data-testid="page-title">
          {title}
        </h1>
      </div>
      <Tooltip label="Global search comes with phase 2">
        <div
          aria-disabled="true"
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            height: 40,
            width: 240,
            padding: '0 12px',
            borderRadius: 10,
            border: `1px solid ${v('border-input')}`,
            background: v('surface-3'),
            color: v('text-disabled'),
            fontSize: 13,
          }}
        >
          <IconSearch size={16} /> Search runs, symbols…
        </div>
      </Tooltip>
      <Tooltip label="Notifications come with phase 2">
        <ActionIcon
          variant="default"
          size={40}
          radius="md"
          disabled
          aria-label="Notifications (phase 2)"
        >
          <IconBell size={18} />
        </ActionIcon>
      </Tooltip>
      <ThemeSwitch />
      <Link to="/runs/new" className="sf-primary" data-testid="topbar-new-run" style={primaryLink}>
        <IconPlus size={18} stroke={2.6} /> New funnel run
      </Link>
    </header>
  );
}

export const primaryLink = {
  display: 'inline-flex',
  alignItems: 'center',
  gap: 8,
  textDecoration: 'none',
  fontSize: 14,
} as const;

function StatusBanners() {
  const status = useServerStatus();
  if (!status.data || status.data.banners.length === 0) return null;
  return (
    <div style={{ display: 'grid', gap: 8, padding: '16px 32px 0' }} data-testid="status-banners">
      {status.data.banners.map((b) => (
        <Banner key={b.id} level={b.level} title={b.title} testId={`banner-${b.id}`}>
          {b.text}
        </Banner>
      ))}
    </div>
  );
}

export function Page({ children }: { children: ReactNode }) {
  return <div style={{ padding: '20px 32px 40px', display: 'grid', gap: 16 }}>{children}</div>;
}

export function Shell() {
  const path = useRouterState({ select: (s) => s.location.pathname });
  return (
    <div style={{ display: 'flex', minHeight: '100vh', background: v('bg') }}>
      <Sidebar path={path} />
      <main style={{ flex: 1, minWidth: 0 }}>
        <TopBar path={path} />
        <StatusBanners />
        <Outlet />
      </main>
    </div>
  );
}
