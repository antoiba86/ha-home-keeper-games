// The Games view (grid and rows) and the Game detail view.

import { formatDate, formatMoney, t, tn } from './i18n';
import { markdownBlock } from './markdown';
import {
  button,
  cover,
  taskLinkHtml,
  href,
  ICONS,
  link,
  navBar,
  options,
  personDot,
  statusLabel,
  statusPill,
} from './markup';
import type { ViewCtx } from './tab-types';
import type { Game, Copy, Loan, Platform } from './types';
import {
  allGenres,
  copyPlatforms,
  defaultPlatform,
  gameByline,
  platformLabel,
  buildPath,
  dueState,
  escapeHTML,
  filterGames,
  hasFilters,
  locationLabel,
  PLATFORMS,
  PLAY_STATUSES,
  progressOf,
  progressRows,
  readFilters,
  ratingOf,
  shelfPath,
  shortLocation,
  SORT_KEYS,
  STATUS_FILTERS,
  statusCounts,
  statusOf,
  type GameFilters,
} from './utils';

export function navCounts(ctx: ViewCtx): { loans: number; wishlist: number } {
  return {
    loans: ctx.lib.loans.filter((l) => !l.returned).length,
    wishlist: ctx.lib.games.filter((b) => b.wishlist && !b.wishlist.bought).length,
  };
}

function menu(label: string, key: string, items: Array<[string, string]>, value: string): string {
  return `<label class="hkl-menu"><span class="hkl-menu-label">${escapeHTML(label)}</span><select data-chg="filter" data-key="${key}" data-k="f-${key}">${options(items, value)}</select></label>`;
}

function readerDots(ctx: ViewCtx, game: Game): string {
  return ctx.lib.people
    .map((p) => {
      const st = statusOf(game, p.id);
      return st === 'completed' || st === 'playing' ? personDot(p, st) : '';
    })
    .join('');
}

function loanPill(ctx: ViewCtx, game: Game): string {
  const loan = ctx.idx.activeLoans.get(game.id)?.[0];
  if (!loan) return '';
  const due = loan.due ? ` · ${t('loan.due_short', { date: formatDate(loan.due, false) })}` : '';
  const label = loan.direction === 'out' ? t('loan.lent_pill', { party: loan.party ?? '' }) : t('loan.borrowed_pill', { party: loan.party ?? '' });
  const late = dueState(loan.due, ctx.today).kind === 'overdue' ? ' late' : '';
  return `<span class="hkl-pill loan${late}">${escapeHTML(label)}${escapeHTML(due)}</span>`;
}

function firstShelf(ctx: ViewCtx, game: Game): string | null {
  const copies = ctx.idx.copiesByGame.get(game.id) ?? [];
  return copies.find((c) => c.shelf_id)?.shelf_id ?? null;
}

function tile(ctx: ViewCtx, game: Game): string {
  const path = `/games/${encodeURIComponent(game.id)}`;
  const loc = game.owned ? shortLocation(ctx.idx, firstShelf(ctx, game)) || t('common.no_shelf') : '';
  const badge = game.cover?.kind === 'custom' ? `<span class="hkl-cover-badge">${escapeHTML(t('game.custom_cover'))}</span>` : '';
  return `<a class="hkl-tile" href="${escapeHTML(href(path))}" data-act="nav" data-path="${escapeHTML(path)}" data-k="b-${escapeHTML(game.id)}">
    ${cover(game, 'tile', badge)}
    <span class="hkl-tile-title">${escapeHTML(game.title)}</span>
    <span class="hkl-tile-author">${escapeHTML(gameByline(game))}</span>
    <span class="hkl-tile-meta">${loc ? `<span class="hkl-loc">${escapeHTML(loc)}</span>` : ''}${game.wishlist ? `<span class="hkl-loc">${escapeHTML(t('nav.wishlist'))}</span>` : ''}</span>
    <span class="hkl-tile-readers">${readerDots(ctx, game)}</span>
    ${game.needs_details ? `<span class="hkl-pill warn">${escapeHTML(t('filter.needs'))}</span>` : ''}
    ${loanPill(ctx, game)}
  </a>`;
}

