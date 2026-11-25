import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import '../src/tab-index.ts';
import { coverUrls } from '../src/markup.ts';
import { ALEX, gameId, fakeHass, fixture, flush, SAM } from './fake-hass.js';

// The barcode is on a copy. The scan tests type these codes; the fake replies choose the game.
const DUNE_CODE = '9780441013593';
const WISHED_CODE = '9780547928227';

let el;
let host;

async function mount(path = '/games', opts = {}) {
  const fake = fakeHass(opts);
  el = document.createElement('home-keeper-games-tab');
  host = {
    apiVersion: 1,
    navigate: vi.fn((p) => {
      el.route = { path: p };
    }),
    taskLink: vi.fn((id) => `/home-keeper/tasks/${id}`),
    applianceLink: (id) => `/home-keeper/appliances/${id}`,
    showToast: vi.fn(),
  };
  el.host = host;
  el.route = { path };
  document.body.appendChild(el);
  el.hass = fake.hass;
  await flush();
  return fake;
}

const $ = (sel) => el.shadowRoot.querySelector(sel);
const $$ = (sel) => [...el.shadowRoot.querySelectorAll(sel)];
const text = () => el.shadowRoot.getElementById('main').textContent.replace(/\s+/g, ' ');

function change(node, value) {
  if (node.type === 'checkbox') node.checked = value;
  else node.value = value;
  node.dispatchEvent(new Event('change', { bubbles: true }));
}

afterEach(() => {
  el?.remove();
  el = undefined;
  vi.useRealTimers();
});

describe('data', () => {
  it('fetches get_state, then subscribes, and fetches again on changed', async () => {
    const fake = await mount();
    expect(fake.send.mock.calls[0][0]).toEqual({ type: 'home_keeper_games/get_state' });
    expect(fake.hass.connection.subscribeMessage).toHaveBeenCalledTimes(1);
    expect(fake.subs[0].msg).toEqual({ type: 'home_keeper_games/subscribe' });
    fake.push();
    await flush();
    expect(fake.calls('get_state')).toHaveLength(2);
  });

  it('ends a subscription that starts after the tab leaves the page', async () => {
    const fake = fakeHass();
    const unsub = vi.fn();
    let resolve;
    fake.hass.connection.subscribeMessage = vi.fn(() => new Promise((r) => (resolve = r)));
    el = document.createElement('home-keeper-games-tab');
    el.route = { path: '/games' };
    document.body.appendChild(el);
    el.hass = fake.hass;
    await flush();
    el.remove();
    resolve(unsub);
    await flush();
    expect(unsub).toHaveBeenCalledTimes(1);
  });

  it('shows the error of a failed fetch', async () => {
    const fake = fakeHass();
    fake.send.mockRejectedValueOnce({ message: 'boom' });
    el = document.createElement('home-keeper-games-tab');
    el.route = { path: '/games' };
    document.body.appendChild(el);
    el.hass = fake.hass;
    await flush();
    expect(text()).toContain('boom');
  });
});

describe('games view', () => {
  it('shows the owned games with the status counts', async () => {
    await mount();
    expect($$('.hkl-tile')).toHaveLength(38);
    expect($('[data-k="st-all"]').textContent).toContain('38');
    expect($('[data-k="st-completed"]').textContent).toContain('9');
    expect($('[data-k="nav-games"]').getAttribute('aria-current')).toBe('page');
  });

  it('reads the filters from the route', async () => {
    await mount('/games;status=playing;view=rows');
    expect($$('.hkl-row').map((r) => r.querySelector('.hkl-row-title').textContent)).toEqual([
      'Every Grain of Rice',
      'Integrated Chinese 1',
      'Project Hail Mary',
      'The Left Hand of Darkness',
      'The Ministry for the Future',
    ]);
    expect($('[data-k="st-playing"]').getAttribute('aria-pressed')).toBe('true');
  });

  it('includes games with no copy when owned is all', async () => {
    await mount('/games;owned=all');
    expect($$('.hkl-tile')).toHaveLength(44);
  });

  it('navigates with replace when a chip or a menu changes', async () => {
    await mount();
    $('[data-k="st-completed"]').click();
    expect(host.navigate).toHaveBeenLastCalledWith('/games;status=completed', { replace: true });
    change($('[data-k="f-sort"]'), 'franchise');
    expect(host.navigate).toHaveBeenLastCalledWith('/games;status=completed;sort=franchise', { replace: true });
    $('[data-k="clear"]').click();
    expect(host.navigate).toHaveBeenLastCalledWith('/games;sort=franchise', { replace: true });
  });

  it('clears a shelf that is not in the new room', async () => {
    const state = fixture();
    const shelf = Object.values(state.shelves).find((s) => s.name === 'Top').id;
    const office = Object.values(state.rooms).find((r) => r.name === 'Office').id;
    await mount(`/games;shelf=${shelf}`);
    change($('[data-k="f-room"]'), office);
    expect(host.navigate).toHaveBeenLastCalledWith(`/games;room=${office}`, { replace: true });
  });

  it('debounces the search into the URL and keeps the focus', async () => {
    await mount();
    vi.useFakeTimers();
    const input = $('[data-k="q"]');
    input.focus();
    input.value = 'science fiction';
    input.dispatchEvent(new Event('input', { bubbles: true }));
    expect(host.navigate).not.toHaveBeenCalled();
    vi.advanceTimersByTime(260);
    expect(host.navigate).toHaveBeenCalledWith('/games;q=science%20fiction', { replace: true });
    expect(el.shadowRoot.activeElement?.dataset.k).toBe('q');
    expect($$('.hkl-tile').length).toBe(11);
  });

  it('opens a game with a push', async () => {
    await mount();
    $('.hkl-tile').click();
    expect(host.navigate.mock.calls[0][0]).toMatch(/^\/games\/[0-9a-f]{32}$/);
    expect(host.navigate.mock.calls[0][1]).toEqual({ replace: false });
  });

  it('escapes user text', async () => {
    const state = fixture();
    state.games.find((b) => b.title === 'Dune').title = '<img src=x onerror="alert(1)">';
    await mount('/games', { state });
    expect(el.shadowRoot.querySelector('img[src="x"]')).toBeNull();
    expect(text()).toContain('<img src=x onerror="alert(1)">');
  });

  it('shows a banner for a non-admin user', async () => {
    const state = fixture();
    state.me.is_admin = false;
    await mount('/games', { state });
    expect(text()).toContain('Only an admin can change the library.');
  });
});

