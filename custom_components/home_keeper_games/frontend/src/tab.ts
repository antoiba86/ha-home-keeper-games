// The `home-keeper-games-tab` element. The Home Keeper panel loads it at
// `/home-keeper/games/...` and gives it `hass`, `narrow`, `route` and `host`
// (host API v1, build spec section 10).
//
// The URL is the source of truth. The `route` setter is the only place that
// changes the view. Every navigation goes through `host.navigate`. The view is
// 1 HTML string per render, and 1 delegated listener per event type reads the
// `data-act`, `data-chg`, `data-input` and `data-form` attributes.

import { errorText, LibraryApi, MAX_COVER_BYTES, MAX_IMPORT_BYTES, type Fields } from './api';
import { renderKeepFocus } from './dom';
import { setLanguage, t, tn } from './i18n';
import { ensureMarkdown, wireMarkdown } from './markdown';
import { wireCovers } from './markup';
import { camLogLines, logCam, Scanner } from './scanner';
import { STYLES } from './styles';
import { gamesPath, progressTarget, renderGame, renderGames } from './tab-games';
import { renderDialog, takenByOther, type Dialog, type DialogState } from './tab-dialogs';
import { renderImport } from './tab-import';
import { playLogPerson, renderLoans, renderPlayLog, renderSettings, renderWishlist } from './tab-lists';
import { cameraBlocked, isBorrowedMode, renderScan, routeShelf } from './tab-scan';
import { renderShelves } from './tab-shelves';
import type { ImportState, ScanEntry, UiState, ViewCtx } from './tab-types';
import type { Candidate, Game, HomeAssistant, ImportSummary, Lib, Platform, PlayStatus, RawState, ScanResult, Session, TabHost } from './types';
import {
  buildIndex,
  buildPath,
  csvRowCount,
  debounce,
  escapeHTML,
  intOrNull,
  makeCodeGate,
  nextMiss,
  normalizeBarcode,
  normalizeState,
  numberOrNull,
  parseRoute,
  progressOf,
  readFilters,
  retailBarcode,
  shelfPath,
  splitList,
  todayISO,
  withQuery,
  type Index,
  type TabRoute,
} from './utils';
import { PANEL_VERSION } from 'panel-version';

const PAGE = 240;
/** How long the camera picture can stop before the tab shows the restart button. */
const STALL_MS = 800;
/** Tab elements made on this page. The debug view shows if Home Keeper makes a new one. */
let tabCount = 0;

function freshImport(personId: string | null): ImportState {
  return {
    personId,
    shelfId: '',
    fileName: '',
    content: '',
    rowCount: 0,
    importReview: true,
    replaceProgress: false,
    summary: null,
    busy: false,
    error: '',
    done: false,
  };
}

function freshUi(): UiState {
  return {
    limit: PAGE,
    notesTab: 'shared',
    editNotes: false,
    progressPerson: null,
    progressPlatform: null,
    scan: {
      method: 'camera',
      roomId: null,
      platform: 'other',
      format: 'physical',
      results: [],
      manualOpen: false,
      markRead: false,
      cameraError: '',
      stalled: false,
      torch: null,
      party: '',
      personId: null,
      due: '',
      addTask: true,
    },
    import: freshImport(null),
    todoEntities: [],
    exportPerson: '',
    playlog: { person: null, sessions: null, error: '', open: {} },
  };
}

/** The id of a created object from a command reply (`{id}` or `{<noun>: {id}}`). */
export function replyId(res: unknown, noun: string): string | null {
  const r = res as Record<string, unknown> | null;
  if (!r || typeof r !== 'object') return null;
  if (typeof r.id === 'string') return r.id;
  const inner = r[noun] as { id?: unknown } | undefined;
  return inner && typeof inner.id === 'string' ? inner.id : null;
}

export class HomeKeeperGamesTab extends HTMLElement {
  private _hass?: HomeAssistant;
  private _api?: LibraryApi;
  private _host: TabHost | null = null;
  private _route: TabRoute = parseRoute('');
  private _lib: Lib | null = null;
  private _idx: Index | null = null;
  private _error = '';
  private _lang = '';
  private _unsub?: () => void | Promise<void>;
  private _subscribing = false;
  private _refreshing: Promise<void> | null = null;
  private _again = false;
  private _dryRunSeq = 0;
  private _ui: UiState = freshUi();
  private _dialog: DialogState | null = null;
  private _scanner: Scanner | null = null;
  private _stopTimer: ReturnType<typeof setTimeout> | undefined;
  private _stallTimer: ReturnType<typeof setTimeout> | undefined;
  private _debugTimer: ReturnType<typeof setInterval> | undefined;
  private readonly _tabId = ++tabCount;
  private _connects = 0;
  private _renders = 0;
  private _gate = makeCodeGate(3000);
  private _scanKey = 0;
  private _gamesPath = '/games';
  private _todoLoaded = false;
  private readonly _root: ShadowRoot;
  private readonly _main: HTMLElement;
  private readonly _dlg: HTMLElement;
  private readonly _search = debounce((q: string) => this._setFilter('q', q), 250);

  constructor() {
    super();
    this._root = this.attachShadow({ mode: 'open' });
    this._root.innerHTML = `<style>${STYLES}</style><div class="hkl-root" id="main"></div><div id="dlg"></div>`;
    this._main = this._root.getElementById('main')!;
    this._dlg = this._root.getElementById('dlg')!;
    this._root.addEventListener('click', (ev) => this._onClick(ev as MouseEvent));
    this._root.addEventListener('change', (ev) => void this._onChange(ev));
    this._root.addEventListener('input', (ev) => this._onInput(ev));
    this._root.addEventListener('submit', (ev) => this._onSubmit(ev as SubmitEvent));
    this._root.addEventListener('keydown', (ev) => this._onKey(ev as KeyboardEvent));
    logCam(`tab ${this._tabId} made`);
  }

  // ── Host properties ────────────────────────────────────────────────────────

  set hass(hass: HomeAssistant) {
    const first = !this._hass;
    this._hass = hass;
    if (this._api) this._api.setHass(hass);
    else this._api = new LibraryApi(hass);
    const lang = hass.locale?.language || hass.language || 'en';
    if (lang !== this._lang) {
      this._lang = lang;
      setLanguage(lang);
      if (!first) this._render();
    }
    if (first) void this._start();
  }
  get hass(): HomeAssistant | undefined {
    return this._hass;
  }

  set narrow(_value: boolean) {
    // CSS picks the layout. The tab accepts `narrow` for the host API only.
  }

  set host(host: TabHost | null) {
    this._host = host;
  }
  get host(): TabHost | null {
    return this._host;
  }

