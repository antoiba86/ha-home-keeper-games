import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import '../src/card-index.ts';
import { sectionsOn } from '../src/card.ts';
import { ALEX, gameId, fakeHass, fixture, flush, SAM } from './fake-hass.js';

let el;

async function mount(config = {}, opts = {}) {
  const fake = fakeHass(opts);
  el = document.createElement('home-keeper-games-card');
  el.setConfig({ type: 'custom:home-keeper-games-card', ...config });
  document.body.appendChild(el);
  el.hass = fake.hass;
  await flush();
  return fake;
}

const $ = (sel) => el.shadowRoot.querySelector(sel);
const $$ = (sel) => [...el.shadowRoot.querySelectorAll(sel)];
const text = () => el.shadowRoot.textContent.replace(/\s+/g, ' ');

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] });
  vi.setSystemTime(new Date(2026, 9, 5, 12));
});
afterEach(() => {
  el?.remove();
  vi.useRealTimers();
});

describe('card', () => {
  it('registers in the card picker', () => {
    expect(window.customCards.some((c) => c.type === 'home-keeper-games-card')).toBe(true);
    expect(customElements.get('home-keeper-games-card').getStubConfig()).toEqual({ type: 'custom:home-keeper-games-card' });
  });

  it('shows the playing games, the backlog, the goal and the household of the caller', async () => {
    const fake = await mount();
    expect(fake.calls('get_state')).toHaveLength(1);
    expect($('h2').textContent).toBe('Library: Alex');
    expect(text()).toContain('38 games');
    expect(text()).toContain('Project Hail Mary');
    expect(text()).toContain('210 min played');
    expect(text()).toContain('Switch · 95 min played');
    expect(text()).toContain('Backlog · 2');
    expect(text()).toContain('6 of 24 games in 2026');
    expect(text()).toContain('Goal: 24');
    expect(text()).toContain('Sam: playing The Left Hand of Darkness');
    expect(text()).toContain('2 days ago');
  });

  it('hides the household rows of a person who does not share', async () => {
    const state = fixture();
    state.people[SAM].share_progress = false;
    await mount({}, { state });
    expect(text()).not.toContain('Sam: playing');
    expect(text()).toContain('Jo: playing The Tombs of Atuan');
  });

  it('sets the play time and the completed status for the caller, with no person_id', async () => {
    const state = fixture();
    const id = gameId(state, 'Project Hail Mary');
    const fake = await mount();
    $(`[data-k="st-${id}:pc"]`).click();
    const input = $(`[data-k="time-${id}:pc"]`);
    input.value = '250';
    input.form.requestSubmit();
    await flush();
    expect(fake.calls('set_progress')[0]).toEqual({ type: 'home_keeper_games/set_progress', game_id: id, platform: 'pc', playtime_minutes: 250 });
    $(`[data-k="cp-${id}:pc"]`).click();
    await flush();
    expect(fake.calls('set_progress')[1]).toEqual({ type: 'home_keeper_games/set_progress', game_id: id, platform: 'pc', play_status: 'completed', completed_at: '2026-10-05', completion_count: 1 });
    const left = gameId(state, 'The Left Hand of Darkness');
    $(`[data-k="cp-${left}:switch"]`).click();
    await flush();
    expect(fake.calls('set_progress')[2]).toMatchObject({ game_id: left, platform: 'switch', completion_count: 1 });
  });

  it('searches and adds a game to the backlog', async () => {
    const state = fixture();
    const fake = await mount();
    const input = $('[data-k="q"]');
    input.focus();
    input.value = 'lavinia';
    input.dispatchEvent(new Event('input', { bubbles: true }));
    await new Promise((r) => setTimeout(r, 200));
    expect(text()).toContain('Living room › Unit A › Shelf 3');
    expect(el.shadowRoot.activeElement?.dataset.k).toBe('q');
    $(`[data-k="w-${gameId(state, 'Lavinia')}"]`).click();
    await flush();
    expect(fake.calls('set_progress')[0]).toMatchObject({ game_id: gameId(state, 'Lavinia'), platform: 'switch2', play_status: 'backlog' });
  });

  it('shows another person for an admin, with person_id in the call', async () => {
    const state = fixture();
    const fake = await mount({ person: SAM });
    expect($('h2').textContent).toBe('Library: Sam');
    const id = gameId(state, 'The Left Hand of Darkness');
    $(`[data-k="cp-${id}:switch2"]`).click();
    await flush();
    expect(fake.calls('set_progress')[0]).toMatchObject({ game_id: id, platform: 'switch2', person_id: SAM, play_status: 'completed' });
  });

  it('ignores the person option for a non-admin user', async () => {
    const state = fixture();
    state.me.is_admin = false;
    await mount({ person: SAM }, { state });
    expect($('h2').textContent).toBe('Library: Alex');
  });

  it('says so when no person is linked', async () => {
    const state = fixture();
    state.me.person_id = null;
    await mount({}, { state });
    expect(text()).toContain('No person is linked to this user.');
  });

  it('picks a random game from the backlog', async () => {
    const rnd = vi.spyOn(Math, 'random').mockReturnValue(0.99);
    await mount();
    $('[data-k="random"]').click();
    expect(text()).toContain('Pick: The Tombs of Atuan');
    expect($$('.pick')).toHaveLength(1);
    rnd.mockRestore();
  });

  it('hides the sections that are off', async () => {
    await mount({ search: false, playing: false, backlog: false, household: false, title: 'Games' });
    expect($('h2').textContent).toBe('Games');
    expect($('[data-k="q"]')).toBeNull();
    expect(text()).not.toContain('Project Hail Mary');
    expect(text()).toContain('6 of 24 games in 2026');
    expect(text()).not.toContain('Household');
  });

  it('reads the section toggles', () => {
    expect(sectionsOn({ type: 'x' })).toEqual({ search: true, playing: true, backlog: true, goal: true, household: true });
    expect(sectionsOn({ type: 'x', goal: false }).goal).toBe(false);
  });
});

describe('card editor', () => {
  it('sends config-changed for a section and a person', () => {
    const ed = document.createElement('home-keeper-games-card-editor');
    ed.hass = fakeHass().hass;
    ed.setConfig({ type: 'custom:home-keeper-games-card' });
    document.body.appendChild(ed);
    const events = [];
    ed.addEventListener('config-changed', (e) => events.push(e.detail.config));
    const box = ed.querySelector('[data-key="goal"]');
    box.checked = false;
    box.dispatchEvent(new Event('change'));
    expect(events.at(-1)).toEqual({ type: 'custom:home-keeper-games-card', goal: false });
    const sel = ed.querySelector('[data-key="person"]');
    expect([...sel.options].map((o) => o.textContent)).toEqual(['Current user', 'Alex', 'Jo', 'Sam']);
    sel.value = ALEX;
    sel.dispatchEvent(new Event('change'));
    expect(events.at(-1)).toEqual({ type: 'custom:home-keeper-games-card', goal: false, person: ALEX });
    ed.remove();
  });
});
