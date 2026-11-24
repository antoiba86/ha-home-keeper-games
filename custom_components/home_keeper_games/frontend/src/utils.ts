// Pure logic for the Home Keeper Games tab and card.
//
// Nothing here touches the DOM, the clock or Home Assistant. A caller gives the
// current time and the data. The mutation gate runs on this file, so each
// function has direct tests in `test/utils.test.js`.

import { t } from './i18n';
import type {
  Game,
  Unit,
  Copy,
  Lib,
  Loan,
  Person,
  RawPerson,
  PlayStatus,
  Platform,
  ProgressRow,
  RawState,
  Room,
  ScanResult,
  Shelf,
} from './types';

// ── Text ─────────────────────────────────────────────────────────────────────

/** Escape user text before it goes into innerHTML. */
export function escapeHTML(value: unknown): string {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

/** Lower case with no accents, for search and sort keys. */
export function fold(value: unknown): string {
  return String(value ?? '')
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase();
}

/** The initial letter of a name, upper case, or "?" for an empty name. */
export function initials(name: string): string {
  const first = name.trim().charAt(0);
  return first ? first.toUpperCase() : '?';
}

// ── State ────────────────────────────────────────────────────────────────────

/** A collection from the backend as a list. The backend can send a map or a list. */
export function asList<T>(value: Record<string, T> | T[] | null | undefined): T[] {
  if (!value) return [];
  return Array.isArray(value) ? [...value] : Object.values(value);
}

function byOrder<T extends { order: number; name: string }>(a: T, b: T): number {
  return (a.order ?? 0) - (b.order ?? 0) || a.name.localeCompare(b.name);
}

/** The avatar colors. A person gets the color of its place in the person order. */
export const PERSON_COLORS = ['#00695c', '#6a1b9a', '#c62828', '#1565c0', '#ef6c00', '#2e7d32', '#4527a0', '#ad1457'];

/**
 * The avatar color of the person at *index* in the person order. 2 people get
 * different colors while the palette has colors left.
 */
export function personColor(index: number): string {
  const n = PERSON_COLORS.length;
  return PERSON_COLORS[((index % n) + n) % n];
}

/** The people of a `get_state` reply, sorted by name, with their avatar colors. */
export function normalizePeople(raw: Record<string, RawPerson> | null | undefined): Person[] {
  return Object.entries(raw ?? {})
    .map(([id, row]) => ({
      id: row.person_id || id,
      name: row.name || id,
      share_progress: row.share_progress !== false,
      wishlist_todo: row.wishlist_todo ?? null,
      yearly_goal: row.yearly_goal ?? null,
    }))
    .sort((a, b) => a.name.localeCompare(b.name) || a.id.localeCompare(b.id))
    .map((p, i): Person => ({ ...p, color: personColor(i) }));
}

/** Turn the raw `get_state` reply into the `Lib` that the views read. */
export function normalizeState(raw: Partial<RawState>): Lib {
  const games = asList(raw.games).map((b) => ({
    ...b,
    tags: b.tags ?? [],
    genres: b.genres ?? [],
    progress: b.progress ?? {},
  }));
  return {
    rooms: asList(raw.rooms).sort(byOrder),
    units: asList(raw.units).sort(byOrder),
    shelves: asList(raw.shelves).sort(byOrder),
    games,
    copies: asList(raw.copies),
    loans: asList(raw.loans),
    people: normalizePeople(raw.people),
    me: { person_id: raw.me?.person_id ?? null, name: raw.me?.name ?? null, is_admin: raw.me?.is_admin === true },
    currency: raw.currency || 'USD',
  };
}

/** Person id to display name, read from the `person.*` entity attributes. */
export function personNames(
  states: Record<string, { entity_id: string; attributes: Record<string, unknown> }> | undefined,
): Record<string, string> {
  const out: Record<string, string> = {};
  for (const st of Object.values(states ?? {})) {
    if (!st.entity_id.startsWith('person.')) continue;
    const id = st.attributes.id;
    if (typeof id !== 'string' || !id) continue;
    const name = st.attributes.friendly_name;
    out[id] = typeof name === 'string' && name ? name : st.entity_id.slice(7);
  }
  return out;
}

// ── Index ────────────────────────────────────────────────────────────────────

export interface Index {
  room: Map<string, Room>;
  unit: Map<string, Unit>;
  shelf: Map<string, Shelf>;
  game: Map<string, Game>;
  copy: Map<string, Copy>;
  person: Map<string, Person>;
  copiesByGame: Map<string, Copy[]>;
  copiesByShelf: Map<string, Copy[]>;
  /** Loans that are not returned, by game id. */
  activeLoans: Map<string, Loan[]>;
  /** The open "out" loan of each copy. */
  loanByCopy: Map<string, Loan>;
}

function push<K, V>(map: Map<K, V[]>, key: K, value: V): void {
  const list = map.get(key);
  if (list) list.push(value);
  else map.set(key, [value]);
}

/** Build the lookup maps that the views use. */
export function buildIndex(lib: Lib): Index {
  const idx: Index = {
    room: new Map(lib.rooms.map((r) => [r.id, r])),
    unit: new Map(lib.units.map((c) => [c.id, c])),
    shelf: new Map(lib.shelves.map((s) => [s.id, s])),
    game: new Map(lib.games.map((b) => [b.id, b])),
    copy: new Map(lib.copies.map((c) => [c.id, c])),
    person: new Map(lib.people.map((p) => [p.id, p])),
    copiesByGame: new Map(),
    copiesByShelf: new Map(),
    activeLoans: new Map(),
    loanByCopy: new Map(),
  };
  for (const copy of lib.copies) {
    push(idx.copiesByGame, copy.game_id, copy);
    push(idx.copiesByShelf, copy.shelf_id ?? '', copy);
  }
  for (const loan of lib.loans) {
    if (loan.returned) continue;
    push(idx.activeLoans, loan.game_id, loan);
    if (loan.direction === 'out' && loan.copy_id) idx.loanByCopy.set(loan.copy_id, loan);
  }
  return idx;
}

/** The room, unit and shelf of a shelf id. Missing parts are null. */
export function shelfPath(
  idx: Index,
  shelfId: string | null | undefined,
): { room: Room | null; unit: Unit | null; shelf: Shelf | null } {
  const shelf = shelfId ? (idx.shelf.get(shelfId) ?? null) : null;
  const unit = shelf ? (idx.unit.get(shelf.unit_id) ?? null) : null;
  const room = unit ? (idx.room.get(unit.room_id) ?? null) : null;
  return { room, unit, shelf };
}

/** "Room › Unit › Shelf" for a shelf id, or '' for no shelf. */
export function locationLabel(idx: Index, shelfId: string | null | undefined): string {
  const { room, unit, shelf } = shelfPath(idx, shelfId);
  return [room?.name, unit?.name, shelf?.name].filter(Boolean).join(' › ');
}

/** "Room · Shelf", the short form for a game tile. */
export function shortLocation(idx: Index, shelfId: string | null | undefined): string {
  const { room, shelf } = shelfPath(idx, shelfId);
  return [room?.name, shelf?.name].filter(Boolean).join(' · ');
}

/** The shelves in display order: room, then unit, then shelf. */
export function orderedShelves(lib: Lib): Shelf[] {
  const out: Shelf[] = [];
  for (const room of lib.rooms) {
    for (const bc of lib.units) {
      if (bc.room_id !== room.id) continue;
      for (const sh of lib.shelves) if (sh.unit_id === bc.id) out.push(sh);
    }
  }
  return out;
}

/** The shelf after *shelfId* in display order, or null at the end. */
export function nextShelf(lib: Lib, shelfId: string | null): Shelf | null {
  const list = orderedShelves(lib);
  const at = list.findIndex((s) => s.id === shelfId);
  return at >= 0 && at + 1 < list.length ? list[at + 1] : null;
}

// ── Routes ───────────────────────────────────────────────────────────────────

export type View =
  | 'games'
  | 'game'
  | 'shelves'
  | 'loans'
  | 'wishlist'
  | 'scan'
  | 'import'
  | 'settings';

export interface TabRoute {
  view: View;
  /** The game id for `game`, the room id for `shelves`, else null. */
  id: string | null;
  /** The filter values that are not the default: the `;key=value` parameters. */
  query: Record<string, string>;
}

/** The default value of each query key. A default value is left out of the URL. */
export const QUERY_DEFAULTS: Record<string, string> = {
  status: 'all',
  owned: 'yes',
  sort: 'title',
  view: 'grid',
  tab: 'out',
  mode: 'shelf',
  step: 'setup',
};

/** The query keys that each view keeps, in URL order. */
const VIEW_QUERY: Record<View, string[]> = {
  games: ['q', 'status', 'room', 'shelf', 'reader', 'genre', 'owned', 'sort', 'view'],
  game: [],
  shelves: [],
  loans: ['tab'],
  wishlist: [],
  scan: ['shelf', 'mode', 'step', 'debug'],
  import: [],
  settings: [],
};

function parseQuery(search: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [key, value] of new URLSearchParams(search)) out[key] = value;
  return out;
}