  set route(route: { path: string }) {
    const prev = this._route;
    const search = route.path.includes('?') ? '' : (globalThis.location?.search ?? '');
    this._route = parseRoute(route.path, search);
    if (prev.view === 'scan' || this._route.view === 'scan') logCam(`tab ${this._tabId} route ${route.path}`);
    if (this._route.view === 'games') this._gamesPath = buildPath(this._route);
    if (prev.view !== this._route.view || prev.id !== this._route.id) {
      this._ui.editNotes = false;
      this._ui.limit = PAGE;
      if (this._route.view === 'import' && prev.view !== 'import') this._ui.import = freshImport(this._lib?.me.person_id ?? null);
    }
    if (prev.view === 'game' && prev.id !== this._route.id) {
      this._ui.progressPerson = null;
      this._ui.progressPlatform = null;
    }
    // The title sheet belongs to the scan. If the user leaves, the game keeps its barcode as the title.
    if (this._route.view !== 'scan' && this._sheetOpen()) this._closeDialog();
    this._syncScanner();
    if (this._route.view === 'settings') void this._loadTodo();
    if (this._route.view === 'playlog') void this._loadSessions();
    this._render();
  }
  get route(): { path: string } {
    return { path: buildPath(this._route) };
  }

  connectedCallback(): void {
    if (this._hass && !this._unsub && !this._subscribing) void this._subscribe();
    // Home Keeper redraws its panel when the data changes. The redraw moves this
    // tab out of the page and back in. Keep the camera, or start it again.
    this._connects++;
    if (this._scanner) logCam(`tab ${this._tabId} connected`);
    clearTimeout(this._stopTimer);
    this._stopTimer = undefined;
    void this._scanner?.resume();
    this._syncScanner();
  }

  disconnectedCallback(): void {
    void this._unsub?.();
    this._unsub = undefined;
    this._search.cancel();
    // Stop the camera only if the tab does not come back at once.
    if (this._scanner) logCam(`tab ${this._tabId} disconnected`);
    clearTimeout(this._stopTimer);
    this._stopTimer = setTimeout(() => {
      this._stopTimer = undefined;
      if (this.isConnected) return;
      this._stopScanner();
      clearInterval(this._debugTimer);
      this._debugTimer = undefined;
    }, 0);
  }

  // ── Data ───────────────────────────────────────────────────────────────────

  private async _start(): Promise<void> {
    this._render();
    void ensureMarkdown().then((ok) => ok && this._render());
    await this._refresh();
    if (this._route.view === 'settings') void this._loadTodo();
    await this._subscribe();
  }

  private async _subscribe(): Promise<void> {
    if (!this._api || this._unsub || this._subscribing) return;
    this._subscribing = true;
    try {
      this._unsub = await this._api.subscribe(() => void this._refresh());
      // The tab can leave the page while the subscription starts.
      if (!this.isConnected) {
        void this._unsub();
        this._unsub = undefined;
      }
    } catch (err) {
      this._error = errorText(err);
    } finally {
      this._subscribing = false;
    }
  }

  /** Fetch `get_state`. Calls during a fetch run 1 more fetch after it. */
  private _refresh(): Promise<void> {
    if (this._refreshing) {
      this._again = true;
      return this._refreshing;
    }
    this._refreshing = (async () => {
      do {
        this._again = false;
        try {
          this._setState(await this._api!.getState());
          this._error = '';
          if (this._route.view === 'playlog') void this._loadSessions(true);
        } catch (err) {
          this._error = errorText(err);
        }
        this._render();
      } while (this._again);
    })().finally(() => {
      this._refreshing = null;
    });
    return this._refreshing;
  }

  private _setState(raw: RawState): void {
    this._lib = normalizeState(raw);
    this._idx = buildIndex(this._lib);
    if (!this._ui.import.personId) this._ui.import.personId = this._lib.me.person_id;
  }

  private async _loadTodo(): Promise<void> {
    if (this._todoLoaded || !this._api) return;
    this._todoLoaded = true;
    try {
      this._ui.todoEntities = await this._api.listTodoEntities();
      this._render();
    } catch {
      this._todoLoaded = false;
    }
  }

  /**
   * Read the sessions of the person of the play log with `list_sessions`. The
   * state has no sessions, so the view reads them again after each change.
   */
  private async _loadSessions(force = false): Promise<void> {
    const ctx = this._ctx();
    if (!ctx || !this._api) return;
    const pid = playLogPerson(ctx);
    const state = this._ui.playlog;
    if (!force && state.person === pid && (state.sessions !== null || state.error)) return;
    if (state.person !== pid) state.open = {};
    state.person = pid;
    if (!pid) {
      state.sessions = [];
      return;
    }
    try {
      const reply = await this._api.call<{ sessions: Session[] }>('list_sessions', { person_id: pid, limit: 500 });
      if (this._ui.playlog.person !== pid) return;
      state.sessions = reply.sessions ?? [];
      state.error = '';
    } catch (err) {
      state.sessions = [];
      state.error = errorText(err);
    }
    this._render();
  }

  /** Run a command, show a toast, then fetch the state. Returns true if the command worked. */
  private async _run(command: string, fields: Fields, okText = ''): Promise<boolean> {
    try {
      await this._api!.call(command, fields);
      if (okText) this._toast(okText);
      void this._refresh();
      return true;
    } catch (err) {
      this._toast(errorText(err));
      // Show the stored values again, not the change that failed.
      this._render();
      return false;
    }
  }

  private _toast(text: string): void {
    if (this._host) this._host.showToast(text);
    else this.dispatchEvent(new CustomEvent('hass-notification', { detail: { message: text }, bubbles: true, composed: true }));
  }

  // ── Navigation ─────────────────────────────────────────────────────────────

  private _go(path: string, replace = false): void {
    if (this._host) this._host.navigate(path, { replace });
    else this.route = { path };
  }

  private _setFilter(key: string, value: string): void {
    let query = withQuery(this._route.query, key, value);
    if (key === 'room' && value && this._idx && query.shelf && query.shelf !== 'none') {
      if (shelfPath(this._idx, query.shelf).room?.id !== value) query = withQuery(query, 'shelf', '');
    }
    this._go(gamesPath(query), true);
  }

  // ── Render ─────────────────────────────────────────────────────────────────

  private _ctx(): ViewCtx | null {
    if (!this._lib || !this._idx) return null;
    const states = this._hass?.states ?? {};
    return {
      lib: this._lib,
      idx: this._idx,
      route: this._route,
      me: this._lib.me.person_id,
      today: todayISO(new Date()),
      ui: this._ui,
      gamesPath: this._gamesPath,
      taskLink: (id) => this._host?.taskLink(id) ?? `/home-keeper/tasks/${encodeURIComponent(id)}`,
      areaName: (id) => this._hass?.areas?.[id]?.name ?? id,
      todoName: (id) => String(states[id]?.attributes?.friendly_name ?? id),
    };
  }

  private _viewHtml(ctx: ViewCtx): string {
    switch (this._route.view) {
      case 'game':
        return renderGame(ctx, ctx.idx.game.get(this._route.id ?? ''));
      case 'shelves':
        return renderShelves(ctx);
      case 'loans':
        return renderLoans(ctx);
      case 'wishlist':
        return renderWishlist(ctx);
      case 'playlog':
        return renderPlayLog(ctx);
      case 'scan':
        return renderScan(ctx);
      case 'settings':
        return renderSettings(ctx);
      case 'import':
        return renderGames({ ...ctx, route: parseRoute(this._gamesPath) }) + renderImport(ctx);
      default:
        return renderGames(ctx);
    }
  }