describe('covers', () => {
  beforeEach(() => coverUrls.clear());

  it('signs each cover path, then shows the image with the signed URL', async () => {
    const state = fixture();
    const game = state.games.find((b) => b.title === 'The Left Hand of Darkness');
    expect(game.cover_url).toMatch(/^\/api\/home_keeper_games\/cover\/[0-9a-f]{32}\?v=[0-9a-f]{8}$/);
    const fake = await mount('/games');
    const signs = fake.send.mock.calls.map((c) => c[0]).filter((m) => m.type === 'auth/sign_path');
    expect(signs.length).toBe(state.games.filter((b) => b.owned && b.cover_url).length);
    expect(signs[0].expires).toBe(3600);
    const tile = $(`[data-k="b-${game.id}"]`);
    expect(tile.querySelector('img').getAttribute('src')).toBe(`${game.cover_url}&authSig=t3600`);
    expect(tile.querySelector('.hkl-cover-badge').textContent).toBe('Custom cover');
    const plain = $$('.hkl-tile .hkl-cover:not([data-cover])');
    expect(plain.length).toBeGreaterThan(0);
    expect(plain[0].querySelector('img')).toBeNull();
  });

  it('shows the title block when the sign fails', async () => {
    const state = fixture();
    const game = state.games.find((b) => b.title === 'Piranesi');
    await mount(`/games/${game.id}`, { replies: { 'auth/sign_path': () => Promise.reject(new Error('no')) } });
    const block = $('.hkl-cover-large');
    expect(block.dataset.cover).toBe(game.cover_url);
    expect(block.querySelector('img')).toBeNull();
    expect(block.querySelector('.hkl-cover-title').textContent).toBe('Piranesi');
  });

  it('puts the reader marks in their own row and shows the ring colors in the legend', async () => {
    const state = fixture();
    const game = state.games.find((b) => b.title === 'The Left Hand of Darkness');
    await mount('/games');
    const tile = $(`[data-k="b-${game.id}"]`);
    const dots = tile.querySelectorAll('.hkl-tile-readers .hkl-dot');
    expect([...dots].map((d) => d.getAttribute('aria-label'))).toEqual(['Alex: Playing', 'Sam: Playing']);
    expect(tile.querySelector('.hkl-tile-meta .hkl-dot')).toBeNull();
    expect(dots[0].style.getPropertyValue('--p')).not.toBe(dots[1].style.getPropertyValue('--p'));
    expect($$('.hkl-legend .hkl-ring').map((r) => r.className)).toEqual(['hkl-ring ring-completed', 'hkl-ring ring-playing']);
  });
});