function row(ctx: ViewCtx, game: Game): string {
  const path = `/games/${encodeURIComponent(game.id)}`;
  const loc = game.owned ? shortLocation(ctx.idx, firstShelf(ctx, game)) || t('common.no_shelf') : t('game.not_owned');
  return `<a class="hkl-row" href="${escapeHTML(href(path))}" data-act="nav" data-path="${escapeHTML(path)}" data-k="b-${escapeHTML(game.id)}">
    ${cover(game, 'thumb')}
    <span class="hkl-row-main"><span class="hkl-row-title">${escapeHTML(game.title)}</span><span class="hkl-row-sub">${escapeHTML(gameByline(game))}</span><span class="hkl-row-loc">${escapeHTML(loc)}</span></span>
    <span class="hkl-row-dots">${readerDots(ctx, game)}${loanPill(ctx, game)}</span>
    ${statusPill(statusOf(game, ctx.me))}
  </a>`;
}

function summaryLine(ctx: ViewCtx, f: GameFilters, count: number): string {
  const parts: string[] = [];
  if (f.room) parts.push(ctx.idx.room.get(f.room)?.name ?? '');
  if (f.shelf === 'none') parts.push(t('common.no_shelf'));
  else if (f.shelf) parts.push(ctx.idx.shelf.get(f.shelf)?.name ?? '');
  if (f.reader) parts.push(t('filter.completed_by_name', { name: ctx.idx.person.get(f.reader)?.name ?? '' }));
  if (f.genre) parts.push(f.genre);
  if (f.owned === 'no') parts.push(t('filter.owned_no'));
  if (f.owned === 'all') parts.push(t('filter.owned_all'));
  if (f.q) parts.push(`"${f.q}"`);
  const label = parts.filter(Boolean).join(' · ');
  return `<div class="hkl-summary">${label ? `<span class="hkl-eyebrow">${escapeHTML(label)}</span>` : ''}<span class="hkl-badge">${escapeHTML(tn('count.games', count))}</span>${hasFilters(f) ? `<button class="hkl-link" data-act="clear-filters" data-k="clear">${escapeHTML(t('filter.clear'))}</button>` : ''}</div>`;
}