function decodePart(value: string): string {
  try {
    return decodeURIComponent(value);
  } catch {
    return value;
  }
}

/** Add the `;key=value` parameters of a path segment to *into*. */
function parseParams(text: string, into: Record<string, string>): void {
  for (const part of text.split(';')) {
    const eq = part.indexOf('=');
    if (eq > 0) into[decodePart(part.slice(0, eq))] = decodePart(part.slice(eq + 1));
  }
}

function cleanQuery(view: View, query: Record<string, string>): Record<string, string> {
  const out: Record<string, string> = {};
  for (const key of VIEW_QUERY[view]) {
    const value = query[key];
    if (value && value !== QUERY_DEFAULTS[key]) out[key] = value;
  }
  return out;
}

/**
 * Parse the tab path (after `/home-keeper/games`) into a route.
 *
 * The filters of a view are `;key=value` parameters on the last segment, as in
 * `/games;q=le%20guin;status=read`. The host API of Home Keeper keeps the path
 * and drops a `?query`, so the parameters are in the path. A `?query` in the
 * path, or *search* when the path has none, is also read, and a parameter wins
 * over it. An unknown path gives the game list.
 */
export function parseRoute(path: string | undefined, search = ''): TabRoute {
  const raw = path ?? '';
  const q = raw.indexOf('?');
  const pathname = q >= 0 ? raw.slice(0, q) : raw;
  const query = parseQuery(q >= 0 ? raw.slice(q + 1) : search);
  const parts = pathname.split('/').filter(Boolean);
  const last = parts.length - 1;
  if (last >= 0) {
    const semi = parts[last].indexOf(';');
    if (semi >= 0) {
      parseParams(parts[last].slice(semi + 1), query);
      parts[last] = parts[last].slice(0, semi);
    }
  }
  const segs = parts.filter(Boolean).map(decodePart);
  const head = segs[0] ?? 'games';
  let view: View = 'games';
  let id: string | null = null;
  if (head === 'games' && segs[1]) {
    view = 'game';
    id = segs[1];
  } else if (head === 'shelves') {
    view = 'shelves';
    id = segs[1] ?? null;
  } else if (['loans', 'wishlist', 'scan', 'import', 'settings'].includes(head)) {
    view = head as View;
  }
  return { view, id, query: cleanQuery(view, query) };
}