describe('game detail', () => {
  it('shows the location, the loan and the task link', async () => {
    const state = fixture();
    await mount(`/games/${gameId(state, 'The Left Hand of Darkness')}`);
    expect($('h1').textContent).toBe('The Left Hand of Darkness');
    expect(text()).toContain('Living room › Unit A › Shelf 2');
    expect(text()).toContain('Priya · since Sep 12, 2026');
    const task = state.loans.find((l) => l.party === 'Priya' && l.game_id === gameId(state, 'The Left Hand of Darkness')).hk_task_id;
    expect(task).toMatch(/^[0-9a-f]{32}$/);
    expect($('.hkl-task').getAttribute('href')).toBe(`/home-keeper/tasks/${task}`);
    expect(host.taskLink).toHaveBeenCalledWith(task);
    expect(text()).toContain('Completed on Mar 2, 2025 · Completed 2 times');
    expect(text()).toContain('Switch 2 Playing');
    expect(text()).toContain('Hainish Cycle');
    expect($('[data-k="rs-completed"]').getAttribute('aria-pressed')).toBe('true');
    expect($$('.hkl-star.on')).toHaveLength(4);
  });

  it('shows 1 chip for each platform and edits the platform of the chip', async () => {
    const state = fixture();
    const id = gameId(state, 'The Left Hand of Darkness');
    const fake = await mount(`/games/${id}`);
    expect($$('.hkl-plat').map((c) => c.textContent)).toEqual(['Switch 2 · Completed', 'Switch · Playing']);
    expect($('[data-k="pp-switch2"]').getAttribute('aria-pressed')).toBe('true');
    expect($('[data-k="r-completion_count"]').value).toBe('2');
    $('[data-k="pp-switch"]').click();
    expect($('[data-k="pp-switch"]').getAttribute('aria-pressed')).toBe('true');
    expect($('[data-k="rs-playing"]').getAttribute('aria-pressed')).toBe('true');
    expect($('[data-k="r-playtime_minutes"]').value).toBe('95');
    change($('[data-k="r-last_played_at"]'), '2026-10-04');
    await flush();
    expect(fake.calls('set_progress')[0]).toMatchObject({ game_id: id, person_id: ALEX, platform: 'switch', last_played_at: '2026-10-04' });
    change($('[data-k="pp-add"]'), 'pc');
    expect($('[data-k="pp-pc"]').getAttribute('aria-pressed')).toBe('true');
    expect($$('[data-act="set-status"][aria-pressed="true"]')).toHaveLength(0);
    expect($('[data-k="progress-clear"]')).toBeNull();
    $('[data-k="pp-switch"]').click();
    $('[data-k="progress-clear"]').click();
    await flush();
    expect(fake.calls('set_progress')[1]).toMatchObject({ game_id: id, platform: 'switch', play_status: 'none' });
  });

  it('opens the task with host.openTask, or leaves the link to the browser', async () => {
    const state = fixture();
    await mount(`/games/${gameId(state, 'The Left Hand of Darkness')}`);
    const link = $('.hkl-task');
    const plain = new MouseEvent('click', { bubbles: true, cancelable: true, composed: true });
    link.dispatchEvent(plain);
    expect(plain.defaultPrevented).toBe(false);
    host.openTask = vi.fn();
    const click = new MouseEvent('click', { bubbles: true, cancelable: true, composed: true });
    $('.hkl-task').dispatchEvent(click);
    expect(click.defaultPrevented).toBe(true);
    expect(host.openTask).toHaveBeenCalledWith(link.dataset.id);
    expect(host.navigate).not.toHaveBeenCalled();
  });

  it('sets the status, the rating and the play time for the person', async () => {
    const state = fixture();
    const id = gameId(state, 'The Lathe of Heaven');
    const platform = state.copies.find((c) => c.game_id === id).platform;
    const fake = await mount(`/games/${id}`);
    $('[data-k="rs-playing"]').click();
    await flush();
    const [msg] = fake.calls('set_progress');
    expect(msg).toMatchObject({ game_id: id, person_id: ALEX, platform, play_status: 'playing' });
    expect(msg.started_at).toMatch(/^\d{4}-\d\d-\d\d$/);
    $('[data-k="star-3"]').click();
    await flush();
    expect(fake.calls('set_progress')[1]).toMatchObject({ game_id: id, platform, rating: 3 });
    change($('[data-k="r-playtime_minutes"]'), '42');
    await flush();
    expect(fake.calls('set_progress')[2]).toMatchObject({ playtime_minutes: 42 });
  });

  it('sets the status of another person', async () => {
    const state = fixture();
    const id = gameId(state, 'Dune');
    const fake = await mount(`/games/${id}`);
    change($('[data-k="rp"]'), SAM);
    $('[data-k="rs-completed"]').click();
    await flush();
    expect(fake.calls('set_progress')[0]).toMatchObject({ person_id: SAM, play_status: 'completed', completion_count: 1 });
  });

  it('returns a loan', async () => {
    const state = fixture();
    const fake = await mount(`/games/${gameId(state, 'The Left Hand of Darkness')}`);
    $('[data-act="return-loan"]').click();
    await flush();
    expect(fake.calls('return_loan')).toEqual([{ type: 'home_keeper_games/return_loan', loan_id: expect.any(String) }]);
    expect(host.showToast).toHaveBeenCalledWith('Book returned.');
  });

  it('deletes after the confirmation and goes back to the list', async () => {
    const state = fixture();
    const id = gameId(state, 'Dune');
    const fake = await mount(`/games/${id}`);
    $('[data-k="delete-game"]').click();
    expect(el.shadowRoot.getElementById('dlg').textContent).toContain('Delete "Dune"');
    $('[data-k="d-submit"]').click();
    await flush();
    expect(fake.calls('delete_game')[0]).toMatchObject({ game_id: id });
    expect(host.navigate).toHaveBeenLastCalledWith('/games', { replace: true });
  });

  it('shows the gone notice for a deleted game', async () => {
    await mount('/games/nope');
    expect(text()).toContain('This game is not in the library.');
  });

  it('saves the shared notes', async () => {
    const state = fixture();
    const id = gameId(state, 'Dune');
    const fake = await mount(`/games/${id}`);
    $('[data-k="notes-edit"]').click();
    $('[data-k="notes-text"]').value = '**Good**';
    $('[data-k="notes-save"]').click();
    await flush();
    expect(fake.calls('update_game')[0]).toMatchObject({ game_id: id, shared_notes: '**Good**' });
  });

  it('edits the game from the dialog', async () => {
    const state = fixture();
    const id = gameId(state, 'Dune');
    const fake = await mount(`/games/${id}`);
    $('[data-k="edit-game"]').click();
    const dlg = el.shadowRoot.getElementById('dlg');
    dlg.querySelector('[name="genres"]').value = 'Strategy, Classic';
    dlg.querySelector('[name="franchise"]').value = 'Dune';
    dlg.querySelector('[data-k="d-submit"]').click();
    await flush();
    expect(fake.calls('update_game')[0]).toMatchObject({
      game_id: id,
      title: 'Dune',
      genres: ['Strategy', 'Classic'],
      franchise: 'Dune',
    });
    expect(dlg.innerHTML).toBe('');
  });

  it('adds a copy with the game fields, and a digital copy goes on no shelf', async () => {
    const state = fixture();
    const id = gameId(state, 'Dune');
    const fake = await mount(`/games/${id}`);
    expect(text()).toContain('Barcode');
    $('[data-k="add-copy"]').click();
    const dlg = el.shadowRoot.getElementById('dlg');
    const set = (name, value) => (dlg.querySelector(`[name="${name}"]`).value = value);
    expect([...dlg.querySelectorAll('[name="platform"] option')].map((o) => o.textContent)).toEqual([
      'PS5', 'PS4', 'PS3', 'Switch 2', 'Switch', 'Xbox Series', 'Xbox One', 'PC', 'Other platform',
    ]);
    set('platform', 'switch');
    set('format', 'digital');
    set('shelf_id', state.shelves[0].id);
    set('storefront', 'eShop');
    set('region', 'PAL');
    set('edition', 'Deluxe');
    set('barcode', '045496-590420');
    dlg.querySelector('[name="steelbook"]').checked = true;
    dlg.querySelector('[data-k="d-submit"]').click();
    await flush();
    expect(fake.calls('add_copy')[0]).toMatchObject({
      game_id: id,
      shelf_id: null,
      platform: 'switch',
      format: 'digital',
      storefront: 'eShop',
      region: 'PAL',
      edition: 'Deluxe',
      steelbook: true,
      barcode: '045496590420',
    });
  });

  it('refuses a bad copy barcode', async () => {
    const state = fixture();
    const fake = await mount(`/games/${gameId(state, 'Dune')}`);
    $('[data-k="add-copy"]').click();
    const dlg = el.shadowRoot.getElementById('dlg');
    dlg.querySelector('[name="barcode"]').value = 'b#d';
    dlg.querySelector('[data-k="d-submit"]').click();
    await flush();
    expect(dlg.querySelector('.hkl-error').textContent).toBe('This is not a valid barcode.');
    expect(fake.calls('add_copy')).toHaveLength(0);
  });

  it('shows the error of a failed dialog inline and keeps what the user typed', async () => {
    const state = fixture();
    let n = 0;
    await mount(`/games/${gameId(state, 'Dune')}`, { replies: { update_game: () => Promise.reject({ message: `Not allowed ${++n}` }) } });
    $('[data-k="edit-game"]').click();
    const dlg = el.shadowRoot.getElementById('dlg');
    dlg.querySelector('[name="franchise"]').value = 'Typed text';
    dlg.querySelector('[data-k="d-submit"]').click();
    await flush();
    expect(dlg.querySelectorAll('.hkl-error')).toHaveLength(1);
    expect(dlg.querySelector('.hkl-error').textContent).toBe('Not allowed 1');
    expect(dlg.querySelector('[name="franchise"]').value).toBe('Typed text');
    expect(dlg.querySelector('[data-k="d-submit"]').disabled).toBe(false);
    dlg.querySelector('[data-k="d-submit"]').click();
    await flush();
    expect([...dlg.querySelectorAll('.hkl-error')].map((e) => e.textContent)).toEqual(['Not allowed 2']);
  });

  it('disables the submit button while the call runs, and a late reply leaves a new dialog open', async () => {
    const state = fixture();
    let finish;
    await mount(`/games/${gameId(state, 'Dune')}`, { replies: { update_game: () => new Promise((r) => (finish = r)) } });
    $('[data-k="edit-game"]').click();
    const dlg = el.shadowRoot.getElementById('dlg');
    dlg.querySelector('[data-k="d-submit"]').click();
    await flush();
    expect(dlg.querySelector('[data-k="d-submit"]').disabled).toBe(true);
    dlg.querySelector('[data-k="d-x"]').click();
    expect(dlg.innerHTML).toBe('');
    $('[data-k="edit-game"]').click();
    finish({});
    await flush();
    expect(dlg.querySelector('[data-k="d-submit"]').disabled).toBe(false);
  });

  it('keeps the notes editor open with the text when the save fails', async () => {
    const state = fixture();
    const id = gameId(state, 'Dune');
    await mount(`/games/${id}`, { replies: { update_game: () => Promise.reject({ message: 'No' }) } });
    $('[data-k="notes-edit"]').click();
    $('[data-k="notes-text"]').value = 'Kept';
    $('[data-k="notes-save"]').click();
    await flush();
    expect($('[data-k="notes-text"]').value).toBe('Kept');
    expect(host.showToast).toHaveBeenCalledWith('No');
  });

  it('shows the stored status again when a change fails', async () => {
    const state = fixture();
    const id = gameId(state, 'The Lathe of Heaven');
    await mount(`/games/${id}`, { replies: { set_progress: () => Promise.reject({ message: 'No' }) } });
    const time = $('[data-k="r-playtime_minutes"]');
    const before = time.value;
    change(time, '42');
    await flush();
    expect($('[data-k="r-playtime_minutes"]').value).toBe(before);
  });
});

