// The harness script: a fake `hass`, a fake host and the fixture state.
import '../dist/games-tab.js';
import '../dist/games-card.js';

const params = new URLSearchParams(location.search);
if (params.get('theme') === 'dark') document.documentElement.classList.add('dark');
const state = await (await fetch('../test/fixtures/state.json')).json();
// get_state sends lists. The harness changes records by id.
const byId = (list, id) => list.find((r) => r.id === id);
if (params.get('admin') === '0') state.me.is_admin = false;

const listeners = new Set();
const push = () => listeners.forEach((cb) => cb({ type: 'changed', revision: Date.now() }));
const today = new Date().toISOString().slice(0, 10);

function handle(msg) {
  const cmd = msg.type.split('/')[1];
  switch (cmd) {
    case 'get_state':
      return structuredClone(state);
    case 'sign_path':
      // The harness serves no covers, so each cover shows its title block.
      throw new Error('no covers in the harness');
    case 'list_todo_entities':
      return { entities: [{ entity_id: 'todo.alex_books', name: 'Alex books' }, { entity_id: 'todo.jo_books', name: 'Jo books' }, { entity_id: 'todo.shopping_list', name: 'Shopping list' }] };
    case 'set_reading': {
      const game = byId(state.games, msg.game_id);
      const pid = msg.person_id ?? state.me.person_id;
      const row = (game.reading[pid] ??= { status: null, rating: null, page: null, started: null, finished: null, read_count: 0, private_notes: '' });
      for (const [k, v] of Object.entries(msg)) if (!['type', 'id', 'game_id', 'person_id'].includes(k)) row[k] = v;
      row.updated_at = new Date().toISOString();
      push();
      return row;
    }
    case 'return_loan':
      byId(state.loans, msg.loan_id).returned = today;
      push();
      return { loan: byId(state.loans, msg.loan_id) };
    case 'scan_barcode': {
      const found = state.games.find((b) => b.barcode === msg.barcode);
      if (found) {
        const existing = state.copies.filter((c) => c.game_id === found.id);
        if (existing.length && (!msg.on_duplicate || msg.on_duplicate === 'ask')) return { result: 'duplicate', game: found, copy: null, existing_copies: existing };
        return { result: msg.on_duplicate === 'skip' ? 'skipped' : msg.on_duplicate === 'move' ? 'moved' : 'added', game: found, copy: existing[0] ?? null, existing_copies: existing };
      }
      return { result: 'not_found', game: { id: 'new', title: msg.barcode, barcode: msg.barcode, authors: [], needs_details: true, reading: {}, cover: { kind: 'none' } }, copy: null, existing_copies: [] };
    }
    case 'import_csv':
      return {
        dry_run: Boolean(msg.dry_run),
        truncated: false,
        counts: { rows: 318, read: 201, reading: 2, want: 41, wishlist: 74, tags: 9, copies: 57, existing: 187, new: 57, title_match: 12 },
        rows: [{ line: 2, title: 'Piranesi', authors: ['Susanna Clarke'], barcode: '9781635575637', game_id: null, action: 'existing', message: '' }],
      };
    default:
      return {};
  }
}

const hass = {
  language: params.get('lang') || 'en',
  states: {
    'person.alex': { entity_id: 'person.alex', state: 'home', attributes: { id: state.me.person_id, friendly_name: 'Alex' } },
    'person.sam': { entity_id: 'person.sam', state: 'home', attributes: { id: 'sam', friendly_name: 'Sam' } },
    'person.jo': { entity_id: 'person.jo', state: 'away', attributes: { id: 'jo', friendly_name: 'Jo' } },
    'todo.alex_books': { entity_id: 'todo.alex_books', state: '2', attributes: { friendly_name: 'Alex books' } },
    'todo.jo_books': { entity_id: 'todo.jo_books', state: '1', attributes: { friendly_name: 'Jo books' } },
  },
  areas: { living_room: { area_id: 'living_room', name: 'Living Room' }, office: { area_id: 'office', name: 'Office' } },
  connection: {
    sendMessagePromise: async (msg) => handle(msg),
    subscribeMessage: async (cb) => {
      listeners.add(cb);
      return () => listeners.delete(cb);
    },
  },
};

function toast(text) {
  const el = document.getElementById('toast');
  el.textContent = text;
  el.style.display = 'block';
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => (el.style.display = 'none'), 2500);
}

const app = document.getElementById('app');
if (params.get('card') === '1') {
  app.innerHTML = '<div class="cardwrap"></div>';
  const card = document.createElement('home-keeper-games-card');
  card.setConfig({ type: 'custom:home-keeper-games-card', person: params.get('person') || undefined });
  app.firstChild.appendChild(card);
  card.hass = hass;
} else {
  app.innerHTML = '<header>Home Keeper</header><div class="tabs"><span>Tasks</span><span>Appliances</span><span class="on">Library</span><span>Settings</span></div><main></main>';
  const tab = document.createElement('home-keeper-games-tab');
  let path = params.get('path') || '/games';
  const host = {
    apiVersion: 1,
    navigate(next, opts = {}) {
      path = next;
      const url = new URL(location.href);
      url.searchParams.set('path', next);
      history[opts.replace ? 'replaceState' : 'pushState'](null, '', url);
      tab.route = { path: next };
    },
    taskLink: (id) => `/home-keeper/tasks/${id}`,
    applianceLink: (id) => `/home-keeper/appliances/${id}`,
    showToast: toast,
  };
  window.addEventListener('popstate', () => {
    tab.route = { path: new URLSearchParams(location.search).get('path') || '/games' };
  });
  tab.host = host;
  tab.narrow = innerWidth < 870;
  tab.route = { path };
  app.querySelector('main').appendChild(tab);
  tab.hass = hass;
}