/** Build the tab path for a route. The inverse of `parseRoute`. */
export function buildPath(route: { view: View; id?: string | null; query?: Record<string, string> }): string {
  const id = route.id ? `/${encodeURIComponent(route.id)}` : '';
  let path: string;
  if (route.view === 'game') path = `/games${id}`;
  else if (route.view === 'shelves') path = `/shelves${id}`;
  else path = `/${route.view}`;
  const query = cleanQuery(route.view, route.query ?? {});
  const params = Object.entries(query).map(([key, value]) => `;${key}=${encodeURIComponent(value)}`);
  return path + params.join('');
}

/** A copy of *query* with *key* set to *value*. An empty value removes the key. */
export function withQuery(
  query: Record<string, string>,
  key: string,
  value: string | null | undefined,
): Record<string, string> {
  const out = { ...query };
  if (value) out[key] = value;
  else delete out[key];
  return out;
}

// ── Game filters ─────────────────────────────────────────────────────────────

export type StatusFilter = 'all' | 'unplayed' | 'playing' | 'completed' | 'needs';
export const STATUS_FILTERS: StatusFilter[] = ['all', 'unplayed', 'playing', 'completed', 'needs'];
export type SortKey = 'title' | 'franchise' | 'added' | 'released' | 'rating';
export const SORT_KEYS: SortKey[] = ['title', 'franchise', 'added', 'released', 'rating'];

export interface GameFilters {
  q: string;
  status: StatusFilter;
  room: string;
  shelf: string;
  reader: string;
  genre: string;
  owned: 'yes' | 'no' | 'all';
  sort: SortKey;
  view: 'grid' | 'rows';
}

function oneOf<T extends string>(value: string | undefined, allowed: readonly T[], fallback: T): T {
  return allowed.includes(value as T) ? (value as T) : fallback;
}

