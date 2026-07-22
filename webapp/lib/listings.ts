import fs from 'fs';
import path from 'path';

export interface Listing {
  company: string;
  role: string;
  location: string;
  type: 'summer' | 'offcycle' | 'newgrad';
  season: string;
  education: string;
  url: string;
  sponsorship: string;
  citizenship: string;
  date_added: string;
  grad_date?: string;
}

export interface ProcessedRow {
  companyDisplay: string;
  role: string;
  location: string;
  locations: string[];
  type: 'summer' | 'offcycle' | 'newgrad';
  season: string;
  education: string;
  url: string;
  dateFormatted: string;
  gradDate: string;
  isGrouped: boolean;
}

export interface ListingsData {
  summer: ProcessedRow[];
  offcycle: ProcessedRow[];
  newgrad: ProcessedRow[];
  counts: { summer: number; offcycle: number; newgrad: number };
}

function companySortKey(name: string): string {
  return name.replace(/[\u{1F000}-\u{1FFFF}\u2600-\u26FF\u2700-\u27BF]/gu, '').trim().toLowerCase();
}

function formatCompany(entry: Listing): string {
  let name = entry.company.trim();
  const sponsorship = (entry.sponsorship || '').toLowerCase();
  const citizenship = (entry.citizenship || '').toLowerCase();
  if (sponsorship.includes('not') || sponsorship.includes('no —')) {
    name += ' 🛂';
  }
  if (citizenship.includes('yes —')) {
    name += ' 🇺🇸';
  }
  return name;
}

function formatDate(dateAdded: string): string {
  try {
    const [year, month, day] = dateAdded.split('-').map(Number);
    const dt = new Date(year, month - 1, day);
    return dt.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  } catch {
    return dateAdded;
  }
}

export function getListings(): Listing[] {
  const listingsPath =
    process.env.LISTINGS_PATH ||
    path.resolve(process.cwd(), '..', 'listings.json');
  const raw = fs.readFileSync(listingsPath, 'utf-8');
  return JSON.parse(raw) as Listing[];
}

function processTable(
  listings: Listing[],
  type: 'summer' | 'offcycle' | 'newgrad'
): ProcessedRow[] {
  const filtered = listings.filter((e) => e.type === type);

  const sorted = [...filtered].sort((a, b) => {
    if (a.date_added !== b.date_added) {
      return b.date_added.localeCompare(a.date_added);
    }
    return companySortKey(a.company).localeCompare(companySortKey(b.company));
  });

  const rows: ProcessedRow[] = [];
  const groupTracker = new Set<string>();

  for (const entry of sorted) {
    const companyKey = companySortKey(entry.company);
    const groupKey = `${companyKey}__${entry.date_added}`;
    const isGrouped = groupTracker.has(groupKey);
    const companyDisplay = isGrouped ? '↳' : formatCompany(entry);
    groupTracker.add(groupKey);

    const rawLocations = entry.location
      .split(';')
      .map((l) => l.trim())
      .filter(Boolean);

    rows.push({
      companyDisplay,
      role: entry.role.trim(),
      location: entry.location.trim(),
      locations: rawLocations,
      type: entry.type,
      season: (entry.season || '').trim(),
      education: (entry.education || 'Undergrad').trim(),
      url: (entry.url || '').trim(),
      dateFormatted: formatDate(entry.date_added),
      gradDate: (entry.grad_date || '').trim(),
      isGrouped,
    });
  }

  return rows;
}

export function getAllListingsData(): ListingsData {
  const listings = getListings();
  const summer = processTable(listings, 'summer');
  const offcycle = processTable(listings, 'offcycle');
  const newgrad = processTable(listings, 'newgrad');
  return {
    summer,
    offcycle,
    newgrad,
    counts: {
      summer: summer.length,
      offcycle: offcycle.length,
      newgrad: newgrad.length,
    },
  };
}