/** The Games view. */
export function renderGames(ctx: ViewCtx): string {
  const f = readFilters(ctx.route.query);
  const fctx = { idx: ctx.idx, me: ctx.me };
  const games = filterGames(ctx.lib.games, f, fctx);
  const counts = statusCounts(ctx.lib.games, f, fctx);
  const chips = STATUS_FILTERS.map((s) => {
    const on = f.status === s;
    return `<button class="hkl-seg${on ? ' on' : ''}" data-act="status" data-value="${s}" data-k="st-${s}" aria-pressed="${on}">${escapeHTML(t(`filter.${s}`))} <span class="hkl-seg-n">${counts[s]}</span></button>`;
  }).join('');
  const rooms: Array<[string, string]> = [['', t('filter.any')], ...ctx.lib.rooms.map((r): [string, string] => [r.id, r.name])];
  const shelves: Array<[string, string]> = [['', t('filter.any')], ['none', t('common.no_shelf')]];
  for (const sh of ctx.lib.shelves) {
    const { room, unit } = shelfPath(ctx.idx, sh.id);
    if (f.room && room?.id !== f.room) continue;
    shelves.push([sh.id, [room?.name, unit?.name, sh.name].filter(Boolean).join(' › ')]);
  }
  const readers: Array<[string, string]> = [['', t('filter.anyone')], ...ctx.lib.people.map((p): [string, string] => [p.id, p.name])];
  const genres: Array<[string, string]> = [['', t('filter.any')], ...allGenres(ctx.lib.games).map((s): [string, string] => [s, s])];
  const sorts = SORT_KEYS.map((k): [string, string] => [k, t(`sort.${k}`)]);
  const owned: Array<[string, string]> = [
    ['yes', t('filter.owned_yes')],
    ['all', t('filter.owned_all')],
    ['no', t('filter.owned_no')],
  ];
  const shown = games.slice(0, ctx.ui.limit);
  const list = f.view === 'rows'
    ? `<div class="hkl-rows">${shown.map((b) => row(ctx, b)).join('')}</div>`
    : `<div class="hkl-grid">${shown.map((b) => tile(ctx, b)).join('')}</div>`;
  const more = games.length > shown.length
    ? `<div class="hkl-more">${button(escapeHTML(t('games.show_more', { n: games.length - shown.length })), 'more', 'outline', 'data-k="more"')}</div>`
    : '';
  const empty = !games.length
    ? `<div class="hkl-empty">${escapeHTML(ctx.lib.games.length ? t('games.no_match') : t('games.empty'))}</div>`
    : '';
  const actions = `${button(`${ICONS.scan}${escapeHTML(t('action.scan_games'))}`, 'nav', 'primary', 'data-path="/scan" data-k="scan-games"')}
    ${button(escapeHTML(t('action.add_game')), 'add-game', 'tonal', 'data-k="add-game"')}
    ${button(escapeHTML(t('action.import')), 'nav', 'text', 'data-path="/import" data-k="import"')}`;
  return `${navBar(ctx.route, navCounts(ctx), actions)}
  <div class="hkl-filterbar">
    <div class="hkl-segs" role="group" aria-label="${escapeHTML(t('filter.status_label'))}">${chips}</div>
    <label class="hkl-search">${ICONS.search}<input type="search" data-input="q" data-k="q" aria-label="${escapeHTML(t('games.search_label'))}" placeholder="${escapeHTML(t('games.search_placeholder'))}" value="${escapeHTML(f.q)}" /></label>
  </div>
  <div class="hkl-menus">
    ${menu(t('filter.room'), 'room', rooms, f.room)}
    ${menu(t('filter.shelf'), 'shelf', shelves, f.shelf)}
    ${menu(t('filter.completed_by'), 'reader', readers, f.reader)}
    ${menu(t('filter.genre'), 'genre', genres, f.genre)}
    ${menu(t('filter.owned'), 'owned', owned, f.owned)}
    ${menu(t('filter.sort'), 'sort', sorts, f.sort)}
    <div class="hkl-spacer"></div>
    <div class="hkl-toggle" role="group" aria-label="${escapeHTML(t('games.layout'))}">
      <button data-act="layout" data-value="grid" data-k="lay-grid" class="${f.view === 'grid' ? 'on' : ''}" aria-pressed="${f.view === 'grid'}" aria-label="${escapeHTML(t('games.layout_grid'))}" title="${escapeHTML(t('games.layout_grid'))}">${ICONS.grid}</button>
      <button data-act="layout" data-value="rows" data-k="lay-rows" class="${f.view === 'rows' ? 'on' : ''}" aria-pressed="${f.view === 'rows'}" aria-label="${escapeHTML(t('games.layout_rows'))}" title="${escapeHTML(t('games.layout_rows'))}">${ICONS.rows}</button>
    </div>
  </div>
  ${summaryLine(ctx, f, games.length)}
  ${empty}${list}${more}
  <div class="hkl-legend"><span><span class="hkl-ring ring-completed" aria-hidden="true"></span>${escapeHTML(t('status.completed'))}</span><span><span class="hkl-ring ring-playing" aria-hidden="true"></span>${escapeHTML(t('status.playing'))}</span></div>`;
}

// ── Game detail ──────────────────────────────────────────────────────────────

function stars(rating: number | null): string {
  const out: string[] = [];
  for (let i = 1; i <= 5; i++) {
    const on = rating != null && i <= rating;
    out.push(`<button class="hkl-star${on ? ' on' : ''}" data-act="rate" data-value="${i}" data-k="star-${i}" aria-label="${escapeHTML(tn('game.stars', i))}" aria-pressed="${on}">${ICONS.star}</button>`);
  }
  return `<div class="hkl-stars" role="group" aria-label="${escapeHTML(t('game.rating'))}">${out.join('')}</div>`;
}