/** Read the game filters from a route query. An unknown value reads as the default. */
export function readFilters(query: Record<string, string>): GameFilters {
  return {
    q: query.q ?? '',
    status: oneOf(query.status, STATUS_FILTERS, 'all'),
    room: query.room ?? '',
    shelf: query.shelf ?? '',
    reader: query.reader ?? '',
    genre: query.genre ?? '',
    owned: oneOf(query.owned, ['yes', 'no', 'all'] as const, 'yes'),
    sort: oneOf(query.sort, SORT_KEYS, 'title'),
    view: oneOf(query.view, ['grid', 'rows'] as const, 'grid'),
  };
}

/** True if a filter other than sort, layout and the owned default narrows the list. */
export function hasFilters(f: GameFilters): boolean {
  return Boolean(f.q || f.room || f.shelf || f.reader || f.genre || f.status !== 'all' || f.owned !== 'yes');
}

/** The play statuses, in the order of the status buttons. */
export const PLAY_STATUSES: PlayStatus[] = ['backlog', 'playing', 'completed', 'abandoned'];
// The status that sums up the rows of a person: the first in this list wins.
const STATUS_RANK: PlayStatus[] = ['playing', 'completed', 'backlog', 'abandoned'];

/** The progress rows of *personId* for *game*, in platform order. */
export function progressRows(game: Game, personId: string | null | undefined): Array<[Platform, ProgressRow]> {
  if (!personId) return [];
  const rows = game.progress?.[personId] ?? {};
  return PLATFORMS.filter((p) => rows[p]).map((p): [Platform, ProgressRow] => [p, rows[p]!]);
}

/** The progress row of *personId* for *game* on *platform*, or null. */
export function progressOf(game: Game, personId: string | null | undefined, platform: string | null | undefined): ProgressRow | null {
  if (!personId || !platform) return null;
  return game.progress?.[personId]?.[platform as Platform] ?? null;
}

/** The status that sums up the rows of *personId* for *game*: playing, then completed, backlog, abandoned. */
export function statusOf(game: Game, personId: string | null | undefined): PlayStatus | null {
  const have = new Set(progressRows(game, personId).map(([, row]) => row.play_status));
  return STATUS_RANK.find((s) => have.has(s)) ?? null;
}

/** The highest rating of *personId* for *game* on any platform, or 0. */
export function ratingOf(game: Game, personId: string | null | undefined): number {
  return Math.max(0, ...progressRows(game, personId).map(([, row]) => row.rating ?? 0));
}

/** The platforms of the copies of a game, in platform order. */
export function copyPlatforms(copies: Copy[]): Platform[] {
  const have = new Set(copies.map((c) => c.platform || 'other'));
  return PLATFORMS.filter((p) => have.has(p));
}

/**
 * The platform of a new progress row, as the backend picks it: the platform of the
 * copies when they all have the same one, else `other`.
 */
export function defaultPlatform(copies: Copy[]): Platform {
  const found = copyPlatforms(copies);
  return found.length === 1 ? found[0] : 'other';
}

/** The text that a search reads for a game. */
export function searchText(game: Game, personId: string | null, extra: Array<string | null> = []): string {
  const parts = [
    ...extra,
    game.title,
    game.franchise,
    ...game.genres,
    game.shared_notes,
    ...game.tags,
    ...progressRows(game, personId).map(([, row]) => row.review),
  ];
  return fold(parts.filter(Boolean).join(' \n '));
}

/** True if every word of *q* is in the search text of *game*. */
export function matchesSearch(game: Game, q: string, personId: string | null, extra: Array<string | null> = []): boolean {
  const words = fold(q).split(/\s+/).filter(Boolean);
  if (!words.length) return true;
  const text = searchText(game, personId, extra);
  const digits = text.replace(/-/g, '');
  return words.every((w) => text.includes(w) || (/^[\d-]+$/.test(w) && digits.includes(w.replace(/-/g, ''))));
}

export interface FilterContext {
  idx: Index;
  me: string | null;
}

function inPlace(game: Game, f: GameFilters, ctx: FilterContext): boolean {
  if (!f.room && !f.shelf) return true;
  const copies = ctx.idx.copiesByGame.get(game.id) ?? [];
  return copies.some((c) => {
    if (f.shelf === 'none') return !c.shelf_id;
    if (f.shelf && c.shelf_id !== f.shelf) return false;
    if (f.room && shelfPath(ctx.idx, c.shelf_id).room?.id !== f.room) return false;
    return true;
  });
}

function matchesStatus(game: Game, status: StatusFilter, me: string | null): boolean {
  const mine = statusOf(game, me);
  switch (status) {
    case 'unplayed':
      return !progressRows(game, me).some(([, row]) => row.play_status === 'completed');
    case 'playing':
      return mine === 'playing';
    case 'completed':
      return progressRows(game, me).some(([, row]) => row.play_status === 'completed');
    case 'needs':
      return game.needs_details;
    default:
      return true;
  }
}