  private _render(): void {
    const ctx = this._ctx();
    const foot = `<div class="hkl-foot">${escapeHTML(t('common.version', { version: PANEL_VERSION }))}</div>`;
    if (!ctx) {
      this._main.innerHTML = this._error
        ? `<div class="hkl-error" role="alert">${escapeHTML(this._error)}</div>`
        : `<div class="hkl-loading">${escapeHTML(t('common.loading'))}</div>`;
      return;
    }
    const err = this._error ? `<div class="hkl-error" role="alert">${escapeHTML(this._error)}</div>` : '';
    const admin = ctx.lib.me.is_admin ? '' : `<div class="hkl-banner warn">${escapeHTML(t('common.admin_only'))}</div>`;
    this._main.dataset.view = this._route.view;
    this._renders++;
    // The video stays in the page across a render. A browser can pause a video that leaves the page.
    renderKeepFocus(this._root, this._main, `${admin}${err}${this._viewHtml(ctx)}${this._route.view === 'scan' ? '' : foot}`, '[data-slot="video"]');
    wireMarkdown(this._main);
    wireCovers(this._main, this._api, () => this._render());
    const slot = this._main.querySelector('[data-slot="video"]');
    if (slot && !this._scanner) slot.replaceChildren();
    if (slot && this._scanner && this._scanner.video.parentNode !== slot) {
      slot.replaceChildren(this._scanner.video);
      void this._scanner.resume();
    }
    this._paintDebug();
  }

  /** Write the camera state into the debug view (`;debug=1`) of the scan. */
  private _paintDebug(): void {
    const pre = this._main.querySelector('[data-k="cam-debug"]');
    if (!pre) {
      clearInterval(this._debugTimer);
      this._debugTimer = undefined;
      return;
    }
    this._debugTimer ??= setInterval(() => this._paintDebug(), 500);
    pre.textContent = [
      `tab ${this._tabId} of ${tabCount}: in page=${this.isConnected} connects=${this._connects} renders=${this._renders}`,
      ...(this._scanner?.debugLines() ?? ['camera: off']),
      `user agent: ${navigator.userAgent}`,
      'log:',
      ...camLogLines(),
    ].join('\n');
  }

  private _renderDialog(): void {
    const ctx = this._ctx();
    if (!this._dialog || !ctx) {
      this._dlg.innerHTML = '';
      return;
    }
    const areas = Object.values(this._hass?.areas ?? {})
      .map((a): [string, string] => [a.area_id, a.name])
      .sort((a, b) => a[1].localeCompare(b[1]));
    this._dlg.innerHTML = renderDialog(ctx, this._dialog, areas);
    const first = this._dlg.querySelector<HTMLElement>('input:not([type=hidden]):not([type=checkbox]), select, textarea');
    (first ?? this._dlg.querySelector<HTMLElement>('[data-k="d-submit"]'))?.focus();
  }

  /** Show the busy state and the error of the open dialog. The form keeps what the user typed. */
  private _showDialogStatus(): void {
    const state = this._dialog;
    const form = this._dlg.querySelector<HTMLFormElement>('form[data-form="dialog"]');
    if (!state || !form) {
      this._renderDialog();
      return;
    }
    const submit = form.querySelector<HTMLButtonElement>('[data-k="d-submit"]');
    if (submit) submit.disabled = state.busy;
    let error = [...form.children].find((c): c is HTMLElement => c.classList.contains('hkl-error'));
    if (!state.error) {
      error?.remove();
      return;
    }
    if (!error) {
      error = document.createElement('div');
      error.className = 'hkl-error';
      error.setAttribute('role', 'alert');
      form.querySelector('.hkl-dlg-actions')?.before(error);
    }
    error.textContent = state.error;
  }

  private _openDialog(dialog: Dialog): void {
    this._dialog = { dialog, error: '', busy: false };
    this._renderDialog();
  }

  private _closeDialog(): void {
    const sheet = this._sheetOpen();
    this._dialog = null;
    this._renderDialog();
    this._askMiss();
    // After the last title sheet, the barcode field gets the focus, if it shows.
    if (sheet && !this._dialog) this._main.querySelector<HTMLElement>('[data-k="barcode-input"]')?.focus();
  }

  /** Open the Change IGDB game dialog. It searches the title, on the platform of the copies if they have 1. */
  private _openIgdb(game: Game): void {
    const copies = this._idx?.copiesByGame.get(game.id) ?? [];
    const platforms = [...new Set(copies.map((c) => c.platform).filter((p) => p && p !== 'other'))];
    this._openDialog({
      kind: 'igdb-game',
      gameId: game.id,
      query: game.title,
      platform: platforms.length === 1 ? platforms[0] : '',
      results: null,
      searching: false,
      picked: null,
    });
    void this._igdbSearch();
  }

  /** Search IGDB with the text and the platform of the open Change IGDB game dialog. */
  private async _igdbSearch(): Promise<void> {
    const state = this._dialog;
    if (state?.dialog.kind !== 'igdb-game' || state.dialog.searching || !this._api) return;
    const d = state.dialog;
    const form = this._dlg.querySelector<HTMLFormElement>('form[data-form="dialog"]');
    if (form) {
      const data = new FormData(form);
      d.query = String(data.get('igdb_query') ?? '').trim();
      d.platform = String(data.get('igdb_platform') ?? '');
    }
    state.error = '';
    if (!d.query) {
      state.error = t('dialog.need_title');
      this._renderDialog();
      return;
    }
    d.searching = true;
    d.results = null;
    d.picked = null;
    this._renderDialog();
    try {
      const reply = await this._api.call<{ candidates?: Candidate[] }>('search_catalog', {
        query: d.query,
        ...(d.platform ? { platform: d.platform } : {}),
      });
      d.results = reply?.candidates ?? [];
      d.picked = d.results.find((c) => !takenByOther(c, d.gameId))?.igdb_id ?? null;
    } catch (err) {
      state.error = errorText(err);
    }
    d.searching = false;
    // The user can close the dialog during the search.
    if (this._dialog === state) this._renderDialog();
  }

  /** True when the open dialog is a sheet that only a submit or a remove can close. */
  private _sheetOpen(): boolean {
    return this._dialog?.dialog.kind === 'scan-title';
  }

  // ── Events ─────────────────────────────────────────────────────────────────

  private _onClick(ev: MouseEvent): void {
    const target = ev.target as HTMLElement;
    const el = target.closest<HTMLElement>('[data-act]');
    if (!el) return;
    const act = el.dataset.act!;
    if (act.endsWith('scrim') && el !== target) return;
    // With no `host.openTask` (Home Keeper before 0.30), the link opens the task.
    if (act === 'open-task' && !this._host?.openTask) return;
    if (el.tagName === 'A') {
      if (ev.ctrlKey || ev.metaKey || ev.shiftKey || ev.altKey || ev.button !== 0) return;
      ev.preventDefault();
    }
    void this._act(act, el);
  }