function loanBox(ctx: ViewCtx, loan: Loan): string {
  const due = dueState(loan.due, ctx.today);
  const dueText = loan.due
    ? due.kind === 'overdue'
      ? tn('loan.overdue_days', due.days)
      : t('loan.due_on', { date: formatDate(loan.due) })
    : t('loan.no_date');
  const task = loan.hk_task_id
    ? `${taskLinkHtml(ctx, loan.hk_task_id)} · `
    : '';
  const head = loan.direction === 'out' ? t('game.loan_out') : t('game.loan_in');
  return `<div class="hkl-box${due.kind === 'overdue' ? ' late' : ''}">
    <span class="hkl-eyebrow">${escapeHTML(head)}</span>
    <span class="hkl-box-main">${escapeHTML(t('loan.party_since', { party: loan.party ?? '', date: formatDate(loan.started) }))}</span>
    <span class="hkl-box-sub">${task}${escapeHTML(dueText)}</span>
    <span class="hkl-box-actions">${button(escapeHTML(t('action.return')), 'return-loan', 'tonal', `data-id="${escapeHTML(loan.id)}" data-k="ret-${escapeHTML(loan.id)}"`)}</span>
  </div>`;
}

function copyBox(ctx: ViewCtx, copy: Copy, index: number, total: number): string {
  const loc = copy.shelf_id ? locationLabel(ctx.idx, copy.shelf_id) : t('common.no_shelf');
  const room = shelfPath(ctx.idx, copy.shelf_id).room;
  const label = total > 1 ? t('game.location_n', { n: index + 1 }) : t('game.location');
  const lent = ctx.idx.loanByCopy.get(copy.id);
  return `<div class="hkl-box">
    <span class="hkl-eyebrow">${escapeHTML(label)}</span>
    <span class="hkl-box-main">${escapeHTML(loc)}</span>
    <span class="hkl-box-sub">${escapeHTML(`${platformLabel(copy.platform)} · ${t(`format.kind_${copy.format}`)}`)}${lent ? ` · ${escapeHTML(t('loan.lent_pill', { party: lent.party ?? '' }))}` : ''}</span>
    <span class="hkl-box-actions">${button(escapeHTML(t('action.move')), 'move-copy', 'tonal', `data-id="${escapeHTML(copy.id)}" data-k="mv-${escapeHTML(copy.id)}"`)}${room ? button(escapeHTML(t('action.open_shelf')), 'nav', 'text', `data-path="/shelves/${escapeHTML(encodeURIComponent(room.id))}" data-k="os-${escapeHTML(copy.id)}"`) : ''}</span>
  </div>`;
}

function copyDetails(ctx: ViewCtx, copies: Copy[]): string {
  if (!copies.length) {
    return `<section class="hkl-card"><h2>${escapeHTML(t('game.copy_details'))}</h2><p class="hkl-muted">${escapeHTML(t('game.no_copies'))}</p>${button(escapeHTML(t('action.add_copy')), 'add-copy', 'tonal', 'data-k="add-copy"')}</section>`;
  }
  const cur = ctx.lib.currency;
  const blocks = copies
    .map((c) => {
      const kv = (k: string, v: string) => (v ? `<span class="hkl-kv"><span>${escapeHTML(k)}</span><span>${escapeHTML(v)}</span></span>` : '');
      const bought = [c.acquired ? formatDate(c.acquired) : '', c.acquired_from ?? ''].filter(Boolean).join(' · ');
      const flags = [c.steelbook ? t('copy.steelbook') : ''].filter(Boolean);
      return `<div class="hkl-copy">
        ${copies.length > 1 ? `<span class="hkl-eyebrow">${escapeHTML(locationLabel(ctx.idx, c.shelf_id) || t('common.no_shelf'))}</span>` : ''}
        ${kv(t('copy.platform'), platformLabel(c.platform))}
        ${kv(t('copy.format'), t(`format.kind_${c.format}`))}
        ${kv(t('copy.storefront'), c.storefront)}
        ${kv(t('copy.region'), c.region)}
        ${kv(t('copy.edition'), c.edition)}
        ${kv(t('game.barcode_label'), c.barcode ?? '')}
        ${kv(t('copy.condition'), c.condition ? t(`condition.${c.condition}`) : '')}
        ${kv(t('copy.bought'), bought)}
        ${kv(t('copy.price'), formatMoney(c.price, cur))}
        ${kv(t('copy.value'), formatMoney(c.value, cur))}
        ${flags.length ? `<span class="hkl-chips">${flags.map((x) => `<span class="hkl-chip">${escapeHTML(x)}</span>`).join('')}</span>` : ''}
        ${c.note ? `<span class="hkl-muted">${escapeHTML(c.note)}</span>` : ''}
        <span class="hkl-box-actions">${button(escapeHTML(t('action.edit_copy')), 'edit-copy', 'text', `data-id="${escapeHTML(c.id)}" data-k="ec-${escapeHTML(c.id)}"`)}${button(escapeHTML(t('action.delete_copy')), 'delete-copy', 'text', `data-id="${escapeHTML(c.id)}" data-k="dc-${escapeHTML(c.id)}"`)}</span>
      </div>`;
    })
    .join('');
  return `<section class="hkl-card"><h2>${escapeHTML(t('game.copy_details'))}</h2>${blocks}${button(escapeHTML(t('action.add_copy')), 'add-copy', 'text', 'data-k="add-copy"')}</section>`;
}

