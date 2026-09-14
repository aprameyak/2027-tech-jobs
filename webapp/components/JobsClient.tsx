'use client';

import { useState, useMemo, useSyncExternalStore, useCallback, useId, useRef, useEffect } from 'react';
import type { ListingsData, ProcessedRow } from '@/lib/listings';

type TabKey = 'summer' | 'offcycle' | 'newgrad';

const TAB_LABELS: Record<TabKey, string> = {
  summer: 'Summer 2027',
  offcycle: 'Off-Cycle',
  newgrad: 'New Grad',
};

const ACTIVE_TAB_KEY = 'activeTab';
const tabListeners = new Set<() => void>();

function subscribeActiveTab(listener: () => void) {
  tabListeners.add(listener);
  return () => {
    tabListeners.delete(listener);
  };
}

function getActiveTabSnapshot(): TabKey {
  try {
    const saved = localStorage.getItem(ACTIVE_TAB_KEY);
    if (saved === 'summer' || saved === 'offcycle' || saved === 'newgrad') {
      return saved;
    }
    if (saved !== null) {
      localStorage.removeItem(ACTIVE_TAB_KEY);
    }
  } catch (e) {
    console.warn('Could not read tab state from localStorage', e);
  }
  return 'summer';
}

function getActiveTabServerSnapshot(): TabKey {
  return 'summer';
}

function ApplyButton({
  url,
  role,
  company,
}: {
  url: string;
  role: string;
  company: string;
}) {
  if (!url) {
    return (
      <span title="Position closed">
        <span aria-hidden="true">🔒</span>
        <span className="sr-only">Position closed</span>
      </span>
    );
  }
  return (
    <a
      href={url}
      target="_blank"
      rel="noopener noreferrer"
      aria-label={`Apply for ${role} at ${company} (opens in a new tab)`}
      className="inline-flex items-center gap-1 rounded bg-blue-600 px-3 py-1 text-xs font-medium text-white hover:bg-blue-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2 transition-colors whitespace-nowrap"
    >
      Apply
    </a>
  );
}