  private _onKey(ev: KeyboardEvent): void {
    // Enter in the IGDB search field searches. It does not submit the dialog.
    if (ev.key === 'Enter' && (ev.composedPath()[0] as HTMLElement | undefined)?.dataset?.input === 'igdb-query') {
      ev.preventDefault();
      void this._igdbSearch();
      return;
    }
    if (ev.key !== 'Escape') return;
    if (this._sheetOpen()) {
      ev.stopPropagation();
    } else if (this._dialog) {
      this._closeDialog();
      ev.stopPropagation();
    } else if (this._route.view === 'import') {
      void this._act('import-close', this);
    }
  }

  private _onInput(ev: Event): void {
    const el = ev.target as HTMLInputElement;
    if (el.dataset?.input === 'q') this._search(el.value);
    if (el.dataset?.input === 'miss-title') {
      const submit = this._dlg.querySelector<HTMLButtonElement>('[data-k="d-submit"]');
      if (submit) submit.disabled = Boolean(this._dialog?.busy) || !el.value.trim();
    }
  }

  private async _onChange(ev: Event): Promise<void> {
    const el = ev.target as HTMLInputElement;
    const kind = el.dataset?.chg;
    if (!kind) return;
    const value = el.type === 'checkbox' ? el.checked : el.value;
    const key = el.dataset.key ?? '';
    const id = el.dataset.id ?? '';
    switch (kind) {
      case 'filter':
        this._setFilter(key, String(value));
        return;
      case 'progress-person':
        this._ui.progressPerson = String(value);
        this._ui.progressPlatform = null;
        this._render();
        return;
      case 'progress-platform':
        if (value) this._ui.progressPlatform = String(value) as Platform;
        this._render();
        return;
      case 'progress-field': {
        const num = key === 'playtime_minutes' || key === 'completion_count';
        const v = num ? intOrNull(value) : String(value) || null;
        await this._setProgress({ [key]: key === 'completion_count' ? (v ?? 0) : v });
        return;
      }
      case 'cover-file':
        await this._uploadCover(el);
        return;
      case 'miss-cover': {
        const name = el.files?.[0]?.name;
        const label = this._dlg.querySelector<HTMLElement>('[data-k="d-cover-name"]');
        if (label) label.textContent = name ?? t('scan.miss_cover');
        return;
      }
      case 'wish-buy':
        await this._run('update_wishlist', { game_id: id, buy: Boolean(value) });
        return;
      case 'person': {
        const fields: Fields = { person_id: id };
        if (key === 'share_progress') fields.share_progress = Boolean(value);
        if (key === 'yearly_goal') fields.yearly_goal = intOrNull(value);
        if (key === 'wishlist_todo') fields.wishlist_todo = String(value) || null;
        await this._run('set_person_settings', fields, t('settings.saved'));
        return;
      }
      case 'export-person':
        this._ui.exportPerson = String(value);
        return;
      case 'scan-method':
        this._ui.scan.method = value === 'manual' ? 'manual' : 'camera';
        this._render();
        return;
      case 'scan-field': {
        const s = this._ui.scan as unknown as Record<string, unknown>;
        s[key] = value;
        return;
      }
      case 'scan-markread':
        this._ui.scan.markRead = Boolean(value);
        return;
      case 'import': {
        const s = this._ui.import as unknown as Record<string, unknown>;
        s[key] = value;
        if (this._ui.import.content) await this._dryRun();
        else this._render();
        return;
      }
      case 'import-file':
        await this._readImportFile(el);
        return;
    }
  }

  private _onSubmit(ev: SubmitEvent): void {
    const form = ev.target as HTMLFormElement;
    const kind = form.dataset?.form;
    if (!kind) return;
    ev.preventDefault();
    if (kind === 'dialog') void this._submitDialog(form);
    if (kind === 'notes') void this._saveNotes(form);
    if (kind === 'currency') void this._saveCurrency(form);
    if (kind === 'barcode') {
      if (this._scanPaused()) {
        this._askMiss();
        return;
      }
      const input = form.elements.namedItem('barcode') as HTMLInputElement;
      const code = normalizeBarcode(input.value);
      if (!code) {
        this._toast(t('scan.bad_barcode'));
        return;
      }
      input.value = '';
      void this._scanCode(code);
    }
  }

  private _game(): Game | undefined {
    return this._idx?.game.get(this._route.id ?? '');
  }