/** The person and the platform that the progress form edits. */
export function progressTarget(ctx: ViewCtx, game: Game): { pid: string | null; platform: Platform; chips: Platform[] } {
  const pid = ctx.ui.progressPerson ?? ctx.me;
  const copies = ctx.idx.copiesByGame.get(game.id) ?? [];
  const have = new Set<Platform>([...progressRows(game, pid).map(([p]) => p), ...copyPlatforms(copies)]);
  const wanted = ctx.ui.progressPlatform;
  if (wanted) have.add(wanted);
  const chips = PLATFORMS.filter((p) => have.has(p));
  return { pid, platform: wanted ?? chips[0] ?? defaultPlatform(copies), chips };
}

function field(label: string, key: string, type: 'number' | 'date', value: unknown): string {
  const num = type === 'number' ? ' min="0" inputmode="numeric"' : '';
  return `<label class="hkl-field small">${escapeHTML(label)}<input type="${type}"${num} data-chg="progress-field" data-key="${key}" data-k="r-${key}" value="${escapeHTML(value ?? '')}" /></label>`;
}

function progressSection(ctx: ViewCtx, game: Game): string {
  const { pid, platform, chips } = progressTarget(ctx, game);
  const row = progressOf(game, pid, platform);
  const st = row?.play_status ?? null;
  const plats = chips
    .map((p) => {
      const on = p === platform;
      const r = progressOf(game, pid, p);
      const label = r ? `${platformLabel(p)} · ${statusLabel(r.play_status)}` : platformLabel(p);
      return `<button class="hkl-plat${on ? ' on' : ''}" data-act="progress-platform" data-value="${p}" data-k="pp-${p}" aria-pressed="${on}">${escapeHTML(label)}</button>`;
    })
    .join('');
  const rest = PLATFORMS.filter((p) => !chips.includes(p));
  const add = rest.length
    ? `<select class="hkl-plat-add" data-chg="progress-platform" data-k="pp-add" aria-label="${escapeHTML(t('game.add_platform'))}"><option value="">+ ${escapeHTML(t('game.platform'))}</option>${options(rest.map((p): [string, string] => [p, platformLabel(p)]), null)}</select>`
    : '';
  const seg = PLAY_STATUSES.map((s) => {
    const on = st === s;
    return `<button class="hkl-seg${on ? ' on' : ''}" data-act="set-status" data-value="${s}" data-k="rs-${s}" aria-pressed="${on}">${on ? ICONS.check : ''}${escapeHTML(statusLabel(s))}</button>`;
  }).join('');
  const facts: string[] = [];
  if (row?.play_status === 'completed' && row.completed_at) facts.push(t('game.completed_on', { date: formatDate(row.completed_at) }));
  if (row && row.completion_count > 1) facts.push(tn('game.completed_times', row.completion_count));
  const people = ctx.lib.people.filter((p) => p.id !== pid);
  const household = people
    .map((p) => {
      const rows = progressRows(game, p.id);
      const text = rows.map(([plat, r]) => `${platformLabel(plat)} ${statusLabel(r.play_status)}`).join(' · ');
      const rating = ratingOf(game, p.id);
      const stars = rating ? ` · ${tn('game.stars', rating)}` : '';
      const pill = rows.length ? '' : statusPill(null);
      return `<div class="hkl-hh">${personDot(p)}<span class="hkl-hh-name">${escapeHTML(p.name)}</span>${pill}<span class="hkl-muted">${escapeHTML(text + stars)}</span></div>`;
    })
    .join('');
  const pick = ctx.lib.people.length > 1
    ? `<label class="hkl-inline">${escapeHTML(t('common.person'))} <select data-chg="progress-person" data-k="rp">${options(ctx.lib.people.map((p) => [p.id, p.name]), pid)}</select></label>`
    : `<span class="hkl-muted">${escapeHTML(t('common.person'))} ${escapeHTML(ctx.idx.person.get(pid ?? '')?.name ?? '')}</span>`;
  const fields = [
    field(t('game.playtime'), 'playtime_minutes', 'number', row?.playtime_minutes),
    field(t('game.started'), 'started_at', 'date', row?.started_at),
    field(t('game.completed_at'), 'completed_at', 'date', row?.completed_at),
    field(t('game.last_played'), 'last_played_at', 'date', row?.last_played_at),
    field(t('game.completions'), 'completion_count', 'number', row?.completion_count ?? 0),
  ].join('');
  const clear = row ? button(escapeHTML(t('game.remove_platform')), 'progress-clear', 'text', 'data-k="progress-clear"') : '';
  return `<section class="hkl-card">
    <div class="hkl-card-head"><h2>${escapeHTML(t('game.progress'))}</h2>${pick}</div>
    <div class="hkl-plats" role="group" aria-label="${escapeHTML(t('game.platform'))}">${plats}${add}</div>
    <div class="hkl-progress">
      <div class="hkl-segs" role="group" aria-label="${escapeHTML(t('game.progress'))}">${seg}</div>
      ${stars(row?.rating ?? null)}
      ${facts.length ? `<span class="hkl-muted">${escapeHTML(facts.join(' · '))}</span>` : ''}
    </div>
    <div class="hkl-fields">${fields}</div>
    ${clear}
    ${household ? `<span class="hkl-eyebrow">${escapeHTML(t('game.household'))}</span><div class="hkl-household">${household}</div>` : ''}
  </section>`;
}

