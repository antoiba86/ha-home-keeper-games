// The Rooms and shelves view: the rooms list and a drawing of each unit.

import { formatMoney, t, tn } from './i18n';
import { button, href, navBar } from './markup';
import { navCounts } from './tab-games';
import type { ViewCtx } from './tab-types';
import type { Game, Unit, Shelf } from './types';
import { buildPath, escapeHTML, roomValue, shelfPath, spines } from './utils';

function gamesOnShelf(ctx: ViewCtx, shelfId: string): Game[] {
  const ids = new Set((ctx.idx.copiesByShelf.get(shelfId) ?? []).map((c) => c.game_id));
  return [...ids].map((id) => ctx.idx.game.get(id)).filter((b): b is Game => Boolean(b));
}

function roomGameCount(ctx: ViewCtx, roomId: string): number {
  const ids = new Set<string>();
  for (const copy of ctx.lib.copies) {
    if (shelfPath(ctx.idx, copy.shelf_id).room?.id === roomId) ids.add(copy.game_id);
  }
  return ids.size;
}

function shelfRow(ctx: ViewCtx, shelf: Shelf): string {
  const games = gamesOnShelf(ctx, shelf.id);
  const drawn = spines(games)
    .map(
      (s) =>
        `<a class="hkl-spine" href="${escapeHTML(href(`/games/${encodeURIComponent(s.id)}`))}" data-act="nav" data-path="/games/${escapeHTML(encodeURIComponent(s.id))}" style="width:${s.w}px;height:${s.h}px;background:${s.color}" title="${escapeHTML(s.title)}" aria-label="${escapeHTML(s.title)}"></a>`,
    )
    .join('');
  const id = escapeHTML(shelf.id);
  return `<div class="hkl-shelf" data-shelf="${id}">
    <div class="hkl-shelf-games">${drawn || `<span class="hkl-muted small">${escapeHTML(t('shelves.empty_shelf'))}</span>`}</div>
    <div class="hkl-board"></div>
    <div class="hkl-shelf-label">
      <span class="hkl-shelf-name">${escapeHTML(shelf.name)}</span>
      <span class="hkl-muted">${escapeHTML(tn('count.games', games.length))}</span>
      <span class="hkl-spacer"></span>
      <button class="hkl-link" data-act="nav" data-path="${escapeHTML(buildPath({ view: 'games', query: { shelf: shelf.id } }))}" data-k="sb-${id}">${escapeHTML(t('shelves.show_games'))}</button>
      <button class="hkl-link" data-act="nav" data-path="${escapeHTML(buildPath({ view: 'scan', query: { shelf: shelf.id } }))}" data-k="ss-${id}">${escapeHTML(t('action.scan'))}</button>
      <button class="hkl-link" data-act="edit-shelf" data-id="${id}" data-k="es-${id}">${escapeHTML(t('action.rename'))}</button>
      <button class="hkl-link danger" data-act="delete-shelf" data-id="${id}" data-k="ds-${id}">${escapeHTML(t('action.delete'))}</button>
    </div>
  </div>`;
}

function unitCard(ctx: ViewCtx, bc: Unit): string {
  const shelves = ctx.lib.shelves.filter((s) => s.unit_id === bc.id);
  const meta = [bc.note, tn('count.shelves', shelves.length)].filter(Boolean).join(' · ');
  const id = escapeHTML(bc.id);
  return `<div class="hkl-case">
    <div class="hkl-card-head">
      <h2>${escapeHTML(bc.name)}</h2><span class="hkl-muted">${escapeHTML(meta)}</span>
      <span class="hkl-spacer"></span>
      ${button(escapeHTML(t('action.add_shelf')), 'add-shelf', 'tonal', `data-id="${id}" data-k="as-${id}"`)}
      <button class="hkl-link" data-act="edit-unit" data-id="${id}" data-k="eb-${id}">${escapeHTML(t('action.edit'))}</button>
      <button class="hkl-link danger" data-act="delete-unit" data-id="${id}" data-k="db-${id}">${escapeHTML(t('action.delete'))}</button>
    </div>
    <div class="hkl-case-body">${shelves.map((s) => shelfRow(ctx, s)).join('') || `<span class="hkl-muted">${escapeHTML(t('shelves.no_shelves'))}</span>`}</div>
  </div>`;
}

