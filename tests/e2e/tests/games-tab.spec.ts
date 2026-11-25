import { adminState, gameByTitle, expect, libraryTab, openTab, restoreProgress, test, trackErrors } from './helpers';

/**
 * The Games tab in the real Home Keeper panel: the tab bar, the game grid, the
 * search, the covers and the game detail. The data is the committed seed
 * (tests/e2e/seed/build_seed.py). A test that changes a progress row puts the seed
 * row back after.
 */
/** A game with a paper copy that is not lent, so the Lend dialog has a copy. */
async function lendableGame(): Promise<Record<string, any>> {
  const state = await adminState();
  const lent = new Set(state.loans.filter((l: any) => !l.returned).map((l: any) => l.copy_id));
  const copy = state.copies.find((c: any) => !lent.has(c.id) && c.format !== 'digital');
  if (!copy) throw new Error('no copy to lend in the seed');
  return state.games.find((b: any) => b.id === copy.game_id);
}

test.describe('Games tab', { tag: '@responsive' }, () => {
  test('a copy shows its platform and the barcode of its case', async ({ page }) => {
    const game = await gameByTitle('The Left Hand of Darkness');
    const state = await adminState();
    const copy = state.copies.find((c: { game_id: string; barcode: string | null }) => c.game_id === game.id && c.barcode);
    const tab = await openTab(page, `/games/${game.id}`);
    // Only the copy with the barcode shows it.
    const details = tab.locator('.hkl-copy').filter({ hasText: copy.barcode });
    await expect(details).toHaveCount(1);
    await expect(details).toContainText('Platform');
    await tab.locator(`[data-k="ec-${copy.id}"]`).click();
    const dialog = tab.locator('.hkl-dialog');
    await expect(dialog.locator('[name="platform"]')).toHaveValue(copy.platform);
    await expect(dialog.locator('[name="barcode"]')).toHaveValue(copy.barcode);
    await expect(dialog.locator('[name="steelbook"]')).toBeVisible();
    await dialog.locator('[data-k="d-cancel"]').click();
    await expect(dialog).toHaveCount(0);
  });

  test('Home Keeper shows the Games tab at /home-keeper/games', async ({ page }) => {
    const errors = trackErrors(page);
    const tab = await openTab(page);
    const panel = page.locator('home-keeper-panel');
    await expect(panel.locator('#tab-x-games[active]:visible, #mtab-x-games[aria-current="page"]:visible').first()).toBeVisible();
    await expect(tab.locator('[data-k="nav-games"]')).toHaveAttribute('aria-current', 'page');
    const state = await adminState();
    const owned = state.games.filter((b: { owned: boolean }) => b.owned).length;
    await expect(tab.locator('.hkl-tile')).toHaveCount(owned);
    await expect(tab.locator('[data-k="st-all"]')).toContainText(String(owned));
    expect(errors, errors.join('\n')).toEqual([]);
  });

  test('the search narrows the grid and goes into the URL', async ({ page }) => {
    const tab = await openTab(page);
    await tab.locator('[data-k="q"]').fill('science fiction');
    await expect(page).toHaveURL(/\/home-keeper\/games\/games;q=science%20fiction$/);
    const state = await adminState();
    const leGuin = state.games.filter((b: { owned: boolean; genres: string[] }) => b.owned && b.genres.includes('Science fiction'));
    await expect(tab.locator('.hkl-tile')).toHaveCount(leGuin.length);
    await expect(tab.locator('.hkl-summary')).toContainText(`${leGuin.length} books`);
    await tab.locator('[data-k="clear"]').click();
    await expect(page).toHaveURL(/\/home-keeper\/games\/games$/);
  });

  test('a dialog error keeps the text that the user typed', async ({ page }) => {
    const game = await lendableGame();
    const tab = await openTab(page, `/games/${game.id}`);
    await tab.locator('[data-k="lend"]').click();
    const dialog = tab.locator('.hkl-dialog');
    await dialog.locator('[name="note"]').fill('Back by the trip');
    await dialog.locator('[data-k="d-submit"]').click();
    await expect(dialog.locator('.hkl-error')).toHaveText('Enter the book and the name of the person.');
    await expect(dialog.locator('[name="note"]')).toHaveValue('Back by the trip');
    await expect(dialog.locator('[data-k="d-submit"]')).toBeEnabled();
    await dialog.locator('[data-k="d-cancel"]').click();
    await expect(dialog).toHaveCount(0);
  });

  test('a cover loads through a signed URL', async ({ page }) => {
    const game = await gameByTitle('Piranesi');
    expect(game.cover_url).toMatch(/^\/api\/home_keeper_games\/cover\//);
    const tab = await openTab(page);
    const img = tab.locator(`[data-k="b-${game.id}"] img`);
    await expect(img).toHaveAttribute('src', /authSig=/);
    await expect.poll(() => img.evaluate((el: HTMLImageElement) => el.complete && el.naturalWidth)).toBeGreaterThan(0);
  });

  test('the shared notes render as Markdown', async ({ page }) => {
    const game = await gameByTitle('The Left Hand of Darkness');
    const tab = await openTab(page, `/games/${game.id}`);
    await expect(tab.locator('h1')).toHaveText(game.title);
    const md = tab.locator('ha-markdown.hkl-md');
    await expect(md.locator('strong')).toHaveText('Oct 2026');
    await expect(tab.locator('.hkl-md-plain')).toHaveCount(0);
  });
});

test.describe('Game detail', { tag: '@responsive' }, () => {
  const TITLE = 'The Lathe of Heaven';
  let seedRow: Record<string, unknown> | undefined;
  let gameId = '';

  test.beforeEach(async () => {
    const game = await gameByTitle(TITLE);
    gameId = game.id;
    seedRow = game.progress.alex?.ps4;
  });

  test.afterEach(async () => {
    await restoreProgress(gameId, 'alex', 'ps4', seedRow);
  });

  test('sets the play status and the rating', async ({ page }) => {
    const tab = await openTab(page, `/games/${gameId}`);
    await expect(tab.locator('[data-k="pp-ps4"]')).toHaveAttribute('aria-pressed', 'true');
    await expect(tab.locator('[data-k="rs-backlog"]')).toHaveAttribute('aria-pressed', 'true');
    await tab.locator('[data-k="rs-playing"]').click();
    await expect(tab.locator('[data-k="rs-playing"]')).toHaveAttribute('aria-pressed', 'true');
    await tab.locator('[data-k="star-4"]').click();
    await expect(tab.locator('.hkl-star.on')).toHaveCount(4);
    await expect
      .poll(async () => {
        const row = (await gameByTitle(TITLE)).progress.alex.ps4;
        return [row.play_status, row.rating, Boolean(row.started_at)];
      })
      .toEqual(['playing', 4, true]);
    // The card status on the grid follows.
    await libraryTab(page).locator('[data-k="back"]').click();
    await expect(page).toHaveURL(/\/home-keeper\/games\/games$/);
  });

  test('a chip for each platform picks the row that the form edits', async ({ page }) => {
    const game = await gameByTitle('The Left Hand of Darkness');
    const tab = await openTab(page, `/games/${game.id}`);
    const chips = tab.locator('.hkl-plats .hkl-plat');
    await expect(chips).toHaveCount(2);
    await expect(tab.locator('[data-k="pp-switch2"]')).toHaveAttribute('aria-pressed', 'true');
    await expect(tab.locator('[data-k="rs-completed"]')).toHaveAttribute('aria-pressed', 'true');
    await tab.locator('[data-k="pp-switch"]').click();
    await expect(tab.locator('[data-k="pp-switch"]')).toHaveAttribute('aria-pressed', 'true');
    await expect(tab.locator('[data-k="rs-playing"]')).toHaveAttribute('aria-pressed', 'true');
    await expect(tab.locator('[data-k="pp-add"]')).toBeVisible();
  });
});