function notesSection(ctx: ViewCtx, game: Game): string {
  const { pid, platform } = progressTarget(ctx, game);
  const tab = ctx.ui.notesTab;
  const text = tab === 'shared' ? game.shared_notes : (progressOf(game, pid, platform)?.review ?? '');
  const tabs = (['shared', 'private'] as const)
    .map((k) => `<button class="hkl-subtab${tab === k ? ' on' : ''}" data-act="notes-tab" data-value="${k}" data-k="nt-${k}" aria-pressed="${tab === k}">${escapeHTML(t(`game.notes_${k}`))}</button>`)
    .join('');
  const body = ctx.ui.editNotes
    ? `<form data-form="notes" class="hkl-notes-form"><textarea name="text" rows="6" data-k="notes-text" aria-label="${escapeHTML(t(`game.notes_${tab}`))}">${escapeHTML(text)}</textarea><div class="hkl-dlg-actions">${button(escapeHTML(t('action.cancel')), 'notes-cancel', 'text', 'type="button" data-k="notes-cancel"')}<button class="hkl-btn primary" type="submit" data-k="notes-save">${escapeHTML(t('action.save'))}</button></div></form>`
    : `${markdownBlock(text) || `<p class="hkl-muted">${escapeHTML(t('game.no_notes'))}</p>`}${button(escapeHTML(t('action.edit_notes')), 'notes-edit', 'text', 'data-k="notes-edit"')}`;
  return `<section class="hkl-card"><div class="hkl-subtabs">${tabs}</div>${body}${tab === 'private' ? `<span class="hkl-muted small">${escapeHTML(t('game.private_hint'))}</span>` : ''}</section>`;
}

