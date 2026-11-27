// The dialogs of the tab. Each dialog is a form; `tab.ts` reads the form data on
// submit and calls the websocket command. The dialog layer is separate from the
// view, so a data push does not clear what the user types.

import { t } from './i18n';
import { formatOptions, ICONS, options, personOptions, platformOptions, shelfOptions } from './markup';
import type { ViewCtx } from './tab-types';
import type { Candidate, Copy } from './types';
import { escapeHTML, locationLabel, PLATFORMS, platformLabel } from './utils';

export type Dialog =
  | { kind: 'add-game' }
  | { kind: 'edit-game'; gameId: string }
  /** Search IGDB and give the game another IGDB game. `results` is null before the first reply. */
  | {
      kind: 'igdb-game';
      gameId: string;
      query: string;
      platform: string;
      results: Candidate[] | null;
      searching: boolean;
      picked: number | null;
    }
  | { kind: 'copy'; gameId: string; copyId: string | null }
  | { kind: 'move'; copyId: string }
  | { kind: 'set-shelf' }
  /** No game had the scanned barcode: ask for the title before the next scan. */
  | { kind: 'scan-title'; key: number; gameId: string; copyId: string | null; barcode: string }
  | { kind: 'lend'; gameId: string | null }
  | { kind: 'borrow' }
  | { kind: 'log-session'; personId: string | null }
  | { kind: 'wish-add'; gameId: string | null }
  | { kind: 'got-it'; gameId: string }
  | { kind: 'room'; roomId: string | null }
  | { kind: 'unit'; roomId: string; unitId: string | null }
  | { kind: 'shelf'; unitId: string; shelfId: string | null }
  | {
      kind: 'confirm';
      title: string;
      text: string;
      label: string;
      command: string;
      fields: Record<string, unknown>;
      after?: string;
    };

export interface DialogState {
  dialog: Dialog;
  error: string;
  busy: boolean;
}

const field = (label: string, input: string, cls = '') =>
  `<label class="hkl-field${cls ? ` ${cls}` : ''}">${escapeHTML(label)}${input}</label>`;

const text = (name: string, value: unknown = '', attrs = '') =>
  `<input name="${name}" value="${escapeHTML(value ?? '')}" data-k="d-${name}" ${attrs} />`;

const check = (name: string, label: string, on: boolean, hint = '') =>
  `<label class="hkl-check"><input type="checkbox" name="${name}" data-k="d-${name}"${on ? ' checked' : ''} /><span>${escapeHTML(label)}${hint ? `<span class="hkl-muted small block">${escapeHTML(hint)}</span>` : ''}</span></label>`;

function copyFields(ctx: ViewCtx, copy: Copy | null): string {
  const conditions: Array<[string, string]> = [['', t('common.none')], ...['new', 'fine', 'good', 'fair', 'poor'].map((c): [string, string] => [c, t(`condition.${c}`)])];
  return `<div class="hkl-fields">
    ${field(t('copy.shelf'), `<select name="shelf_id" data-k="d-shelf">${shelfOptions(ctx.lib, copy?.shelf_id ?? null)}</select>`)}
    ${field(t('copy.platform'), `<select name="platform" data-k="d-platform">${platformOptions(copy?.platform ?? 'other')}</select>`)}
    ${field(t('copy.format'), `<select name="format" data-k="d-format">${formatOptions(copy?.format ?? 'physical')}</select>`)}
    ${field(t('copy.storefront'), text('storefront', copy?.storefront))}
    ${field(t('copy.region'), text('region', copy?.region), 'small')}
    ${field(t('copy.edition'), text('edition', copy?.edition))}
    ${field(t('game.barcode_label'), text('barcode', copy?.barcode ?? '', 'autocomplete="off"'))}
    ${field(t('copy.condition'), `<select name="condition" data-k="d-condition">${options(conditions, copy?.condition ?? '')}</select>`)}
    ${field(t('copy.acquired'), text('acquired', copy?.acquired, 'type="date"'))}
    ${field(t('copy.acquired_from'), text('acquired_from', copy?.acquired_from))}
    ${field(t('copy.price'), text('price', copy?.price, 'inputmode="decimal"'), 'small')}
    ${field(t('copy.value'), text('value', copy?.value, 'inputmode="decimal"'), 'small')}
  </div>
  ${check('steelbook', t('copy.steelbook'), Boolean(copy?.steelbook))}
  ${field(t('copy.note'), text('note', copy?.note), 'wide')}`;
}