describe('shelves, loans, wishlist and settings', () => {
  it('draws a spine for each game on a shelf', async () => {
    await mount('/shelves');
    const shelf = $$('.hkl-shelf')[1];
    expect(shelf.querySelector('.hkl-shelf-name').textContent).toBe('Shelf 2');
    expect(shelf.querySelectorAll('.hkl-spine')).toHaveLength(7);
    expect(text()).toContain('No shelf: 2 copies');
  });

  it('adds a unit with shelves', async () => {
    const fake = await mount('/shelves', { replies: { add_unit: { id: 'newcase' } } });
    $('[data-act="add-unit"]').click();
    const dlg = el.shadowRoot.getElementById('dlg');
    dlg.querySelector('[name="name"]').value = 'Case C';
    dlg.querySelector('[name="shelves"]').value = '2';
    dlg.querySelector('[data-k="d-submit"]').click();
    await flush(10);
    expect(fake.calls('add_unit')[0]).toMatchObject({ name: 'Case C', room_id: expect.any(String) });
    expect(fake.calls('add_shelf').map((m) => [m.unit_id, m.name])).toEqual([
      ['newcase', 'Shelf 1'],
      ['newcase', 'Shelf 2'],
    ]);
  });

  it('lists the loans of each tab', async () => {
    await mount('/loans');
    expect($$('.hkl-listrow')).toHaveLength(3);
    expect($('[data-k="lt-in"]').textContent).toContain('2');
    await mount('/loans;tab=in');
    expect(text()).toContain('Seattle Public Library · Alex · Physical · Playing');
  });

  it('lends a copy with a task', async () => {
    const fake = await mount('/loans');
    $('[data-k="lend-game"]').click();
    const dlg = el.shadowRoot.getElementById('dlg');
    dlg.querySelector('[name="party"]').value = 'Priya';
    dlg.querySelector('[name="due"]').value = '2026-11-04';
    dlg.querySelector('[data-k="d-submit"]').click();
    await flush();
    expect(fake.calls('lend_game')[0]).toMatchObject({ party: 'Priya', due: '2026-11-04', add_task: true, copy_id: expect.any(String) });
  });

  it('adds a borrowed game by barcode', async () => {
    const fake = await mount('/loans');
    $('[data-k="add-borrowed"]').click();
    const dlg = el.shadowRoot.getElementById('dlg');
    dlg.querySelector('[name="query"]').value = '978-0-441-47812-5';
    dlg.querySelector('[name="party"]').value = 'Library';
    dlg.querySelector('[data-k="d-submit"]').click();
    await flush();
    expect(fake.calls('borrow_game')[0]).toMatchObject({ barcode: '9780441478125', party: 'Library', person_id: ALEX });
    expect(fake.calls('borrow_game')[0].title).toBeUndefined();
  });

  it('sets Buy on a wishlist game', async () => {
    const fake = await mount('/wishlist');
    expect($$('.hkl-listrow')).toHaveLength(4);
    const box = $('[data-chg="wish-buy"]:not(:checked)');
    change(box, true);
    await flush();
    expect(fake.calls('update_wishlist')[0]).toMatchObject({ game_id: box.dataset.id, buy: true });
  });

  it('saves the person settings', async () => {
    const fake = await mount('/settings', { replies: { list_todo_entities: { entities: [{ entity_id: 'todo.books', name: 'Games list' }] } } });
    await flush();
    expect(fake.calls('list_todo_entities')).toHaveLength(1);
    expect($$('[data-key="wishlist_todo"] option').map((o) => o.textContent)).toContain('Games list');
    change($(`[data-k="pg-${ALEX}"]`), '30');
    await flush();
    expect(fake.calls('set_person_settings')[0]).toEqual({ type: 'home_keeper_games/set_person_settings', person_id: ALEX, yearly_goal: 30 });
  });
});

describe('settings currency', () => {
  it('saves a new currency code with set_settings', async () => {
    const fake = await mount('/settings');
    const input = $('[data-k="currency"]');
    expect(input.value).toBe('EUR');
    input.value = 'usd';
    $('[data-k="currency-save"]').click();
    await flush();
    expect(fake.calls('set_settings')).toEqual([{ type: 'home_keeper_games/set_settings', currency: 'USD' }]);
    expect(host.showToast).toHaveBeenCalledWith('Settings saved.');
  });

  it('refuses a code that is not 3 letters and sends nothing for the same code', async () => {
    const fake = await mount('/settings');
    $('[data-k="currency"]').value = 'EU';
    $('[data-k="currency-save"]').click();
    await flush();
    expect(host.showToast).toHaveBeenCalledWith('Type a currency code of 3 letters.');
    $('[data-k="currency"]').value = ' eur ';
    $('[data-k="currency-save"]').click();
    await flush();
    expect(fake.calls('set_settings')).toEqual([]);
  });
});