/** True if *game* passes every filter except the status filter. */
export function matchesBase(game: Game, f: GameFilters, ctx: FilterContext): boolean {
  if (f.owned === 'yes' && !game.owned) return false;
  if (f.owned === 'no' && game.owned) return false;
  if (f.genre && !game.genres.includes(f.genre)) return false;
  if (f.reader && !progressRows(game, f.reader).some(([, row]) => row.play_status === 'completed')) return false;
  if (!inPlace(game, f, ctx)) return false;
  // Stryker disable next-line ArrayDeclaration: a string in the fallback maps to an undefined barcode, the same as no copy.
  const codes = (ctx.idx.copiesByGame.get(game.id) ?? []).map((c) => c.barcode);
  return matchesSearch(game, f.q, ctx.me, codes);
}

/** The games that pass all the filters, sorted. */
export function filterGames(games: Game[], f: GameFilters, ctx: FilterContext): Game[] {
  const out = games.filter((b) => matchesBase(b, f, ctx) && matchesStatus(b, f.status, ctx.me));
  return sortGames(out, f.sort, ctx.me);
}

/** The count for each status chip, with the other filters applied. */
export function statusCounts(games: Game[], f: GameFilters, ctx: FilterContext): Record<StatusFilter, number> {
  const counts: Record<StatusFilter, number> = { all: 0, unplayed: 0, playing: 0, completed: 0, needs: 0 };
  for (const game of games) {
    if (!matchesBase(game, f, ctx)) continue;
    for (const s of STATUS_FILTERS) if (matchesStatus(game, s, ctx.me)) counts[s] += 1;
  }
  return counts;
}

/** The year in a free text date such as "1969" or "March 2001", or null. */
export function yearOf(value: string | null | undefined): number | null {
  const m = String(value ?? '').match(/\b(\d{4})\b/);
  return m ? Number(m[1]) : null;
}

/** Sort games by *key*. Title is the tiebreak for every key. */
export function sortGames(games: Game[], key: SortKey, me: string | null): Game[] {
  const byTitle = (a: Game, b: Game) => fold(a.title).localeCompare(fold(b.title));
  const cmp: Record<SortKey, (a: Game, b: Game) => number> = {
    title: () => 0,
    // A game with no franchise sorts after every game with a franchise.
    franchise: (a, b) => (fold(a.franchise) || '\uffff').localeCompare(fold(b.franchise) || '\uffff'),
    added: (a, b) => String(b.created_at).localeCompare(String(a.created_at)),
    released: (a, b) => (yearOf(a.release_date) ?? 99999) - (yearOf(b.release_date) ?? 99999),
    rating: (a, b) => ratingOf(b, me) - ratingOf(a, me),
  };
  return [...games].sort((a, b) => cmp[key](a, b) || byTitle(a, b));
}

/** The genres of all games, sorted, with no duplicates. */
export function allGenres(games: Game[]): string[] {
  return [...new Set(games.flatMap((b) => b.genres))].sort((a, b) => a.localeCompare(b));
}

/** The second line of a game: its franchise, else its genres. */
export function gameByline(game: Game): string {
  return game.franchise || game.genres.join(', ');
}

// ── Copies ───────────────────────────────────────────────────────────────────

/** The formats of a copy, in display order. */
export const FORMATS = ['physical', 'digital', 'other'] as const;

/** The platforms of a copy, in display order. */
export const PLATFORMS = ['ps5', 'ps4', 'ps3', 'switch2', 'switch', 'xbox_series', 'xbox_one', 'pc', 'other'] as const;

/** The names of the platforms. They are product names, the same in each language. */
export const PLATFORM_NAMES: Record<string, string> = {
  ps5: 'PS5',
  ps4: 'PS4',
  ps3: 'PS3',
  switch2: 'Switch 2',
  switch: 'Switch',
  xbox_series: 'Xbox Series',
  xbox_one: 'Xbox One',
  pc: 'PC',
};

/** The name of a platform. `other` and an unknown value read as "Other platform". */
export function platformLabel(platform: string | null | undefined): string {
  return PLATFORM_NAMES[platform ?? ''] ?? t('copy.platform_other');
}

// ── Barcodes ─────────────────────────────────────────────────────────────────

/** The longest barcode that the integration stores. */
export const MAX_BARCODE = 50;