  private async _act(act: string, el: HTMLElement): Promise<void> {
    const id = el.dataset.id ?? '';
    const value = el.dataset.value ?? '';
    const game = this._game();
    const lib = this._lib;
    const idx = this._idx;
    switch (act) {
      case 'nav':
        this._go(el.dataset.path ?? '/games', el.dataset.replace === '1');
        return;
      case 'back':
        this._go(this._gamesPath, true);
        return;
      case 'open-task':
        this._host?.openTask?.(id);
        return;
      case 'status':
        this._setFilter('status', value);
        return;
      case 'layout':
        this._setFilter('view', value);
        return;
      case 'clear-filters': {
        const f = readFilters(this._route.query);
        this._go(gamesPath({ sort: f.sort, view: f.view }), true);
        return;
      }
      case 'more':
        this._ui.limit += PAGE;
        this._render();
        return;
      case 'set-status':
        if (game) await this._setStatus(game, value as PlayStatus);
        return;
      case 'progress-platform':
        this._ui.progressPlatform = value as Platform;
        this._render();
        return;
      case 'progress-clear':
        if (await this._setProgress({ play_status: 'none' })) this._ui.progressPlatform = null;
        this._render();
        return;
      case 'rate': {
        const { pid, platform } = this._progressTarget();
        const row = game ? progressOf(game, pid, platform) : null;
        const n = Number(value);
        await this._setProgress({ rating: row?.rating === n ? null : n });
        return;
      }
      case 'notes-tab':
        this._ui.notesTab = value === 'private' ? 'private' : 'shared';
        this._ui.editNotes = false;
        this._render();
        return;
      case 'notes-edit':
        this._ui.editNotes = true;
        this._render();
        this._main.querySelector<HTMLElement>('[data-k="notes-text"]')?.focus();
        return;
      case 'notes-cancel':
        this._ui.editNotes = false;
        this._render();
        return;
      case 'return-loan':
        await this._run('return_loan', { loan_id: id }, t('loan.returned_toast'));
        return;
      case 'playlog-person':
        this._go(buildPath({ view: 'playlog', query: withQuery(this._route.query, 'person', id) }), true);
        return;
      case 'playlog-toggle':
        this._ui.playlog.open[id] = !this._ui.playlog.open[id];
        this._render();
        return;
      case 'delete-session':
        this._openDialog({ kind: 'confirm', title: t('dialog.delete_session'), text: t('dialog.delete_session_text'), label: t('action.delete'), command: 'delete_session', fields: { session_id: id } });
        return;
      case 'log-session':
        this._openDialog({ kind: 'log-session', personId: this._ctx() ? playLogPerson(this._ctx()!) : null });
        return;
      case 'delete-loan':
        this._openDialog({ kind: 'confirm', title: t('dialog.delete_loan'), text: t('dialog.delete_loan_text'), label: t('action.delete'), command: 'delete_loan', fields: { loan_id: id } });
        return;
      case 'move-copy':
        this._openDialog({ kind: 'move', copyId: id });
        return;
      case 'add-game':
        this._openDialog({ kind: 'add-game' });
        return;
      case 'edit-game':
        if (game) this._openDialog({ kind: 'edit-game', gameId: game.id });
        return;
      case 'scan-details':
        this._openDialog({ kind: 'edit-game', gameId: id });
        return;
      case 'igdb-game':
        if (game) this._openIgdb(game);
        return;
      case 'igdb-search':
        void this._igdbSearch();
        return;
      case 'add-copy':
        if (game) this._openDialog({ kind: 'copy', gameId: game.id, copyId: null });
        return;
      case 'edit-copy':
        if (game) this._openDialog({ kind: 'copy', gameId: game.id, copyId: id });
        return;
      case 'delete-copy':
        this._openDialog({ kind: 'confirm', title: t('dialog.delete_copy'), text: t('dialog.delete_copy_text'), label: t('action.delete'), command: 'delete_copy', fields: { copy_id: id } });
        return;
      case 'delete-game':
        if (game) {
          this._openDialog({ kind: 'confirm', title: t('dialog.delete_game'), text: t('dialog.delete_game_text', { title: game.title }), label: t('action.delete'), command: 'delete_game', fields: { game_id: game.id }, after: this._gamesPath });
        }
        return;
      case 'change-cover':
        this._main.querySelector<HTMLInputElement>('[data-k="cover-file"]')?.click();
        return;
      case 'lend':
        this._openDialog({ kind: 'lend', gameId: el.dataset.game ?? null });
        return;
      case 'borrow':
        this._openDialog({ kind: 'borrow' });
        return;
      case 'wish-add':
        this._openDialog({ kind: 'wish-add', gameId: null });
        return;
      case 'wish-this':
        if (game) this._openDialog({ kind: 'wish-add', gameId: game.id });
        return;
      case 'got-it':
        this._openDialog({ kind: 'got-it', gameId: id });
        return;
      case 'wish-remove':
        await this._run('remove_from_wishlist', { game_id: id }, t('wishlist.removed'));
        return;
      case 'add-room':
        this._openDialog({ kind: 'room', roomId: null });
        return;
      case 'edit-room':
        this._openDialog({ kind: 'room', roomId: id });
        return;
      case 'delete-room':
        this._openDialog({ kind: 'confirm', title: t('dialog.delete_room'), text: t('dialog.delete_place_text', { name: idx?.room.get(id)?.name ?? '' }), label: t('action.delete'), command: 'delete_room', fields: { room_id: id, force: true }, after: '/shelves' });
        return;
      case 'add-unit':
        this._openDialog({ kind: 'unit', roomId: id, unitId: null });
        return;
      case 'edit-unit': {
        const bc = idx?.unit.get(id);
        if (bc) this._openDialog({ kind: 'unit', roomId: bc.room_id, unitId: id });
        return;
      }
      case 'delete-unit':
        this._openDialog({ kind: 'confirm', title: t('dialog.delete_unit'), text: t('dialog.delete_place_text', { name: idx?.unit.get(id)?.name ?? '' }), label: t('action.delete'), command: 'delete_unit', fields: { unit_id: id, force: true } });
        return;
      case 'add-shelf':
        this._openDialog({ kind: 'shelf', unitId: id, shelfId: null });
        return;
      case 'edit-shelf': {
        const sh = idx?.shelf.get(id);
        if (sh) this._openDialog({ kind: 'shelf', unitId: sh.unit_id, shelfId: id });
        return;
      }
      case 'delete-shelf':
        this._openDialog({ kind: 'confirm', title: t('dialog.delete_shelf'), text: t('dialog.delete_place_text', { name: idx?.shelf.get(id)?.name ?? '' }), label: t('action.delete'), command: 'delete_shelf', fields: { shelf_id: id, force: true } });
        return;
      case 'set-shelf':
        this._openDialog({ kind: 'set-shelf' });
        return;
      case 'dialog-close':
      case 'dialog-scrim':
        this._closeDialog();
        return;
      case 'scan-miss-remove':
        await this._removeMiss();
        return;
      case 'export':
        await this._export();
        return;
      case 'import-pick':
        this._main.querySelector<HTMLInputElement>('[data-k="im-file"]')?.click();
        return;
      case 'import-run':
        await this._runImport();
        return;
      case 'import-close':
      case 'import-close-scrim':
        this._ui.import = freshImport(lib?.me.person_id ?? null);
        this._go(this._gamesPath, true);
        return;
      default:
        await this._scanAct(act, el);
    }
  }

  // ── Progress ───────────────────────────────────────────────────────────────

  /** The person and the platform that the progress form of the open game edits. */
  private _progressTarget(): { pid: string | null; platform: Platform | null } {
    const ctx = this._ctx();
    const game = this._game();
    if (!ctx || !game) return { pid: null, platform: null };
    const { pid, platform } = progressTarget(ctx, game);
    return { pid, platform };
  }

  private async _setProgress(fields: Fields): Promise<boolean> {
    const id = this._route.id;
    const { pid, platform } = this._progressTarget();
    if (!id || !pid) {
      this._toast(t('common.no_person'));
      return false;
    }
    return this._run('set_progress', { game_id: id, person_id: pid, platform, ...fields });
  }

  private async _setStatus(game: Game, status: PlayStatus): Promise<void> {
    const { pid, platform } = this._progressTarget();
    const row = progressOf(game, pid, platform);
    const today = todayISO(new Date());
    const fields: Fields = { play_status: status };
    if (status === 'playing' && !row?.started_at) fields.started_at = today;
    if (status === 'completed' && row?.play_status !== 'completed') {
      fields.completed_at = today;
      fields.completion_count = (row?.completion_count ?? 0) + 1;
    }
    await this._setProgress(fields);
  }

  private async _saveNotes(form: HTMLFormElement): Promise<void> {
    const game = this._game();
    if (!game) return;
    const text = (form.elements.namedItem('text') as HTMLTextAreaElement).value;
    const saved =
      this._ui.notesTab === 'shared'
        ? await this._run('update_game', { game_id: game.id, shared_notes: text })
        : await this._setProgress({ review: text });
    // If the save fails, the editor stays open with the text.
    if (saved) this._ui.editNotes = false;
    this._render();
  }