describe('scan', () => {
  beforeEach(() => {
    Object.defineProperty(window, 'isSecureContext', { value: false, configurable: true });
  });

  it('blocks the camera on a page that is not HTTPS, and Enter barcode still starts', async () => {
    const state = fixture();
    const shelf = Object.values(state.shelves)[0].id;
    await mount(`/scan;shelf=${shelf}`);
    expect(text()).toContain('Scan into Shelf 1');
    expect($('[data-k="m-https"]').textContent).toContain('The camera needs HTTPS.');
    expect($('[data-k="scan-start"]').disabled).toBe(true);
    expect($('[data-k="scan-start"]').getAttribute('aria-describedby')).toBe('scan-https');
    expect($('#scan-https')).toBe($('[data-k="m-https"]'));
    $('[data-k="scan-start"]').click();
    expect(host.navigate).not.toHaveBeenCalled();

    change($('[data-k="m-manual"]'), 'manual');
    await flush();
    expect($('[data-k="m-https"]')).toBeNull();
    expect($('[data-k="scan-start"]').disabled).toBe(false);
    $('[data-k="scan-start"]').click();
    expect(host.navigate).toHaveBeenLastCalledWith(`/scan;shelf=${shelf};step=camera`, { replace: false });
    await flush();
    expect($('[data-k="barcode-input"]')).not.toBeNull();
  });

  it('shows the HTTPS message on the camera step of a page that is not HTTPS', async () => {
    const state = fixture();
    await mount(`/scan;shelf=${Object.values(state.shelves)[0].id};step=camera`);
    await flush();
    expect(text()).toContain('The camera needs HTTPS.');
    expect($('[data-k="barcode-input"]')).not.toBeNull();
  });

  it('lets the camera start on an HTTPS page', async () => {
    Object.defineProperty(window, 'isSecureContext', { value: true, configurable: true });
    const state = fixture();
    await mount(`/scan;shelf=${Object.values(state.shelves)[0].id}`);
    expect($('[data-k="m-https"]')).toBeNull();
    expect($('[data-k="scan-start"]').disabled).toBe(false);
  });

  it('scans a barcode and resolves a duplicate', async () => {
    const state = fixture();
    const shelf = Object.values(state.shelves)[0].id;
    const dune = Object.values(state.games).find((b) => b.title === 'Dune');
    const copies = Object.values(state.copies).filter((c) => c.game_id === dune.id);
    const fake = await mount(`/scan;shelf=${shelf};step=camera`, {
      replies: {
        scan_barcode: (m) =>
          m.on_duplicate === 'ask'
            ? { result: 'duplicate', game: dune, copy: null, existing_copies: copies }
            : { result: 'moved', game: dune, copy: copies[0], existing_copies: copies },
      },
    });
    const input = $('[data-k="barcode-input"]');
    input.value = 'b#d';
    $('[data-k="barcode-add"]').click();
    expect(host.showToast).toHaveBeenCalledWith('This is not a valid barcode.');
    $('[data-k="barcode-input"]').value = DUNE_CODE;
    $('[data-k="barcode-add"]').click();
    await flush();
    expect(fake.calls('scan_barcode')[0]).toMatchObject({
      barcode: DUNE_CODE,
      shelf_id: shelf,
      platform: 'other',
      format: 'physical',
      on_duplicate: 'ask',
    });
    expect(text()).toContain('Already in Living room › Unit A › Shelf 1');
    $('[data-value="move"]').click();
    await flush();
    expect(fake.calls('scan_barcode')[1]).toMatchObject({ on_duplicate: 'move' });
    expect(text()).toContain('Moved here');
    expect(text()).toContain('Added to this shelf: 1');
    $('[data-k="scan-done"]').click();
    expect(text()).toContain('Scan summary');
    expect($$('.hkl-stat b').map((b) => b.textContent)).toEqual(['0', '1', '0']);
  });

  it('keeps a typed barcode when a store change renders the view', async () => {
    const state = fixture();
    const fake = await mount(`/scan;shelf=${state.shelves[0].id};step=camera`);
    const input = $('[data-k="barcode-input"]');
    input.focus();
    input.value = '978044';
    fake.push();
    await flush();
    const now = $('[data-k="barcode-input"]');
    expect(now).not.toBe(input);
    expect(now.value).toBe('978044');
    expect(el.shadowRoot.activeElement).toBe(now);
  });

  it('marks a scanned game that comes from the wishlist', async () => {
    const state = fixture();
    const shelf = state.shelves[0].id;
    const wished = state.games.find((b) => b.title === 'The Other Wind');
    const dune = state.games.find((b) => b.title === 'Dune');
    const fake = await mount(`/scan;shelf=${shelf};step=camera`, {
      replies: {
        scan_barcode: (m) =>
          m.barcode === WISHED_CODE
            ? { result: 'added', game: wished, copy: null, existing_copies: [], from_wishlist: true }
            : { result: 'added', game: dune, copy: null, existing_copies: [] },
      },
    });
    void fake;
    for (const code of [WISHED_CODE, DUNE_CODE]) {
      $('[data-k="barcode-input"]').value = code;
      $('[data-k="barcode-add"]').click();
      await flush();
    }
    const rows = $$('.hkl-result');
    const wishRow = rows.find((r) => r.textContent.includes('The Other Wind'));
    const duneRow = rows.find((r) => r.textContent.includes('Dune'));
    expect(wishRow.querySelector('[data-k^="from-wish-"]').textContent).toBe('From wishlist');
    expect(wishRow.querySelector('.hkl-pill.ok').textContent).toBe('Added');
    expect(duneRow.querySelector('[data-k^="from-wish-"]')).toBeNull();
  });

  it('sets Completed for me on the scanned games when the box is set', async () => {
    const state = fixture();
    const shelf = Object.values(state.shelves)[0].id;
    const dune = Object.values(state.games).find((b) => b.title === 'Dune');
    const fake = await mount(`/scan;shelf=${shelf};step=camera`, {
      replies: { scan_barcode: { result: 'added', game: dune, copy: null, existing_copies: [] } },
    });
    $('[data-k="barcode-input"]').value = DUNE_CODE;
    $('[data-k="barcode-add"]').click();
    await flush();
    $('[data-k="scan-done"]').click();
    change($('[data-k="markread"]'), true);
    $('[data-k="scan-finish"]').click();
    await flush();
    expect(fake.calls('set_progress')[0]).toMatchObject({ game_id: dune.id, person_id: ALEX, play_status: 'completed' });
  });
});