interface DialogBody {
  title: string;
  html: string;
  submit: string;
  danger?: boolean;
  noCancel?: boolean;
  /** The label of the cancel button, if it is not "Cancel". */
  cancel?: string;
  /** A sheet has no close button. The user must submit it or remove the scan. */
  sheet?: boolean;
}

/** The title sheet of a scan with no match. Only the title is required. */
function scanTitleBody(ctx: ViewCtx, d: Extract<Dialog, { kind: 'scan-title' }>): DialogBody {
  const copy = d.copyId ? ctx.idx.copy.get(d.copyId) : undefined;
  return {
    title: t('scan.no_match'),
    submit: t('scan.miss_save'),
    sheet: true,
    html: `<div class="hkl-miss-head"><span class="hkl-cover hkl-cover-thumb miss" aria-hidden="true"></span><span class="hkl-row-main"><span class="hkl-muted" data-k="d-barcode">${escapeHTML(t('game.barcode', { code: d.barcode }))}</span><span class="hkl-muted">${escapeHTML(t('scan.miss_hint'))}</span></span></div>
      ${field(t('game.title'), text('title', '', `required autocomplete="off" data-input="miss-title" placeholder="${escapeHTML(t('scan.miss_placeholder'))}"`), 'wide')}
      <details class="hkl-miss-more" data-k="d-more"><summary data-k="d-more-toggle">${escapeHTML(t('scan.miss_more'))}</summary>
        <div class="hkl-fields">
          ${field(t('game.franchise'), text('franchise'), 'wide')}
          ${field(t('game.genres'), text('genres'), 'wide')}
          ${field(t('game.release_date'), text('release_date'), 'small')}
          ${field(t('copy.platform'), `<select name="platform" data-k="d-platform">${platformOptions(copy?.platform ?? 'other')}</select>`)}
          ${field(t('copy.format'), `<select name="format" data-k="d-format">${formatOptions(copy?.format ?? 'physical')}</select>`)}
          <label class="hkl-btn outline hkl-miss-cover">${ICONS.camera}<input class="hkl-sr" type="file" name="cover" accept="image/jpeg,image/png,image/webp" capture="environment" data-chg="miss-cover" data-k="d-cover" /><span data-k="d-cover-name">${escapeHTML(t('scan.miss_cover'))}</span></label>
        </div>
      </details>`,
  };
}

type IgdbDialog = Extract<Dialog, { kind: 'igdb-game' }>;

/** True when another game of the library has this IGDB game. */
export const takenByOther = (c: Candidate, gameId: string): boolean => c.in_library !== null && c.in_library !== gameId;

function candidateRow(c: Candidate, d: IgdbDialog): string {
  const other = takenByOther(c, d.gameId);
  const meta = [c.release_year === null ? '' : String(c.release_year), ...c.platforms.map(platformLabel)].filter(Boolean).join(' · ');
  const img = c.cover_url
    ? `<img class="hkl-igdb-cover" src="${escapeHTML(c.cover_url)}" alt="" loading="lazy" referrerpolicy="no-referrer" />`
    : '<span class="hkl-igdb-cover none" aria-hidden="true"></span>';
  const mark = other ? t('igdb.in_library') : c.in_library === d.gameId ? t('igdb.this_game') : '';
  const id = escapeHTML(String(c.igdb_id));
  return `<label class="hkl-igdb-row${other ? ' off' : ''}" data-k="d-igdb-row-${id}"><input type="radio" name="igdb_id" value="${id}"${d.picked === c.igdb_id ? ' checked' : ''}${other ? ' disabled' : ''} />${img}<span class="hkl-igdb-text"><strong>${escapeHTML(c.title)}</strong>${meta ? `<span class="hkl-muted small">${escapeHTML(meta)}</span>` : ''}</span>${mark ? `<span class="hkl-pill">${escapeHTML(mark)}</span>` : ''}</label>`;
}