  private async _saveCurrency(form: HTMLFormElement): Promise<void> {
    const input = form.elements.namedItem('currency') as HTMLInputElement;
    const currency = input.value.trim().toUpperCase();
    if (!/^[A-Z]{3}$/.test(currency)) {
      this._toast(t('settings.currency_bad'));
      return;
    }
    if (currency === this._lib?.currency) return;
    await this._run('set_settings', { currency }, t('settings.saved'));
  }

  private async _uploadCover(input: HTMLInputElement): Promise<void> {
    const game = this._game();
    const file = input.files?.[0];
    input.value = '';
    if (!game || !file) return;
    if (file.size > MAX_COVER_BYTES) {
      this._toast(t('game.cover_too_big'));
      return;
    }
    try {
      const fileId = await this._api!.uploadCover(file);
      await this._run('set_cover', { game_id: game.id, kind: 'custom', file_id: fileId }, t('game.cover_saved'));
    } catch (err) {
      this._toast(errorText(err));
    }
  }

  // ── Dialog submit ──────────────────────────────────────────────────────────

  private async _submitDialog(form: HTMLFormElement): Promise<void> {
    const state = this._dialog;
    if (!state || state.busy) return;
    const data = new FormData(form);
    const str = (name: string) => String(data.get(name) ?? '').trim();
    const on = (name: string) => data.get(name) === 'on';
    const d = state.dialog;
    state.busy = true;
    state.error = '';
    this._showDialogStatus();
    try {
      const api = this._api!;
      let after: string | undefined;
      switch (d.kind) {
        case 'add-game': {
          const query = str('query');
          if (!query) throw new Error(t('dialog.need_title'));
          const code = retailBarcode(query);
          const res = await api.call<Record<string, unknown>>('add_game', {
            ...(code ? { barcode: code } : { title: query }),
          });
          const gameId = replyId(res, 'game');
          const existing = Boolean(res?.existing ?? (res?.game as Record<string, unknown> | undefined)?.existing);
          if (existing) this._toast(t('dialog.existing'));
          else if (gameId && on('own')) {
            // The barcode of the case goes on the copy, so a scan finds the game later.
            await api.call('add_copy', {
              game_id: gameId,
              shelf_id: str('shelf_id') || null,
              platform: str('platform'),
              format: str('format'),
              ...(code ? { barcode: code } : {}),
            });
          }
          if (gameId) after = `/games/${encodeURIComponent(gameId)}`;
          break;
        }
        case 'igdb-game': {
          const picked = str('igdb_id');
          if (!picked) throw new Error(t('igdb.pick'));
          await api.call('set_igdb_game', { game_id: d.gameId, igdb_id: Number(picked) });
          this._toast(t('igdb.done'));
          break;
        }
        case 'edit-game': {
          const fields: Fields = {
            game_id: d.gameId,
            title: str('title'),
            franchise: str('franchise') || null,
            genres: splitList(str('genres')),
            release_date: str('release_date'),
            tags: splitList(str('tags')),
            summary: str('summary'),
          };
          if (on('details_done')) fields.needs_details = false;
          await api.call('update_game', fields);
          break;
        }
        case 'scan-title': {
          const title = str('title');
          if (!title) throw new Error(t('scan.miss_need_title'));
          const cover = data.get('cover');
          const photo = cover instanceof File && cover.size > 0 ? cover : null;
          if (photo && photo.size > MAX_COVER_BYTES) throw new Error(t('game.cover_too_big'));
          // Send only what the user typed. An empty field keeps the stored value.
          const fields: Fields = { game_id: d.gameId, title };
          for (const name of ['franchise', 'release_date']) if (str(name)) fields[name] = str(name);
          const genres = splitList(str('genres'));
          if (genres.length) fields.genres = genres;
          await api.call('update_game', fields);
          const stored = d.copyId ? this._idx?.copy.get(d.copyId) : undefined;
          const copyFields: Fields = {};
          for (const name of ['format', 'platform'] as const) {
            if (str(name) && str(name) !== stored?.[name]) copyFields[name] = str(name);
          }
          if (d.copyId && Object.keys(copyFields).length) {
            await api.call('update_copy', { copy_id: d.copyId, ...copyFields });
          }
          if (photo) {
            const fileId = await api.uploadCover(photo);
            await api.call('set_cover', { game_id: d.gameId, kind: 'custom', file_id: fileId });
          }
          this._markMiss(d.key, 'named');
          break;
        }
        case 'copy': {
          const fields: Fields = {
            platform: str('platform'),
            format: str('format'),
            storefront: str('storefront'),
            region: str('region'),
            edition: str('edition'),
            steelbook: on('steelbook'),
            barcode: null,
            condition: str('condition') || null,
            acquired: str('acquired') || null,
            acquired_from: str('acquired_from'),
            price: numberOrNull(str('price')),
            value: numberOrNull(str('value')),
            note: str('note'),
          };
          if (str('barcode')) {
            const code = normalizeBarcode(str('barcode'));
            if (!code) throw new Error(t('scan.bad_barcode'));
            fields.barcode = code;
          }
          // A digital copy has no shelf.
          const shelf = str('format') === 'digital' ? null : str('shelf_id') || null;
          if (d.copyId) {
            await api.call('update_copy', { copy_id: d.copyId, ...fields });
            if ((this._idx?.copy.get(d.copyId)?.shelf_id ?? null) !== shelf) await api.call('move_copy', { copy_id: d.copyId, shelf_id: shelf });
          } else {
            await api.call('add_copy', { game_id: d.gameId, shelf_id: shelf, ...fields });
          }
          break;
        }
        case 'move':
          await api.call('move_copy', { copy_id: d.copyId, shelf_id: str('shelf_id') || null });
          break;
        case 'set-shelf': {
          const shelf = str('shelf_id') || null;
          for (const copyId of data.getAll('copy')) await api.call('move_copy', { copy_id: String(copyId), shelf_id: shelf });
          break;
        }
        case 'log-session':
          if (!str('game_id') || !str('minutes')) throw new Error(t('playlog.need_minutes'));
          await api.call('log_session', {
            game_id: str('game_id'),
            person_id: str('person_id') || undefined,
            platform: str('platform') || undefined,
            minutes: Number(str('minutes')),
            date: str('date') || undefined,
          });
          this._toast(t('playlog.logged_toast'));
          break;
        case 'lend':
          if (!str('copy_id') || !str('party')) throw new Error(t('dialog.need_party'));
          await api.call('lend_game', {
            copy_id: str('copy_id'),
            party: str('party'),
            started: str('started') || undefined,
            due: str('due') || undefined,
            note: str('note'),
            add_task: on('add_task'),
          });
          this._toast(t('loan.lent_toast'));
          break;
        case 'borrow': {
          const query = str('query');
          if (!query || !str('party')) throw new Error(t('dialog.need_party'));
          const code = retailBarcode(query);
          await api.call('borrow_game', {
            ...(code ? { barcode: code } : { title: query }),
            party: str('party'),
            person_id: str('person_id'),
            format: str('format'),
            started: str('started') || undefined,
            due: str('due') || undefined,
            note: str('note'),
            add_task: on('add_task'),
          });
          break;
        }
        case 'wish-add': {
          const query = str('query');
          const code = query ? retailBarcode(query) : null;
          if (!d.gameId && !query) throw new Error(t('dialog.need_title'));
          await api.call('add_to_wishlist', {
            ...(d.gameId ? { game_id: d.gameId } : code ? { barcode: code } : { title: query }),
            person_id: str('person_id'),
            buy: on('buy'),
          });
          this._toast(t('wishlist.added'));
          break;
        }
        case 'got-it':
          await api.call('got_wishlist_game', { game_id: d.gameId, shelf_id: str('shelf_id') || null, platform: str('platform'), format: str('format') });
          break;
        case 'room': {
          const fields = { name: str('name'), area_id: str('area_id') || null };
          if (!fields.name) throw new Error(t('dialog.need_name'));
          if (d.roomId) await api.call('update_room', { room_id: d.roomId, ...fields });
          else {
            const res = await api.call('add_room', fields);
            const roomId = replyId(res, 'room');
            if (roomId) after = `/shelves/${encodeURIComponent(roomId)}`;
          }
          break;
        }
        case 'unit': {
          const fields = { name: str('name'), note: str('note') };
          if (!fields.name) throw new Error(t('dialog.need_name'));
          if (d.unitId) await api.call('update_unit', { unit_id: d.unitId, ...fields });
          else {
            const res = await api.call('add_unit', { room_id: d.roomId, ...fields });
            const caseId = replyId(res, 'unit');
            const n = Math.min(20, intOrNull(str('shelves')) ?? 0);
            for (let i = 1; caseId && i <= n; i++) {
              await api.call('add_shelf', { unit_id: caseId, name: t('dialog.shelf_default', { n: i }), order: i });
            }
          }
          break;
        }
        case 'shelf': {
          const name = str('name');
          if (!name) throw new Error(t('dialog.need_name'));
          if (d.shelfId) await api.call('update_shelf', { shelf_id: d.shelfId, name });
          else {
            const order = (this._lib?.shelves.filter((s) => s.unit_id === d.unitId).length ?? 0) + 1;
            await api.call('add_shelf', { unit_id: d.unitId, name, order });
          }
          break;
        }
        case 'confirm':
          await api.call(d.command, d.fields);
          after = d.after;
          break;
      }
      // The user can close this dialog and open a new one during the call.
      if (this._dialog === state) this._closeDialog();
      void this._refresh();
      if (after) this._go(after, d.kind === 'confirm');
    } catch (err) {
      state.busy = false;
      state.error = errorText(err);
      this._dlg.querySelector<HTMLElement>('[data-k="d-sending"]')?.setAttribute('hidden', '');
      if (this._dialog === state) this._showDialogStatus();
    }
  }