describe('scan with no match', () => {
  beforeEach(() => {
    Object.defineProperty(window, 'isSecureContext', { value: false, configurable: true });
  });

  /** A game that a scan of a new barcode saved: its barcode is its title. */
  function missing(state, code, id) {
    const shelf = state.shelves[0].id;
    const game = { ...state.games[0], id, title: code, franchise: null, genres: [], release_date: '', needs_details: true, cover: null };
    const copy = { ...state.copies[0], id: `c-${id}`, game_id: id, shelf_id: shelf, platform: 'other', format: 'physical', barcode: code };
    state.games.push(game);
    state.copies.push(copy);
    return { game, copy, reply: { result: 'not_found', game, copy, existing_copies: [] } };
  }

  async function scan(code) {
    $('[data-k="barcode-input"]').value = code;
    $('[data-k="barcode-add"]').click();
  }

  const sheet = () => $('.hkl-dialog.sheet');

  function typeTitle(value) {
    const input = sheet().querySelector('[name="title"]');
    input.value = value;
    input.dispatchEvent(new Event('input', { bubbles: true }));
  }

  it('asks for the title before the next scan, and saves only the title', async () => {
    const state = fixture();
    const miss = missing(state, '9781402894626', 'new');
    const fake = await mount(`/scan;shelf=${state.shelves[0].id};step=camera`, {
      state,
      replies: {
        scan_barcode: miss.reply,
        update_game: (m) => {
          miss.game.title = m.title;
          return { game: miss.game };
        },
      },
    });
    await scan(miss.copy.barcode);
    await flush();
    expect(sheet()).not.toBeNull();
    expect(sheet().querySelector('h2').textContent).toBe('No book has this barcode');
    expect(sheet().querySelector('[data-k="d-barcode"]').textContent).toBe('Barcode 9781402894626');
    expect(sheet().querySelector('[data-k="d-x"]')).toBeNull();
    expect(sheet().querySelector('[data-k="d-cancel"]')).toBeNull();
    expect(sheet().querySelector('[data-k="d-more"]').open).toBe(false);
    const submit = sheet().querySelector('[data-k="d-submit"]');
    expect(submit.textContent).toBe('Save and scan next');
    expect(submit.disabled).toBe(true);
    expect(el.shadowRoot.activeElement).toBe(sheet().querySelector('[name="title"]'));

    // Escape, a click on the scrim and a new scan do not close the sheet.
    sheet().dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, composed: true }));
    $('.hkl-scrim').click();
    await scan('9780441478125');
    await flush();
    expect(sheet()).not.toBeNull();
    expect(fake.calls('scan_barcode')).toHaveLength(1);

    typeTitle('  ');
    expect(submit.disabled).toBe(true);
    typeTitle('Field Notes on Moss');
    expect(submit.disabled).toBe(false);
    submit.click();
    await flush();
    const calls = fake.calls('update_game');
    expect(calls).toHaveLength(1);
    expect(calls[0]).toEqual({ type: 'home_keeper_games/update_game', game_id: 'new', title: 'Field Notes on Moss' });
    expect(fake.calls('update_copy')).toHaveLength(0);
    expect(fake.calls('set_cover')).toHaveLength(0);
    expect(sheet()).toBeNull();
    expect(el.shadowRoot.activeElement).toBe($('[data-k="barcode-input"]'));
    const row = $$('.hkl-result').find((r) => r.textContent.includes('Field Notes on Moss'));
    expect(row.textContent).toContain('No book has this barcode');

    // The scan goes on.
    await scan('9780441478125');
    await flush();
    expect(fake.calls('scan_barcode')).toHaveLength(2);
  });

  it('shows the error of an empty title and keeps the sheet open', async () => {
    const state = fixture();
    const miss = missing(state, '9781402894626', 'new');
    const fake = await mount(`/scan;shelf=${state.shelves[0].id};step=camera`, { state, replies: { scan_barcode: miss.reply } });
    await scan(miss.copy.barcode);
    await flush();
    sheet().dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
    await flush();
    expect(sheet().querySelector('.hkl-error').textContent).toBe('Type the title.');
    expect(fake.calls('update_game')).toHaveLength(0);
  });

  it('keeps the sheet open with the error when a save call fails', async () => {
    const state = fixture();
    const miss = missing(state, '9781402894626', 'new');
    const fake = await mount(`/scan;shelf=${state.shelves[0].id};step=camera`, {
      state,
      replies: {
        scan_barcode: miss.reply,
        update_copy: () => {
          throw { code: 'home_assistant_error', message: 'Copy save failed' };
        },
      },
    });
    await scan(miss.copy.barcode);
    await flush();
    typeTitle('Field Notes on Moss');
    sheet().querySelector('[name="format"]').value = 'digital';
    sheet().querySelector('[data-k="d-submit"]').click();
    await flush();
    expect(fake.calls('update_game')).toHaveLength(1);
    expect(sheet()).not.toBeNull();
    expect(sheet().querySelector('.hkl-error').textContent).toContain('Copy save failed');
    expect(sheet().querySelector('[name="title"]').value).toBe('Field Notes on Moss');
    // The scan stays paused.
    await scan('9780441478125');
    await flush();
    expect(fake.calls('scan_barcode')).toHaveLength(1);
  });

  it('saves the details that the user adds', async () => {
    const state = fixture();
    const miss = missing(state, '9781402894626', 'new');
    const fake = await mount(`/scan;shelf=${state.shelves[0].id};step=camera`, { state, replies: { scan_barcode: miss.reply } });
    await scan(miss.copy.barcode);
    await flush();
    sheet().querySelector('[data-k="d-more-toggle"]').click();
    expect(sheet().querySelector('[data-k="d-more"]').open).toBe(true);
    expect(sheet().querySelector('[data-k="d-cover"]').getAttribute('capture')).toBe('environment');
    typeTitle('Field Notes on Moss');
    const set = (name, value) => (sheet().querySelector(`[name="${name}"]`).value = value);
    set('franchise', 'Moss');
    set('genres', 'Puzzle, Casual');
    set('release_date', '2004');
    set('format', 'digital');
    set('platform', 'switch');
    sheet().querySelector('[data-k="d-submit"]').click();
    await flush();
    expect(fake.calls('update_game')[0]).toEqual({
      type: 'home_keeper_games/update_game',
      game_id: 'new',
      title: 'Field Notes on Moss',
      franchise: 'Moss',
      release_date: '2004',
      genres: ['Puzzle', 'Casual'],
    });
    expect(fake.calls('update_copy')[0]).toEqual({ type: 'home_keeper_games/update_copy', copy_id: 'c-new', format: 'digital', platform: 'switch' });
    expect(sheet()).toBeNull();
  });

  it('removes a scan, then asks for the next game with no match', async () => {
    const state = fixture();
    const first = missing(state, '9781402894626', 'one');
    const second = missing(state, '9780306406157', 'two');
    const fake = await mount(`/scan;shelf=${state.shelves[0].id};step=camera`, {
      state,
      replies: { scan_barcode: (m) => (m.barcode === first.copy.barcode ? first.reply : second.reply) },
    });
    // The 2nd scan starts while the lookup of the 1st one runs.
    void scan(first.copy.barcode);
    void scan(second.copy.barcode);
    await flush();
    expect(fake.calls('scan_barcode')).toHaveLength(2);
    expect(sheet().querySelector('[data-k="d-barcode"]').textContent).toBe('Barcode 9781402894626');
    const remove = sheet().querySelector('[data-k="d-remove"]');
    expect(remove.textContent).toBe('Remove this scan');
    remove.click();
    await flush();
    expect(fake.calls('delete_game')).toEqual([{ type: 'home_keeper_games/delete_game', game_id: 'one' }]);
    expect(sheet().querySelector('[data-k="d-barcode"]').textContent).toBe('Barcode 9780306406157');
    expect($$('[data-k^="removed-"]').map((p) => p.textContent)).toEqual(['Removed']);

    typeTitle('Second game');
    sheet().querySelector('[data-k="d-submit"]').click();
    await flush();
    expect(sheet()).toBeNull();
    $('[data-k="scan-done"]').click();
    expect($$('.hkl-stat b').map((b) => b.textContent)).toEqual(['0', '0', '1']);
  });

  it('goes on with the scan after the title, with no catalog call', async () => {
    const state = fixture();
    const miss = missing(state, '9781402894626', 'new');
    const fake = await mount(`/scan;shelf=${state.shelves[0].id};step=camera`, {
      state,
      replies: { scan_barcode: miss.reply },
    });
    await scan(miss.copy.barcode);
    await flush();
    typeTitle('Field Notes on Moss');
    sheet().querySelector('[data-k="d-submit"]').click();
    await flush();
    expect(fake.calls('search_catalog')).toEqual([]);
    expect(fake.calls('link_catalog')).toEqual([]);
    expect($('.hkl-dialog')).toBeNull();
    expect(el.shadowRoot.activeElement).toBe($('[data-k="barcode-input"]'));
  });

  it('closes the sheet when the user leaves the scan', async () => {
    const state = fixture();
    const miss = missing(state, '9781402894626', 'new');
    await mount(`/scan;shelf=${state.shelves[0].id};step=camera`, { state, replies: { scan_barcode: miss.reply } });
    await scan(miss.copy.barcode);
    await flush();
    expect(sheet()).not.toBeNull();
    el.route = { path: '/games' };
    await flush();
    expect(sheet()).toBeNull();
  });
});