function igdbBody(ctx: ViewCtx, d: IgdbDialog): DialogBody {
  const platforms: Array<[string, string]> = [
    ['', t('igdb.any_platform')],
    ...PLATFORMS.filter((p) => p !== 'other').map((p): [string, string] => [p, platformLabel(p)]),
  ];
  const status = (text: string) => `<p class="hkl-muted" data-k="d-igdb-status">${escapeHTML(text)}</p>`;
  const list = d.searching
    ? status(t('igdb.searching'))
    : d.results?.length === 0
      ? status(t('igdb.no_results'))
      : (d.results ?? []).map((c) => candidateRow(c, d)).join('');
  const upload = ctx.idx.game.get(d.gameId)?.cover?.kind === 'custom' ? ` ${t('igdb.upload_stays')}` : '';
  return {
    title: t('igdb.change'),
    submit: t('igdb.use'),
    html: `<div class="hkl-igdb-search">
        ${field(t('igdb.search'), `<input name="igdb_query" value="${escapeHTML(d.query)}" data-k="d-igdb-query" data-input="igdb-query" autocomplete="off" enterkeyhint="search" />`, 'wide')}
        ${field(t('copy.platform'), `<select name="igdb_platform" data-k="d-igdb-platform">${options(platforms, d.platform)}</select>`)}
        <button type="button" class="hkl-btn outline" data-act="igdb-search" data-k="d-igdb-search"${d.searching ? ' disabled' : ''}>${escapeHTML(t('igdb.search_action'))}</button>
      </div>
      <div class="hkl-igdb-list" role="radiogroup" aria-label="${escapeHTML(t('igdb.results'))}" aria-busy="${d.searching}">${list}</div>
      <p class="hkl-muted small" data-k="d-igdb-note">${escapeHTML(t('igdb.what_changes') + upload)}</p>`,
  };
}