  // ── Import and export ──────────────────────────────────────────────────────

  private async _readImportFile(input: HTMLInputElement): Promise<void> {
    const file = input.files?.[0];
    input.value = '';
    if (!file) return;
    const s = this._ui.import;
    if (file.size > MAX_IMPORT_BYTES) {
      s.error = t('import.too_big');
      this._render();
      return;
    }
    s.fileName = file.name;
    s.content = await file.text();
    s.rowCount = csvRowCount(s.content);
    s.summary = null;
    s.done = false;
    s.error = '';
    await this._dryRun();
  }

  private _importFields(dryRun: boolean): Fields {
    const s = this._ui.import;
    return {
      content: s.content,
      person_id: s.personId ?? this._lib?.me.person_id ?? undefined,
      shelf_id: s.shelfId || null,
      import_review: s.importReview,
      replace_progress: s.replaceProgress,
      dry_run: dryRun,
    };
  }

  private async _dryRun(): Promise<void> {
    const s = this._ui.import;
    // A change of the source, the person or the shelf starts a new preview.
    // Only the reply of the latest preview is used.
    const run = ++this._dryRunSeq;
    s.busy = true;
    s.error = '';
    this._render();
    let summary: ImportSummary | null = null;
    let error = '';
    try {
      summary = await this._api!.importCsv(this._importFields(true));
    } catch (err) {
      error = errorText(err);
    }
    if (run !== this._dryRunSeq || this._ui.import !== s) return;
    s.summary = summary;
    s.error = error;
    s.busy = false;
    this._render();
  }

  private async _runImport(): Promise<void> {
    const s = this._ui.import;
    if (!s.summary || s.busy) return;
    s.busy = true;
    this._render();
    try {
      s.summary = await this._api!.importCsv(this._importFields(false));
      s.done = true;
      this._toast(t('import.done'));
      void this._refresh();
    } catch (err) {
      s.error = errorText(err);
    }
    s.busy = false;
    this._render();
  }