describe('scan camera', () => {
  let cam;

  /** A fake camera, a fake `BarcodeDetector` and a video `play()` that the test controls. */
  beforeEach(() => {
    Object.defineProperty(window, 'isSecureContext', { value: true, configurable: true });
    cam = { gum: 0, refuse: false, frozen: false, paused: new WeakMap(), tracks: [] };
    const track = () => {
      const t = new EventTarget();
      Object.assign(t, { readyState: 'live', muted: false, enabled: true, stop: () => (t.readyState = 'ended'), getCapabilities: () => ({}) });
      cam.tracks.push(t);
      return t;
    };
    Object.defineProperty(navigator, 'mediaDevices', {
      configurable: true,
      value: {
        getUserMedia: async () => {
          cam.gum++;
          const t = track();
          return { getVideoTracks: () => [t], getTracks: () => [t] };
        },
      },
    });
    window.BarcodeDetector = class {
      static async getSupportedFormats() {
        return ['ean_13'];
      }
      async detect() {
        return [];
      }
    };
    vi.spyOn(HTMLMediaElement.prototype, 'paused', 'get').mockImplementation(function () {
      return cam.paused.get(this) ?? true;
    });
    // The video has a frame, and its time moves, unless the test freezes the picture.
    vi.spyOn(HTMLMediaElement.prototype, 'readyState', 'get').mockReturnValue(4);
    vi.spyOn(HTMLMediaElement.prototype, 'currentTime', 'get').mockImplementation(() => (cam.frozen ? 1 : performance.now() / 1000));
    vi.spyOn(HTMLMediaElement.prototype, 'play').mockImplementation(function () {
      if (cam.refuse) return Promise.reject(new DOMException('no gesture', 'NotAllowedError'));
      cam.paused.set(this, false);
      this.dispatchEvent(new Event('playing'));
      return Promise.resolve();
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
    delete window.BarcodeDetector;
  });

  const video = () => $('[data-slot="video"] video');
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));

  /** The browser pauses the video, as Home Keeper or the system can do. */
  function pause(v) {
    cam.paused.set(v, true);
    v.dispatchEvent(new Event('pause'));
  }

  it('keeps the video in the page when a scan renders the view', async () => {
    const state = fixture();
    const dune = state.games.find((b) => b.title === 'Dune');
    const fake = await mount(`/scan;shelf=${state.shelves[0].id};step=camera`, {
      replies: { scan_barcode: { result: 'added', game: dune, copy: null, existing_copies: [] } },
    });
    const v = video();
    const slot = v.parentNode;
    expect(v.paused).toBe(false);
    $('[data-k="scan-manual"]').click();
    $('[data-k="barcode-input"]').value = DUNE_CODE;
    $('[data-k="barcode-add"]').click();
    fake.push();
    await flush();
    expect(text()).toContain('Added to this shelf: 1');
    // The slot and its video never left the page, so the browser did not pause the video.
    expect($('[data-slot="video"]')).toBe(slot);
    expect(video()).toBe(v);
    expect(cam.gum).toBe(1);
  });

  it('shows the restart button when the browser refuses play(), and a tap plays again', async () => {
    const state = fixture();
    await mount(`/scan;shelf=${state.shelves[0].id};step=camera`);
    const v = video();
    cam.refuse = true;
    pause(v);
    await wait(900);
    expect($('[data-k="cam-restart"]').textContent).toBe('The camera stopped. Tap to start it again.');
    cam.refuse = false;
    $('[data-k="cam-restart"]').click();
    await wait(900);
    expect($('[data-k="cam-restart"]')).toBeNull();
    expect(video()).toBe(v);
    expect(v.paused).toBe(false);
    expect(cam.gum).toBe(1);
  });

  it('does not show the restart button for a short pause', async () => {
    const state = fixture();
    await mount(`/scan;shelf=${state.shelves[0].id};step=camera`);
    const v = video();
    pause(v);
    await v.play();
    await wait(900);
    expect($('[data-k="cam-restart"]')).toBeNull();
  });

  it('starts a new camera on a tap when the camera track ended', async () => {
    const state = fixture();
    await mount(`/scan;shelf=${state.shelves[0].id};step=camera`);
    const first = video();
    cam.tracks[0].readyState = 'ended';
    cam.tracks[0].dispatchEvent(new Event('ended'));
    await wait(900);
    $('[data-k="cam-restart"]').click();
    await flush();
    expect(cam.gum).toBe(2);
    expect(video()).not.toBe(first);
    expect($('[data-k="cam-restart"]')).toBeNull();
  });

  it('starts a new camera on a tap when the picture is frozen', async () => {
    const state = fixture();
    await mount(`/scan;shelf=${state.shelves[0].id};step=camera`);
    const first = video();
    cam.frozen = true;
    await wait(1400);
    expect($('[data-k="cam-restart"]')).toBeNull();
    await wait(1400);
    expect($('[data-k="cam-restart"]')).not.toBeNull();
    expect(first.paused).toBe(false);
    cam.frozen = false;
    $('[data-k="cam-restart"]').click();
    await flush();
    expect(cam.gum).toBe(2);
    expect(video()).not.toBe(first);
    expect($('[data-k="cam-restart"]')).toBeNull();
  });

  it('shows the camera state and log in the debug view only with ;debug=1', async () => {
    const state = fixture();
    await mount(`/scan;shelf=${state.shelves[0].id};step=camera`);
    expect($('[data-k="cam-debug"]')).toBeNull();
    el.route = { path: `/scan;shelf=${state.shelves[0].id};step=camera;debug=1` };
    await flush();
    const dbg = $('[data-k="cam-debug"]').textContent;
    expect(dbg).toMatch(/^tab \d+ of \d+: in page=true/);
    expect(dbg).toContain('video: paused=false frozen=false');
    expect(dbg).toContain('track: live muted=false');
    expect(dbg).toContain('detector: native');
    expect(dbg).toContain('getUserMedia ok');
  });
});

describe('import', () => {
  function pick(name, content) {
    const input = $('[data-k="im-file"]');
    const file = new File([content], name, { type: 'text/csv' });
    Object.defineProperty(input, 'files', { value: [file] });
    input.dispatchEvent(new Event('change', { bubbles: true }));
  }

  it('shows the result of each row and says when the list is cut', async () => {
    const summary = {
      dry_run: true,
      counts: { rows: 900, read: 3, existing: 1, new: 1, title_match: 1, errors: 1 },
      rows: [
        { line: 2, title: 'Piranesi', authors: ['Susanna Clarke'], barcode: '9781635575637', game_id: 'b1', action: 'existing', message: '' },
        { line: 3, title: 'Dune', authors: ['Frank Herbert'], barcode: null, game_id: 'b2', action: 'title_match', message: '' },
        { line: 4, title: '', authors: [], barcode: null, game_id: null, action: 'error', message: 'The row has no title.' },
      ],
      truncated: true,
    };
    await mount('/import', { replies: { import_csv: summary } });
    pick('games-export.csv', 'title\nA\n');
    await flush(10);
    const cells = $$('.hkl-details tr').map((r) => r.lastElementChild.textContent);
    expect(cells).toEqual(['In the library', 'Title match', 'The row has no title.']);
    expect($('[data-k="import-truncated"]').textContent).toBe('The list shows only part of the file. The import reads all rows.');
    expect($('[data-k="import-run"]').textContent).toBe('Import 900 rows');
  });

  it('sends a file above 3 MB to the service over REST', async () => {
    const summary = { dry_run: true, counts: { rows: 1 }, rows: [], truncated: false };
    const callApi = vi.fn(async () => ({ changed_states: [], service_response: summary }));
    const fake = await mount('/import', { callApi });
    const big = `title\n${'x'.repeat(3 * 1024 * 1024)}\n`;
    pick('library.csv', big);
    await flush(10);
    expect(fake.calls('import_csv')).toEqual([]);
    expect(callApi).toHaveBeenCalledWith('POST', 'services/home_keeper_games/import_csv?return_response', expect.objectContaining({ dry_run: true, person_id: ALEX }));
    expect(callApi.mock.calls[0][2].content).toBe(big);
    expect(text()).toContain('Import 1 row');
  });

  it('runs a dry run, then the import', async () => {
    const summary = { dry_run: true, counts: { rows: 3, read: 2, wishlist: 1, existing: 1, new: 2, title_match: 0 }, rows: [], truncated: false };
    const fake = await mount('/import', { replies: { import_csv: summary } });
    expect($('#hkl-import-title').textContent).toBe('Import books');
    const input = $('[data-k="im-file"]');
    const file = new File(['title,authors\nA,B\nC,D\nE,F\n'], 'games-export.csv', { type: 'text/csv' });
    Object.defineProperty(input, 'files', { value: [file] });
    input.dispatchEvent(new Event('change', { bubbles: true }));
    await flush(10);
    expect(fake.calls('import_csv')[0]).toMatchObject({ content: 'title,authors\nA,B\nC,D\nE,F\n', person_id: ALEX, dry_run: true, import_review: true, replace_progress: false, shelf_id: null });
    expect(text()).toContain('games-export.csv · 3 rows');
    expect(text()).toContain('Already in the library: 1');
    $('[data-k="import-run"]').click();
    await flush();
    expect(fake.calls('import_csv')[1]).toMatchObject({ dry_run: false });
    expect(host.showToast).toHaveBeenCalledWith('Import complete.');
  });
});