function body(ctx: ViewCtx, d: Dialog, areas: Array<[string, string]>): DialogBody {
  switch (d.kind) {
    case 'add-game':
      return {
        title: t('dialog.add_game'),
        submit: t('action.add'),
        html: `${field(t('dialog.barcode_or_title'), text('query', '', 'required autocomplete="off"'), 'wide')}
          ${check('own', t('dialog.own_copy'), true)}
          <div class="hkl-fields">
            ${field(t('copy.shelf'), `<select name="shelf_id" data-k="d-shelf">${shelfOptions(ctx.lib, null)}</select>`)}
            ${field(t('copy.platform'), `<select name="platform" data-k="d-platform">${platformOptions('other')}</select>`)}
            ${field(t('copy.format'), `<select name="format" data-k="d-format">${formatOptions('physical')}</select>`)}
          </div>`,
      };
    case 'scan-title':
      return scanTitleBody(ctx, d);
    case 'igdb-game':
      return igdbBody(ctx, d);
    case 'edit-game': {
      const b = ctx.idx.game.get(d.gameId);
      return {
        title: t('dialog.edit_game'),
        submit: t('action.save'),
        html: `<div class="hkl-fields">
          ${field(t('game.title'), text('title', b?.title, 'required'), 'wide')}
          ${field(t('game.franchise'), text('franchise', b?.franchise ?? ''), 'wide')}
          ${field(t('game.genres'), text('genres', b?.genres.join(', ')), 'wide')}
          ${field(t('game.release_date'), text('release_date', b?.release_date), 'small')}
          ${field(t('game.tags'), text('tags', b?.tags.join(', ')), 'wide')}
        </div>
        ${field(t('game.summary'), `<textarea name="summary" rows="4" data-k="d-summary">${escapeHTML(b?.summary ?? '')}</textarea>`, 'wide')}
        ${b?.needs_details ? check('details_done', t('dialog.details_done'), true) : ''}`,
      };
    }
    case 'copy': {
      const copy = d.copyId ? (ctx.idx.copy.get(d.copyId) ?? null) : null;
      return { title: copy ? t('dialog.edit_copy') : t('dialog.add_copy'), submit: t('action.save'), html: copyFields(ctx, copy) };
    }
    case 'move': {
      const copy = ctx.idx.copy.get(d.copyId);
      const game = copy ? ctx.idx.game.get(copy.game_id) : undefined;
      return {
        title: t('dialog.move'),
        submit: t('action.move'),
        html: `<p class="hkl-muted">${escapeHTML(game?.title ?? '')}</p>${field(t('copy.shelf'), `<select name="shelf_id" data-k="d-shelf">${shelfOptions(ctx.lib, copy?.shelf_id ?? null)}</select>`, 'wide')}`,
      };
    }
    case 'set-shelf': {
      const loose = ctx.idx.copiesByShelf.get('') ?? [];
      const rows = loose
        .map((c) => `<label class="hkl-check"><input type="checkbox" name="copy" value="${escapeHTML(c.id)}" checked />${escapeHTML(ctx.idx.game.get(c.game_id)?.title ?? '')} · ${escapeHTML(t(`format.kind_${c.format}`))}</label>`)
        .join('');
      return {
        title: t('dialog.set_shelf'),
        submit: t('action.move'),
        html: `${field(t('copy.shelf'), `<select name="shelf_id" data-k="d-shelf">${shelfOptions(ctx.lib, ctx.lib.shelves[0]?.id ?? null, false)}</select>`, 'wide')}<div class="hkl-checklist">${rows}</div>`,
      };
    }
    case 'lend': {
      const avail = ctx.lib.copies
        .filter((c) => !ctx.idx.loanByCopy.has(c.id) && c.format !== 'digital')
        .filter((c) => !d.gameId || c.game_id === d.gameId)
        .map((c): [string, string] => [c.id, `${ctx.idx.game.get(c.game_id)?.title ?? ''} · ${c.shelf_id ? locationLabel(ctx.idx, c.shelf_id) : t('common.no_shelf')}`])
        .sort((a, b) => a[1].localeCompare(b[1]));
      return {
        title: t('dialog.lend'),
        submit: t('action.lend'),
        html: `${field(t('loan.copy'), `<select name="copy_id" required data-k="d-copy">${options(avail, avail[0]?.[0] ?? '')}</select>`, 'wide')}
          <div class="hkl-fields">
            ${field(t('loan.borrower'), text('party', '', 'required'))}
            ${field(t('loan.started'), text('started', ctx.today, 'type="date"'), 'small')}
            ${field(t('loan.return_by'), text('due', '', 'type="date"'), 'small')}
          </div>
          ${check('add_task', t('loan.add_task'), true, t('loan.add_task_hint'))}
          ${field(t('copy.note'), text('note', '', `placeholder="${escapeHTML(t('common.optional'))}"`), 'wide')}`,
      };
    }
    case 'log-session': {
      const games = [...ctx.lib.games]
        .sort((a, b) => a.title.localeCompare(b.title))
        .map((g): [string, string] => [g.id, g.title]);
      const platforms: Array<[string, string]> = [['', t('playlog.platform_auto')], ...PLATFORMS.map((p): [string, string] => [p, platformLabel(p)])];
      return {
        title: t('playlog.log_session'),
        submit: t('action.add'),
        html: `${field(t('common.person'), `<select name="person_id" data-k="d-person">${personOptions(ctx.lib, d.personId)}</select>`)}
          ${field(t('playlog.game'), `<select name="game_id" required data-k="d-game">${options(games, games[0]?.[0] ?? '')}</select>`, 'wide')}
          <div class="hkl-fields">
            ${field(t('game.platform'), `<select name="platform" data-k="d-platform">${options(platforms, '')}</select>`)}
            ${field(t('playlog.minutes'), text('minutes', '', 'type="number" min="1" max="1440" required inputmode="numeric"'), 'small')}
            ${field(t('playlog.date'), text('date', ctx.today, 'type="date"'), 'small')}
          </div>`,
      };
    }
    case 'borrow':
      return {
        title: t('dialog.borrow'),
        submit: t('action.add'),
        html: `${field(t('dialog.barcode_or_title'), text('query', '', 'required autocomplete="off"'), 'wide')}
          <div class="hkl-fields">
            ${field(t('loan.lender'), text('party', '', 'required'))}
            ${field(t('common.person'), `<select name="person_id" data-k="d-person">${personOptions(ctx.lib, ctx.me)}</select>`)}
            ${field(t('copy.format'), `<select name="format" data-k="d-format">${formatOptions('physical')}</select>`)}
            ${field(t('loan.started'), text('started', ctx.today, 'type="date"'), 'small')}
            ${field(t('loan.due'), text('due', '', 'type="date"'), 'small')}
          </div>
          ${check('add_task', t('loan.add_task'), true, t('loan.add_task_hint'))}
          ${field(t('copy.note'), text('note', '', `placeholder="${escapeHTML(t('common.optional'))}"`), 'wide')}
          <p class="hkl-muted small">${escapeHTML(t('loan.borrow_hint'))}</p>`,
      };
    case 'wish-add': {
      const b = d.gameId ? ctx.idx.game.get(d.gameId) : undefined;
      return {
        title: t('dialog.wish_add'),
        submit: t('action.add'),
        html: `${b ? `<p><b>${escapeHTML(b.title)}</b></p>` : field(t('dialog.barcode_or_title'), text('query', '', 'required autocomplete="off"'), 'wide')}
          ${field(t('common.person'), `<select name="person_id" data-k="d-person">${personOptions(ctx.lib, ctx.me)}</select>`, 'wide')}
          ${check('buy', t('wishlist.buy'), false, t('wishlist.buy_hint'))}`,
      };
    }
    case 'got-it': {
      const b = ctx.idx.game.get(d.gameId);
      return {
        title: t('dialog.got_it'),
        submit: t('action.save'),
        html: `<p><b>${escapeHTML(b?.title ?? '')}</b></p><div class="hkl-fields">
          ${field(t('copy.shelf'), `<select name="shelf_id" data-k="d-shelf">${shelfOptions(ctx.lib, null)}</select>`)}
          ${field(t('copy.platform'), `<select name="platform" data-k="d-platform">${platformOptions('other')}</select>`)}
            ${field(t('copy.format'), `<select name="format" data-k="d-format">${formatOptions('physical')}</select>`)}
        </div>`,
      };
    }
    case 'room': {
      const r = d.roomId ? ctx.idx.room.get(d.roomId) : undefined;
      return {
        title: r ? t('dialog.edit_room') : t('dialog.add_room'),
        submit: r ? t('action.save') : t('action.add'),
        html: `${field(t('dialog.name'), text('name', r?.name, 'required'), 'wide')}
          ${field(t('dialog.area'), `<select name="area_id" data-k="d-area">${options([['', t('common.none')], ...areas], r?.area_id ?? '')}</select>`, 'wide')}
          <p class="hkl-muted small">${escapeHTML(t('shelves.area_hint'))}</p>`,
      };
    }
    case 'unit': {
      const c = d.unitId ? ctx.idx.unit.get(d.unitId) : undefined;
      return {
        title: c ? t('dialog.edit_unit') : t('dialog.add_unit'),
        submit: c ? t('action.save') : t('action.add'),
        html: `${field(t('dialog.name'), text('name', c?.name, 'required'), 'wide')}${field(t('copy.note'), text('note', c?.note), 'wide')}
          ${c ? '' : field(t('dialog.shelf_count'), text('shelves', 4, 'type="number" min="0" max="20"'), 'small')}`,
      };
    }
    case 'shelf': {
      const s = d.shelfId ? ctx.idx.shelf.get(d.shelfId) : undefined;
      const count = ctx.lib.shelves.filter((x) => x.unit_id === d.unitId).length;
      return {
        title: s ? t('dialog.edit_shelf') : t('dialog.add_shelf'),
        submit: s ? t('action.save') : t('action.add'),
        html: field(t('dialog.name'), text('name', s?.name ?? t('dialog.shelf_default', { n: count + 1 }), 'required'), 'wide'),
      };
    }
    case 'confirm':
      return { title: d.title, submit: d.label, html: `<p>${escapeHTML(d.text)}</p>`, danger: true };
  }
}