/** A barcode with no spaces and hyphens, in capital letters. */
export function cleanBarcode(value: string): string {
  return String(value ?? '')
    .replace(/[\s-]/g, '')
    .toUpperCase();
}

/** A typed or scanned barcode that the integration accepts, or null. */
export function normalizeBarcode(value: string): string | null {
  const code = cleanBarcode(value);
  return code.length > 0 && code.length <= MAX_BARCODE && /^[0-9A-Z]+$/.test(code) ? code : null;
}

/** True if the last digit of *digits* is the check digit of an EAN or a UPC code. */
export function hasRetailCheckDigit(digits: string): boolean {
  let sum = 0;
  const body = digits.slice(0, -1);
  for (let i = 0; i < body.length; i++) {
    // The digit next to the check digit has the weight 3.
    sum += Number(body[body.length - 1 - i]) * (i % 2 ? 1 : 3);
  }
  return (10 - (sum % 10)) % 10 === Number(digits[digits.length - 1]);
}

/**
 * The EAN-8, UPC-A or EAN-13 code in a text, or null. A field that takes a title or
 * a barcode reads the text as a barcode only when the check digit is correct, so a
 * title such as "1984" stays a title.
 */
export function retailBarcode(value: string): string | null {
  const code = cleanBarcode(value);
  if (!/^(\d{8}|\d{12}|\d{13})$/.test(code)) return null;
  return hasRetailCheckDigit(code) ? code : null;
}

/**
 * A gate for scanned codes: the same code is let through again only after
 * *windowMs*. The camera reads a barcode many times a second.
 */
export function makeCodeGate(windowMs: number): (code: string, nowMs: number) => boolean {
  const seen = new Map<string, number>();
  return (code, nowMs) => {
    const last = seen.get(code);
    if (last !== undefined && nowMs - last < windowMs) return false;
    seen.set(code, nowMs);
    return true;
  };
}

/** Call *fn* once, *ms* after the last call. `cancel` stops a pending call. */
export function debounce<A extends unknown[]>(
  fn: (...args: A) => void,
  ms: number,
): ((...args: A) => void) & { cancel: () => void } {
  let timer: ReturnType<typeof setTimeout> | undefined;
  const wrapped = (...args: A) => {
    if (timer !== undefined) clearTimeout(timer);
    timer = setTimeout(() => {
      timer = undefined;
      fn(...args);
    }, ms);
  };
  wrapped.cancel = () => {
    if (timer !== undefined) clearTimeout(timer);
    timer = undefined;
  };
  return wrapped;
}

// ── Drawing ──────────────────────────────────────────────────────────────────

/** FNV-1a hash of a string, as an unsigned 32-bit integer. */
export function hash(value: string): number {
  let h = 0x811c9dc5;
  for (let i = 0; i < value.length; i++) {
    h ^= value.charCodeAt(i);
    h = Math.imul(h, 0x01000193);
  }
  return h >>> 0;
}

/** Cover colors: a background and the ink for the title on it. */
export const COVER_COLORS: Array<[string, string]> = [
  ['#2f3e46', '#f1e9d2'],
  ['#1d4e89', '#fdf6e3'],
  ['#b5651d', '#fff8ec'],
  ['#5c2a6b', '#f6e9ff'],
  ['#264d3b', '#e8f3e0'],
  ['#8d6e3f', '#fffaf0'],
  ['#0f3d56', '#e3f2fd'],
  ['#7a2e2e', '#fdecea'],
  ['#3b6e3b', '#f1f8e9'],
  ['#a33b5c', '#fff0f5'],
  ['#37474f', '#eceff1'],
  ['#4e342e', '#efebe9'],
];

/** The cover colors of a game id. The same id always gives the same colors. */
export function coverColors(id: string): { bg: string; ink: string } {
  const [bg, ink] = COVER_COLORS[hash(id) % COVER_COLORS.length];
  return { bg, ink };
}

export interface Spine {
  id: string;
  title: string;
  w: number;
  h: number;
  color: string;
}

/**
 * The spines to draw for the games on a shelf. Width, height and color come from
 * the game id.
 */
export function spines(games: Game[], max = 60): Spine[] {
  return games.slice(0, max).map((b) => {
    const h = hash(b.id);
    const w = 8 + (h % 10);
    return {
      id: b.id,
      title: b.title,
      w,
      h: 56 + ((h >>> 8) % 27),
      color: COVER_COLORS[h % COVER_COLORS.length][0],
    };
  });
}

// ── Dates and numbers ────────────────────────────────────────────────────────