/** The Game detail view. */
export function renderGame(ctx: ViewCtx, game: Game | undefined): string {
  const back = `<button class="hkl-back" data-act="back" data-k="back">${ICONS.back}${escapeHTML(t('action.back'))}</button>`;
  if (!game) {
    return `${navBar(ctx.route, navCounts(ctx))}${back}<div class="hkl-empty">${escapeHTML(t('game.gone'))}</div>`;
  }
  const copies = ctx.idx.copiesByGame.get(game.id) ?? [];
  const loans = ctx.idx.activeLoans.get(game.id) ?? [];
  const franchise = game.franchise ? link(gamesPath({ q: game.franchise }), escapeHTML(game.franchise)) : '';
  const meta = [
    game.release_date,
  ].filter(Boolean).map((x) => escapeHTML(x));
  const tags = [...game.genres, ...game.tags]
    .map((x) => `<span class="hkl-chip">${escapeHTML(x)}</span>`)
    .join('');
  const wish = game.wishlist
    ? `<div class="hkl-banner">${escapeHTML(t('game.on_wishlist', { name: ctx.idx.person.get(game.wishlist.person_id)?.name ?? '' }))}${button(escapeHTML(t('action.got_it')), 'got-it', 'tonal', `data-id="${escapeHTML(game.id)}" data-k="got-it"`)}</div>`
    : '';
  const needs = game.needs_details
    ? `<div class="hkl-banner warn">${escapeHTML(t('game.needs_details'))}${button(escapeHTML(t('action.add_details')), 'edit-game', 'tonal', 'data-k="needs-edit"')}</div>`
    : '';
  const badge = game.cover?.kind === 'custom' ? `<span class="hkl-cover-badge">${escapeHTML(t('game.custom_cover'))}</span>` : '';
  const actions = [
    button(escapeHTML(t('action.edit')), 'edit-game', 'tonal', 'data-k="edit-game"'),
    copies.some((c) => !ctx.idx.loanByCopy.has(c.id)) ? button(escapeHTML(t('action.lend')), 'lend', 'tonal', `data-game="${escapeHTML(game.id)}" data-k="lend"`) : '',
    game.wishlist ? '' : button(escapeHTML(t('action.add_to_wishlist')), 'wish-this', 'text', 'data-k="wish-this"'),
    button(escapeHTML(t('action.delete')), 'delete-game', 'danger', 'data-k="delete-game"'),
  ].join('');
  return `${navBar(ctx.route, navCounts(ctx))}
  ${back}
  <div class="hkl-detail">
    <div class="hkl-detail-cover">
      ${cover(game, 'large', badge)}
      <div class="hkl-cover-actions">${button(escapeHTML(t('action.change_cover')), 'change-cover', 'tonal', 'data-k="change-cover"')}</div>
      <input type="file" accept="image/jpeg,image/png,image/webp" data-chg="cover-file" data-k="cover-file" hidden />
    </div>
    <div class="hkl-detail-info">
      <h1>${escapeHTML(game.title)}</h1>
      ${franchise ? `<span class="hkl-byline">${franchise}</span>` : ''}
      <span class="hkl-muted">${meta.join(' · ')}</span>
      ${tags ? `<div class="hkl-chips">${tags}</div>` : ''}
      ${needs}${wish}
      <div class="hkl-boxes">${copies.map((c, i) => copyBox(ctx, c, i, copies.length)).join('')}${loans.map((l) => loanBox(ctx, l)).join('')}</div>
      ${game.summary ? `<p class="hkl-desc">${escapeHTML(game.summary)}</p>` : ''}
    </div>
  </div>
  ${progressSection(ctx, game)}
  <div class="hkl-two">${notesSection(ctx, game)}${copyDetails(ctx, copies)}</div>
  <div class="hkl-detail-actions">${actions}</div>`;
}

/** The path of the game list for a filter set. */
export function gamesPath(query: Record<string, string>): string {
  return buildPath({ view: 'games', query });
}