/** The dialog layer markup. */
export function renderDialog(ctx: ViewCtx, state: DialogState, areas: Array<[string, string]>): string {
  const { title, html, submit, danger, noCancel, cancel: cancelLabel, sheet } = body(ctx, state.dialog, areas);
  const close = sheet ? '' : `<button type="button" class="hkl-iconbtn" data-act="dialog-close" data-k="d-x" aria-label="${escapeHTML(t('action.close'))}">${ICONS.close}</button>`;
  const cancel = sheet
    ? `<button type="button" class="hkl-btn text" data-act="scan-miss-remove" data-k="d-remove">${escapeHTML(t('scan.miss_remove'))}</button>`
    : noCancel ? '' : `<button type="button" class="hkl-btn text" data-act="dialog-close" data-k="d-cancel">${escapeHTML(cancelLabel ?? t('action.cancel'))}</button>`;
  // A sheet starts with an empty title, so its submit is off until the user types one.
  const off = state.busy || sheet;
  return `<div class="hkl-scrim"${sheet ? '' : ' data-act="dialog-scrim"'}>
    <form class="hkl-dialog${sheet ? ' sheet' : ''}" data-form="dialog" role="dialog" aria-modal="true" aria-labelledby="hkl-dlg-title" novalidate>
      <div class="hkl-dlg-head"><h2 id="hkl-dlg-title">${escapeHTML(title)}</h2>${close}</div>
      <div class="hkl-dlg-body">${html}</div>
      ${state.error ? `<div class="hkl-error" role="alert">${escapeHTML(state.error)}</div>` : ''}
      <div class="hkl-dlg-actions">
        ${cancel}
        <button type="submit" class="hkl-btn ${danger ? 'danger-primary' : 'primary'}" data-k="d-submit"${off ? ' disabled' : ''}>${escapeHTML(submit)}</button>
      </div>
    </form>
  </div>`;
}