function pad(n: number): string {
  return String(n).padStart(2, '0');
}

/** The local date of *now* as YYYY-MM-DD. */
export function todayISO(now: Date): string {
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

/** Days from date *a* to date *b* (both YYYY-MM-DD). Positive if *b* is later. */
export function daysBetween(a: string, b: string): number {
  const ms = Date.parse(`${b.slice(0, 10)}T00:00:00Z`) - Date.parse(`${a.slice(0, 10)}T00:00:00Z`);
  return Math.round(ms / 86400000);
}

export type DueKind = 'none' | 'overdue' | 'today' | 'soon' | 'later';

/** How a due date relates to *today*. "soon" is 1 to 3 days ahead. */
export function dueState(due: string | null | undefined, today: string): { kind: DueKind; days: number } {
  if (!due) return { kind: 'none', days: 0 };
  const days = daysBetween(today, due);
  if (days < 0) return { kind: 'overdue', days: -days };
  if (days === 0) return { kind: 'today', days: 0 };
  return { kind: days <= 3 ? 'soon' : 'later', days };
}

/** A whole number from a form value, or null for an empty or bad value. */
export function intOrNull(value: unknown): number | null {
  const s = String(value ?? '').trim();
  if (!s) return null;
  const n = Number(s);
  return Number.isInteger(n) ? n : null;
}

/** A number from a form value, or null for an empty or bad value. */
export function numberOrNull(value: unknown): number | null {
  const s = String(value ?? '').trim().replace(',', '.');
  if (!s) return null;
  const n = Number(s);
  return Number.isFinite(n) ? n : null;
}

/** A comma list from a form as a list of trimmed values. */
export function splitList(value: string): string[] {
  return String(value ?? '')
    .split(/[,;\n]/)
    .map((s) => s.trim())
    .filter(Boolean);
}

// ── Card ─────────────────────────────────────────────────────────────────────

export interface Activity {
  person: Person;
  game: Game;
  platform: Platform;
  row: ProgressRow;
}

export interface CardModel {
  playing: Array<{ game: Game; platform: Platform; row: ProgressRow }>;
  backlog: Game[];
  goal: { done: number; goal: number | null; year: number };
  household: Activity[];
}

/** The data that the card shows for *personId* at *now*. */
export function cardModel(lib: Lib, personId: string | null, now: Date, maxActivity = 5): CardModel {
  const year = now.getFullYear();
  const playing: CardModel['playing'] = [];
  const backlog: Game[] = [];
  let done = 0;
  const household: Activity[] = [];
  const person = new Map(lib.people.map((p) => [p.id, p]));
  for (const game of lib.games) {
    for (const pid of Object.keys(game.progress)) {
      const rows = progressRows(game, pid);
      if (pid === personId) {
        for (const [platform, row] of rows) if (row.play_status === 'playing') playing.push({ game, platform, row });
        if (rows.some(([, row]) => row.play_status === 'backlog')) backlog.push(game);
        if (rows.some(([, row]) => row.play_status === 'completed' && yearOf(row.completed_at) === year)) done += 1;
      } else if (person.get(pid)?.share_progress) {
        for (const [platform, row] of rows) {
          if (row.play_status !== 'backlog') household.push({ person: person.get(pid)!, game, platform, row });
        }
      }
    }
  }
  household.sort((a, b) => String(b.row.updated_at).localeCompare(String(a.row.updated_at)));
  playing.sort((a, b) => String(b.row.updated_at).localeCompare(String(a.row.updated_at)));
  return {
    playing,
    backlog,
    goal: { done, goal: personId ? (person.get(personId)?.yearly_goal ?? null) : null, year },
    household: household.slice(0, maxActivity),
  };
}

/** One item of *items*, picked with *rnd* (0 <= rnd < 1), or null for an empty list. */
export function pickRandom<T>(items: T[], rnd: number): T | null {
  if (!items.length) return null;
  return items[Math.min(items.length - 1, Math.floor(rnd * items.length))];
}

// ── Scan ─────────────────────────────────────────────────────────────────────

export interface ScanTally {
  added: number;
  moved: number;
  needs: number;
  duplicate: number;
  skipped: number;
}

/** Count the results of a scan session. */
export function scanTally(results: Array<Pick<ScanResult, 'result' | 'game'>>): ScanTally {
  const out: ScanTally = { added: 0, moved: 0, needs: 0, duplicate: 0, skipped: 0 };
  for (const r of results) {
    if (r.result === 'added') out.added += 1;
    else if (r.result === 'moved') out.moved += 1;
    else if (r.result === 'duplicate') out.duplicate += 1;
    else if (r.result === 'skipped') out.skipped += 1;
    if (r.result === 'not_found' || r.game?.needs_details) out.needs += 1;
  }
  return out;
}

/** A scan row that can ask for a title: its reply, and what the user did. */
export interface MissRow {
  res: Pick<ScanResult, 'result' | 'game'> | null;
  named?: boolean;
  removed?: boolean;
}

/**
 * The first scan of a barcode that no game had, and that still has no title from
 * the user, or null. The scan pauses until the user names or removes it.
 */
export function nextMiss<T extends MissRow>(results: T[]): T | null {
  return results.find((r) => r.res?.result === 'not_found' && r.res.game !== null && !r.named && !r.removed) ?? null;
}

// ── Loans ────────────────────────────────────────────────────────────────────

export type LoanTab = 'out' | 'in' | 'returned';

/** The loans of a tab. Open loans sort by due date, returned ones newest first. */
export function loansFor(loans: Loan[], tab: LoanTab): Loan[] {
  if (tab === 'returned') {
    return loans
      .filter((l) => l.returned)
      .sort((a, b) => String(b.returned).localeCompare(String(a.returned)));
  }
  return loans
    .filter((l) => !l.returned && l.direction === tab)
    .sort((a, b) => (a.due ?? '9999').localeCompare(b.due ?? '9999') || a.started.localeCompare(b.started));
}

/** The game value of a room: the sum of copy values. */
export function roomValue(lib: Lib, idx: Index, roomId: string): number {
  let sum = 0;
  for (const copy of lib.copies) {
    if (shelfPath(idx, copy.shelf_id).room?.id === roomId) sum += copy.value ?? 0;
  }
  return sum;
}

// ── Import ───────────────────────────────────────────────────────────────────

/** The number of data rows in a CSV text: records after the header, not lines. */
export function csvRowCount(text: string): number {
  let rows = 0;
  let quoted = false;
  let filled = false;
  for (const c of text) {
    if (c === '"') {
      quoted = !quoted;
      filled = true;
    } else if (c === '\n' && !quoted) {
      if (filled) rows += 1;
      filled = false;
    } else if (c !== '\r') {
      filled = true;
    }
  }
  if (filled) rows += 1;
  return Math.max(0, rows - 1);
}

// ── Covers ───────────────────────────────────────────────────────────────────

/** The life of a signed cover URL in seconds: the `expires` of `auth/sign_path`. */
export const COVER_SIGN_SECONDS = 3600;

/** After this time a cover is signed again, well before its URL expires. */
export const COVER_RESIGN_MS = 45 * 60 * 1000;

/** A signed URL is not used in its last minute, so an image does not load a dead URL. */
const COVER_USE_MS = COVER_SIGN_SECONDS * 1000 - 60 * 1000;

/**
 * Signed cover URLs. The cover view needs a signed-in user, and an `<img>` cannot
 * send the token, so each cover path is signed with `auth/sign_path` before the
 * render that shows it. An entry is reused until it is old, and calls for the
 * same path while a sign runs share that sign. A failed sign keeps the old URL.
 */
export class CoverUrls {
  private readonly _entries = new Map<string, { url: string; at: number }>();
  private readonly _pending = new Map<string, Promise<boolean>>();

  /** Forget every signed URL. */
  clear(): void {
    this._entries.clear();
  }

  /** The signed URL of *path* at *now*, or undefined if it has none that is usable. */
  get(path: string, now: number): string | undefined {
    const entry = this._entries.get(path);
    return entry && now - entry.at < COVER_USE_MS ? entry.url : undefined;
  }

  /** Sign each path that has no fresh URL. Resolves to true if a URL was signed. */
  async ensure(paths: Iterable<string>, sign: (path: string) => Promise<string>, now: number): Promise<boolean> {
    const jobs: Array<Promise<boolean>> = [];
    for (const path of new Set(paths)) {
      const entry = this._entries.get(path);
      if (entry && now - entry.at < COVER_RESIGN_MS) continue;
      let job = this._pending.get(path);
      if (!job) {
        job = sign(path)
          .then(
            (url) => {
              this._entries.set(path, { url, at: now });
              return true;
            },
            // Stryker disable next-line ArrowFunction: undefined and false both read as "not signed" in .some(Boolean).
            () => false,
          )
          .finally(() => this._pending.delete(path));
        this._pending.set(path, job);
      }
      jobs.push(job);
    }
    return (await Promise.all(jobs)).some(Boolean);
  }
}