  private async _export(): Promise<void> {
    try {
      const res = await this._api!.exportCsv({ person_id: this._ui.exportPerson || undefined });
      const blob = new Blob([res.content], { type: 'text/csv;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = res.filename || 'games.csv';
      this._root.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (err) {
      this._toast(errorText(err));
    }
  }

  // ── Scan ───────────────────────────────────────────────────────────────────

  private _scanPath(query: Record<string, string>): string {
    return buildPath({ view: 'scan', query });
  }

  private _syncScanner(): void {
    const want = this._route.view === 'scan' && this._route.query.step === 'camera' && this._ui.scan.method === 'camera';
    if (!want) {
      this._stopScanner();
      return;
    }
    if (this._scanner) return;
    const scanner: Scanner = new Scanner((code) => this._onCode(code), undefined, () => this._onCameraState(scanner));
    this._scanner = scanner;
    this._ui.scan.cameraError = '';
    this._ui.scan.stalled = false;
    void scanner.start().then((res) => {
      // The user left the camera step while the camera started.
      if (this._scanner !== scanner) {
        scanner.stop();
        return;
      }
      if (res !== 'ok') {
        this._ui.scan.cameraError = res;
        this._ui.scan.manualOpen = true;
        this._scanner = null;
      } else {
        this._ui.scan.torch = scanner.torchSupported() ? false : null;
      }
      this._render();
    });
  }

  private _stopScanner(): void {
    this._scanner?.stop();
    this._scanner = null;
    clearTimeout(this._stallTimer);
    this._ui.scan.stalled = false;
  }

  /**
   * The picture of *scanner* stopped or started. A short stop is normal, for
   * example when Home Keeper moves the tab. If the picture is still stopped
   * after the wait, show the button that starts it again.
   */
  private _onCameraState(scanner: Scanner): void {
    clearTimeout(this._stallTimer);
    this._stallTimer = setTimeout(() => {
      if (this._scanner !== scanner) return;
      const stalled = scanner.stalled();
      if (stalled === this._ui.scan.stalled) return;
      this._ui.scan.stalled = stalled;
      this._render();
    }, STALL_MS);
  }

  /** The user tapped the stopped picture. Play it again, or else (track ended, frozen picture) start a new camera. */
  private async _restartCamera(): Promise<void> {
    const scanner = this._scanner;
    if (scanner && !scanner.ended() && !scanner.isFrozen() && (await scanner.resume())) {
      this._onCameraState(scanner);
      return;
    }
    logCam(`tab ${this._tabId} new camera`);
    this._stopScanner();
    this._syncScanner();
    this._render();
  }

  private _onCode(code: string): void {
    if (this._scanPaused()) {
      this._askMiss();
      return;
    }
    const barcode = normalizeBarcode(code);
    if (!barcode || !this._gate(barcode, Date.now())) return;
    navigator.vibrate?.(40);
    void this._scanCode(barcode);
  }

  private async _scanCode(barcode: string): Promise<void> {
    const s = this._ui.scan;
    const entry: ScanEntry = { key: ++this._scanKey, barcode, pending: true, res: null };
    s.results.push(entry);
    this._render();
    try {
      if (this._route.query.mode === 'borrowed') {
        const res = await this._api!.call<Record<string, unknown>>('borrow_game', {
          barcode,
          party: s.party || t('loan.unknown_party'),
          person_id: s.personId ?? this._lib?.me.person_id ?? undefined,
          due: s.due || undefined,
          started: todayISO(new Date()),
          add_task: s.addTask,
        });
        const game = (res?.game as Game | undefined) ?? null;
        entry.res = { result: 'added', game, copy: null, existing_copies: [] };
      } else {
        entry.res = await this._api!.scanBarcode({ barcode, shelf_id: routeShelf(this._ctx()!), platform: s.platform, format: s.format, on_duplicate: 'ask' });
      }
    } catch (err) {
      entry.error = errorText(err);
    }
    entry.pending = false;
    this._render();
    this._askMiss();
    void this._refresh();
  }

  /** True when the scan takes no code: a dialog is open, or a new game has no title yet. */
  private _scanPaused(): boolean {
    return Boolean(this._dialog || nextMiss(this._ui.scan.results));
  }

  /** Open the title sheet for the next scan of a new game, if no dialog is open. */
  private _askMiss(): void {
    if (this._dialog || this._route.view !== 'scan') return;
    const miss = nextMiss(this._ui.scan.results);
    const game = miss?.res?.game;
    if (!miss || !game) return;
    this._openDialog({ kind: 'scan-title', key: miss.key, gameId: game.id, copyId: miss.res?.copy?.id ?? null, barcode: miss.barcode });
    this._render();
  }

  private _markMiss(key: number, flag: 'named' | 'removed'): void {
    const entry = this._ui.scan.results.find((r) => r.key === key);
    if (entry) entry[flag] = true;
  }

  /** Delete the game of the open title sheet, with its copy. */
  private async _removeMiss(): Promise<void> {
    const state = this._dialog;
    const d = state?.dialog;
    if (!state || d?.kind !== 'scan-title' || state.busy) return;
    state.busy = true;
    state.error = '';
    this._showDialogStatus();
    try {
      await this._api!.call('delete_game', { game_id: d.gameId });
      this._markMiss(d.key, 'removed');
      if (this._dialog === state) this._closeDialog();
      this._render();
      void this._refresh();
    } catch (err) {
      state.busy = false;
      state.error = errorText(err);
      if (this._dialog === state) this._showDialogStatus();
    }
  }

  private async _scanDuplicate(entry: ScanEntry, choice: 'move' | 'add_copy' | 'skip'): Promise<void> {
    entry.choice = choice;
    entry.pending = true;
    this._render();
    try {
      const s = this._ui.scan;
      entry.res = await this._api!.scanBarcode({ barcode: entry.barcode, shelf_id: routeShelf(this._ctx()!), platform: s.platform, format: s.format, on_duplicate: choice });
    } catch (err) {
      entry.error = errorText(err);
    }
    entry.pending = false;
    this._render();
    void this._refresh();
  }

  /** Set "Read" for me on each game that the session added or moved. */
  private async _applyMarkRead(): Promise<void> {
    const s = this._ui.scan;
    const me = this._lib?.me.person_id;
    if (!s.markRead || !me || isBorrowedMode(this._ctx()!)) return;
    // 1 row for each game and platform: the platform of the scanned copy.
    const rows = new Map<string, [string, Platform | undefined]>();
    for (const r of s.results) {
      const res = r.res as ScanResult | null;
      if (!res || (res.result !== 'added' && res.result !== 'moved') || !res.game) continue;
      const platform = res.copy?.platform;
      rows.set(`${res.game.id}:${platform ?? ''}`, [res.game.id, platform]);
    }
    const today = todayISO(new Date());
    for (const [gameId, platform] of rows.values()) {
      await this._run('set_progress', { game_id: gameId, person_id: me, platform, play_status: 'completed', completed_at: today });
    }
    if (rows.size) this._toast(tn('scan.marked_read', rows.size));
  }

  private async _scanAct(act: string, el: HTMLElement): Promise<void> {
    const s = this._ui.scan;
    const q = this._route.query;
    switch (act) {
      case 'scan-room':
        s.roomId = el.dataset.id ?? null;
        this._render();
        return;
      case 'scan-start': {
        const ctx = this._ctx();
        if (ctx && cameraBlocked(ctx)) return;
        s.results = [];
        s.manualOpen = s.method === 'manual';
        this._gate = makeCodeGate(3000);
        this._go(this._scanPath({ ...q, step: 'camera' }));
        return;
      }
      case 'scan-manual':
        s.manualOpen = !s.manualOpen;
        this._render();
        this._main.querySelector<HTMLElement>('[data-k="barcode-input"]')?.focus();
        return;
      case 'scan-dup': {
        const entry = s.results.find((r) => String(r.key) === el.dataset.key);
        const choice = el.dataset.value as 'move' | 'add_copy' | 'skip';
        if (entry) await this._scanDuplicate(entry, choice);
        return;
      }
      case 'scan-camera':
        await this._restartCamera();
        return;
      case 'scan-torch':
        if (this._scanner && s.torch !== null) {
          s.torch = !s.torch;
          await this._scanner.setTorch(s.torch).catch(() => undefined);
          this._render();
        }
        return;
      case 'scan-done':
        this._go(this._scanPath({ ...q, step: 'summary' }), true);
        return;
      case 'scan-next':
        await this._applyMarkRead();
        s.results = [];
        this._go(this._scanPath({ ...q, shelf: el.dataset.id ?? '', step: 'camera' }), true);
        return;
      case 'scan-finish': {
        await this._applyMarkRead();
        s.results = [];
        const room = this._idx ? shelfPath(this._idx, routeShelf(this._ctx()!)).room : null;
        this._go(q.mode === 'borrowed' ? buildPath({ view: 'loans', query: { tab: 'in' } }) : room ? `/shelves/${encodeURIComponent(room.id)}` : '/games', true);
        return;
      }
      case 'scan-setup':
        this._go(this._scanPath({ ...q, step: '' }), true);
        return;
      case 'scan-exit':
        this._go(q.mode === 'borrowed' ? '/loans' : this._gamesPath, true);
        return;
    }
  }
}