describe('no Open Library', () => {
  it('shows no Open Library control in the games, the game and the settings views', async () => {
    const state = fixture();
    const id = gameId(state, 'Dune');
    await mount('/games');
    expect($('[data-k="st-not_on_ol"]')).toBeNull();
    expect(text()).not.toContain('Open Library');
    el.route = { path: `/games/${id}` };
    await flush();
    expect($('[data-k="ol-banner"]')).toBeNull();
    expect($('[data-k="refresh"]')).toBeNull();
    expect($('[data-k="use-ol"]')).toBeNull();
    expect(text()).not.toContain('Open Library');
    el.route = { path: '/settings' };
    await flush();
    expect($('[data-k="ol-card"]')).toBeNull();
    expect($('[data-k="ex-format"]')).toBeNull();
    expect(text()).not.toContain('Open Library');
  });
});

describe('change IGDB game', () => {
  const HIT = { igdb_id: 11, title: 'Dune', release_year: 1965, platforms: ['pc'], cover_url: 'https://images.example/t_cover_big/co1.jpg', in_library: null };
  const TAKEN = { igdb_id: 10, title: 'Dune II', release_year: null, platforms: [], cover_url: null, in_library: 'other-game' };
  const dlg = () => el.shadowRoot.getElementById('dlg');

  it('shows no IGDB button with no IGDB keys', async () => {
    const state = fixture();
    await mount(`/games/${gameId(state, 'Dune')}`, { state });
    expect($('[data-k="igdb-game"]')).toBeNull();
  });

  it('searches the title on the platform of the copies and sets the selected game', async () => {
    const state = fixture();
    state.igdb = true;
    const id = gameId(state, 'Dune');
    const platforms = [...new Set(state.copies.filter((c) => c.game_id === id).map((c) => c.platform))].filter((p) => p !== 'other');
    const fake = await mount(`/games/${id}`, { state, replies: { search_catalog: { candidates: [TAKEN, HIT] } } });
    $('[data-k="igdb-game"]').click();
    await flush();
    expect(fake.calls('search_catalog')[0]).toEqual({
      type: 'home_keeper_games/search_catalog',
      query: 'Dune',
      ...(platforms.length === 1 ? { platform: platforms[0] } : {}),
    });
    const taken = dlg().querySelector('[data-k="d-igdb-row-10"] input');
    expect(taken.disabled).toBe(true);
    expect(dlg().querySelector('[data-k="d-igdb-row-10"]').textContent).toContain('In library');
    expect(dlg().querySelector('[data-k="d-igdb-row-11"] input').checked).toBe(true);
    expect(dlg().querySelector('[data-k="d-igdb-row-11"] img').getAttribute('referrerpolicy')).toBe('no-referrer');
    expect(dlg().querySelector('[data-k="d-igdb-row-11"]').textContent).toContain('1965 · PC');
    dlg().querySelector('[data-k="d-submit"]').click();
    await flush();
    expect(fake.calls('set_igdb_game')[0]).toMatchObject({ game_id: id, igdb_id: 11 });
    expect(host.showToast).toHaveBeenCalledWith('The game has the IGDB details now.');
    expect(dlg().innerHTML).toBe('');
  });

  it('searches again on Enter, and shows an empty result, an error and a missing pick', async () => {
    const state = fixture();
    state.igdb = true;
    let reply = { candidates: [] };
    const fake = await mount(`/games/${gameId(state, 'Dune')}`, {
      state,
      replies: {
        search_catalog: () => {
          if (reply instanceof Error) throw reply;
          return reply;
        },
      },
    });
    $('[data-k="igdb-game"]').click();
    await flush();
    expect(dlg().querySelector('[data-k="d-igdb-status"]').textContent).toBe('IGDB has no game for this search.');
    const query = dlg().querySelector('[data-k="d-igdb-query"]');
    query.value = 'Dune Messiah';
    dlg().querySelector('[data-k="d-igdb-platform"]').value = '';
    reply = new Error('IGDB is not available now.');
    const enter = new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, composed: true, cancelable: true });
    query.dispatchEvent(enter);
    await flush();
    expect(enter.defaultPrevented).toBe(true);
    expect(fake.calls('search_catalog')[1]).toEqual({ type: 'home_keeper_games/search_catalog', query: 'Dune Messiah' });
    expect(dlg().querySelector('.hkl-error').textContent).toContain('IGDB is not available now.');
    expect(dlg().querySelector('[data-k="d-igdb-status"]')).toBeNull();
    dlg().querySelector('[data-k="d-submit"]').click();
    await flush();
    expect(dlg().querySelector('.hkl-error').textContent).toBe('Select a game in the list.');
    expect(fake.calls('set_igdb_game')).toEqual([]);
    dlg().querySelector('[data-k="d-igdb-query"]').value = ' ';
    dlg().querySelector('[data-k="d-igdb-search"]').click();
    await flush();
    expect(fake.calls('search_catalog')).toHaveLength(2);
  });

  it('offers IGDB in the banner of a game that needs details, and says that an upload stays', async () => {
    const state = fixture();
    state.igdb = true;
    const game = state.games.find((g) => g.needs_details);
    game.cover = { kind: 'custom', file: 'x.jpg' };
    await mount(`/games/${game.id}`, { state });
    expect($('[data-k="needs-edit"]').classList.contains('text')).toBe(true);
    $('[data-k="needs-igdb"]').click();
    await flush();
    expect(dlg().querySelector('[data-k="d-igdb-note"]').textContent).toContain('Your uploaded cover stays.');
  });
});