/** The Rooms and shelves view. */
export function renderShelves(ctx: ViewCtx): string {
  const rooms = ctx.lib.rooms;
  const room = rooms.find((r) => r.id === ctx.route.id) ?? rooms[0];
  const list = rooms
    .map((r) => {
      const on = r.id === room?.id;
      return `<button class="hkl-roombtn${on ? ' on' : ''}" data-act="nav" data-path="/shelves/${escapeHTML(encodeURIComponent(r.id))}" data-k="room-${escapeHTML(r.id)}"${on ? ' aria-current="page"' : ''}><span>${escapeHTML(r.name)}</span><span class="hkl-muted">${roomGameCount(ctx, r.id)}</span></button>`;
    })
    .join('');
  const aside = `<section class="hkl-rooms" aria-label="${escapeHTML(t('shelves.rooms'))}">
    <span class="hkl-eyebrow">${escapeHTML(t('shelves.rooms'))}</span>
    ${list}
    ${button(escapeHTML(t('action.add_room')), 'add-room', 'text', 'data-k="add-room-2"')}
    <span class="hkl-muted small">${escapeHTML(t('shelves.area_hint'))}</span>
  </section>`;
  const loose = ctx.idx.copiesByShelf.get('') ?? [];
  const banner = loose.length
    ? `<div class="hkl-banner"><span>${escapeHTML(tn('shelves.no_shelf_count', loose.length))}</span><span class="hkl-spacer"></span>${button(escapeHTML(t('action.set_shelf')), 'set-shelf', 'tonal', 'data-k="set-shelf"')}</div>`
    : '';
  if (!room) {
    return `${navBar(ctx.route, navCounts(ctx))}<div class="hkl-places">${aside}<section class="hkl-room"><div class="hkl-empty">${escapeHTML(t('shelves.no_rooms'))}</div>${banner}</section></div>`;
  }
  const cases = ctx.lib.units.filter((c) => c.room_id === room.id);
  const value = roomValue(ctx.lib, ctx.idx, room.id);
  const area = room.area_id ? ctx.areaName(room.area_id) : '';
  const meta = [
    tn('count.units', cases.length),
    tn('count.games', roomGameCount(ctx, room.id)),
    value ? t('shelves.value', { value: formatMoney(value, ctx.lib.currency) }) : '',
    area ? t('shelves.area', { area }) : '',
  ].filter(Boolean).join(' · ');
  const rid = escapeHTML(room.id);
  return `${navBar(ctx.route, navCounts(ctx))}
  <div class="hkl-places">
    ${aside}
    <section class="hkl-room">
      <div class="hkl-card-head">
        <h1>${escapeHTML(room.name)}</h1><span class="hkl-muted">${escapeHTML(meta)}</span>
        <span class="hkl-spacer"></span>
        <span class="hkl-head-actions">
          ${button(escapeHTML(t('action.add_unit')), 'add-unit', 'tonal', `data-id="${rid}" data-k="ab-${rid}"`)}
          <button class="hkl-link" data-act="edit-room" data-id="${rid}" data-k="er-${rid}">${escapeHTML(t('action.edit'))}</button>
          <button class="hkl-link danger" data-act="delete-room" data-id="${rid}" data-k="dr-${rid}">${escapeHTML(t('action.delete'))}</button>
        </span>
      </div>
      ${cases.map((c) => unitCard(ctx, c)).join('') || `<div class="hkl-empty">${escapeHTML(t('shelves.no_units'))}</div>`}
      ${banner}
    </section>
  </div>`;
}