function LocationCell({ locations }: { locations: string[] }) {
  const [open, setOpen] = useState(false);
  const panelId = useId();
  const wrapRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function onPointerDown(event: MouseEvent) {
      if (wrapRef.current && !wrapRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') setOpen(false);
    }
    document.addEventListener('mousedown', onPointerDown);
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('mousedown', onPointerDown);
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [open]);

  if (locations.length <= 1) {
    return <span>{locations[0] ?? ''}</span>;
  }
  return (
    <div className="relative" ref={wrapRef}>
      <button
        type="button"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((v) => !v)}
        className="text-blue-600 underline decoration-dotted text-left hover:text-blue-800 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 rounded"
      >
        {locations.length} locations
      </button>
      {open && (
        <div
          id={panelId}
          role="region"
          aria-label="All locations"
          className="absolute z-10 mt-1 w-56 rounded border border-gray-200 bg-white shadow-lg text-sm"
        >
          <ul className="divide-y divide-gray-100">
            {locations.map((loc) => (
              <li key={loc} className="px-3 py-1.5">
                {loc}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function JobTable({
  rows,
  showSeason,
  showGradDate,
  search,
  labelledBy,
}: {
  rows: ProcessedRow[];
  showSeason: boolean;
  showGradDate: boolean;
  search: string;
  labelledBy: string;
}) {
  const displayRows = useMemo(() => {
    if (!search) return rows;

    const resolved: (ProcessedRow & { resolvedCompany: string })[] = [];
    let lastCompany = '';
    for (const row of rows) {
      const resolvedCompany = row.isGrouped ? lastCompany : row.companyDisplay;
      if (!row.isGrouped) lastCompany = row.companyDisplay;
      resolved.push({ ...row, resolvedCompany });
    }

    const q = search.toLowerCase();
    return resolved.filter(
      (row) =>
        row.resolvedCompany.toLowerCase().includes(q) ||
        row.role.toLowerCase().includes(q) ||
        row.location.toLowerCase().includes(q) ||
        row.gradDate.toLowerCase().includes(q)
    );
  }, [rows, search]);

  if (displayRows.length === 0) {
    return (
      <div className="py-12 text-center text-gray-500" role="status">
        No listings match your search.
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-sm" aria-labelledby={labelledBy}>
        <thead>
          <tr className="border-b border-gray-200 bg-gray-50 text-left text-xs font-semibold uppercase tracking-wide text-gray-500">
            <th scope="col" className="px-4 py-3 w-40">Company</th>
            <th scope="col" className="px-4 py-3">Role</th>
            <th scope="col" className="px-4 py-3 w-40">Location</th>
            {showSeason && (
              <th scope="col" className="px-4 py-3 w-36">Season</th>
            )}
            <th scope="col" className="px-4 py-3 w-28">Education</th>
            {showGradDate && (
              <th scope="col" className="px-4 py-3 w-28">Grad Date</th>
            )}
            <th scope="col" className="px-4 py-3 w-20">Apply</th>
            <th scope="col" className="px-4 py-3 w-20">Added</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {displayRows.map((row, i) => {
            const resolvedCompany =
              'resolvedCompany' in row
                ? (row as ProcessedRow & { resolvedCompany: string }).resolvedCompany
                : row.companyDisplay;
            const displayCompany = search ? resolvedCompany : row.companyDisplay;
            const isContinuation = !search && row.isGrouped;
            const companyForLabel = (isContinuation ? resolvedCompany : displayCompany).replace(
              /[🛂🇺🇸]/gu,
              ''
            ).trim();

            return (
              <tr key={`${row.role}-${row.url}-${i}`} className="hover:bg-blue-50 transition-colors">
                <td className="px-4 py-2.5 align-top font-medium text-gray-900">
                  {isContinuation ? (
                    <span className="text-gray-400 select-none" title={`Also at ${companyForLabel}`}>
                      <span aria-hidden="true">↳</span>
                      <span className="sr-only">Also at {companyForLabel}</span>
                    </span>
                  ) : (
                    displayCompany
                  )}
                </td>
                <td className="px-4 py-2.5 align-top text-gray-700">{row.role}</td>
                <td className="px-4 py-2.5 align-top text-gray-600">
                  <LocationCell locations={row.locations} />
                </td>
                {showSeason && (
                  <td className="px-4 py-2.5 align-top text-gray-600 whitespace-nowrap">
                    {row.season}
                  </td>
                )}
                <td className="px-4 py-2.5 align-top text-gray-600">{row.education}</td>
                {showGradDate && (
                  <td className="px-4 py-2.5 align-top text-gray-600 whitespace-nowrap">
                    {row.gradDate || '—'}
                  </td>
                )}
                <td className="px-4 py-2.5 align-top">
                  <ApplyButton url={row.url} role={row.role} company={companyForLabel || 'company'} />
                </td>
                <td className="px-4 py-2.5 align-top text-gray-500 whitespace-nowrap">
                  {row.dateFormatted}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export default function JobsClient({ data }: { data: ListingsData }) {
  const activeTab = useSyncExternalStore(
    subscribeActiveTab,
    getActiveTabSnapshot,
    getActiveTabServerSnapshot
  );
  const [search, setSearch] = useState('');
  const searchId = useId();
  const tabLabelId = useId();

  const setActiveTab = useCallback((tab: TabKey) => {
    try {
      localStorage.setItem(ACTIVE_TAB_KEY, tab);
    } catch (e) {
      console.warn('Could not save tab state to localStorage', e);
    }
    tabListeners.forEach((listener) => listener());
  }, []);

  const tabs: TabKey[] = ['summer', 'offcycle', 'newgrad'];

  return (
    <div className="min-h-screen bg-gray-50">
      <a href="#job-listings" className="skip-link">
        Skip to job listings
      </a>
      <header className="border-b border-gray-200 bg-white">
        <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 flex items-start justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-gray-900">
              2027 Tech Jobs
            </h1>
            <p className="mt-1 text-sm text-gray-500">
              {data.counts.summer} summer internships · {data.counts.offcycle} off-cycle ·{' '}
              {data.counts.newgrad} new grad roles · updated hourly
            </p>
          </div>
          <a
            href="https://github.com/aprameyak/2027-tech-jobs"
            target="_blank"
            rel="noopener noreferrer"
            aria-label="View repository on GitHub (opens in a new tab)"
            className="text-gray-400 hover:text-gray-700 transition-colors mt-1 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 rounded"
          >
            <svg height="20" width="20" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
              <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z" />
            </svg>
          </a>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6">
        <div className="mb-4 flex items-end gap-2">
          <div className="w-full max-w-md">
            <label htmlFor={searchId} className="mb-1 block text-xs font-medium text-gray-600">
              Search listings
            </label>
            <input
              id={searchId}
              type="search"
              placeholder="Company, role, or location..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm shadow-sm placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            />
          </div>
          <details className="relative">
            <summary
              className="flex h-10 w-10 list-none cursor-pointer items-center justify-center rounded-full border border-gray-300 text-xs text-gray-500 hover:border-gray-400 hover:text-gray-700 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 [&::-webkit-details-marker]:hidden"
              aria-label="Open legend"
            >
              ?
            </summary>
            <div className="absolute right-0 top-12 z-20 w-72 rounded-lg border border-gray-200 bg-white p-3 shadow-lg text-xs text-gray-600">
              <p className="mb-2 font-semibold text-gray-800">Legend</p>
              <ul className="space-y-1.5">
                <li><span className="font-medium">🛂</span> — visa sponsorship not offered</li>
                <li><span className="font-medium">🇺🇸</span> — US citizenship required</li>
                <li><span className="font-medium">🔒</span> — position closed (original date and details preserved)</li>
                <li><span className="font-medium">↳</span> — additional role at same company</li>
                <li><span className="font-medium">Undergrad / Masters / PhD</span> — education level targeted by the posting</li>
                <li><span className="font-medium">Unknown</span> — sponsorship or citizenship status not stated</li>
              </ul>
            </div>
          </details>
        </div>

        <div
          id="job-listings"
          className="mb-1 flex gap-1 border-b border-gray-200"
          role="tablist"
          aria-label="Job category"
        >
          {tabs.map((tab) => {
            const selected = activeTab === tab;
            return (
              <button
                key={tab}
                id={`${tabLabelId}-${tab}`}
                type="button"
                role="tab"
                aria-selected={selected}
                aria-controls={`${tabLabelId}-panel`}
                tabIndex={selected ? 0 : -1}
                onClick={() => setActiveTab(tab)}
                className={`px-4 py-2.5 text-sm font-medium transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-inset ${
                  selected
                    ? 'border-b-2 border-blue-600 text-blue-600'
                    : 'text-gray-500 hover:text-gray-700'
                }`}
              >
                {TAB_LABELS[tab]}{' '}
                <span className="ml-1 rounded-full bg-gray-100 px-1.5 py-0.5 text-xs text-gray-600">
                  {data.counts[tab]}
                </span>
              </button>
            );
          })}
        </div>

        <div
          id={`${tabLabelId}-panel`}
          role="tabpanel"
          aria-labelledby={`${tabLabelId}-${activeTab}`}
          className="rounded-b-lg rounded-tr-lg border border-t-0 border-gray-200 bg-white shadow-sm"
        >
          <JobTable
            rows={data[activeTab]}
            showSeason={activeTab === 'offcycle'}
            showGradDate={activeTab === 'newgrad'}
            search={search}
            labelledBy={`${tabLabelId}-${activeTab}`}
          />
        </div>

        <p className="mt-4 text-center text-xs text-gray-400">
          If this helped you,{' '}
          <a
            href="https://github.com/aprameyak/2027-tech-jobs"
            target="_blank"
            rel="noopener noreferrer"
            className="underline hover:text-gray-600 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 rounded"
          >
            star the repo
          </a>
          {' '}— it helps others find it · 🔒 = position closed
        </p>
      </main>
    </div>
  );
}
