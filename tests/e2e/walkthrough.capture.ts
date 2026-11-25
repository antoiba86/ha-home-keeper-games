/**
 * The video walkthrough of the Library tab, for the PR comment (not committed).
 *
 *   KEEP_UP=1 NO_TESTS=1 bash ci/e2e-up.sh
 *   bash ci/capture-video.sh        # writes docs/videos/walkthrough.{webm,mp4,gif}
 *
 * The tour: open the Library tab in Home Keeper, browse the grid, search, open a
 * game, set the play status on a platform, add another platform chip, scan a stored
 * barcode and a new barcode into a shelf, give the title of the new game, lend a game
 * with a Home Keeper task, see the loan, and open the card on a dashboard. `BEAT` pauses
 * let each step read in the video. The tour puts the seed back at the end.
 *
 * The recording needs its own context: `recordVideo` is set when a context is made.
 */
import { expect, test, type Page } from '@playwright/test';
import { resolve } from 'node:path';
import { library } from './ha-ws';
import { adminState, gameByTitle, gamesWithCode, noServiceWorker, openCard, openTab, restoreProgress } from './tests/helpers';
import { DESKTOP } from './viewports';

const OUT = process.env.VIDEO_DIR || '/tmp/home-keeper-games-video';
const BEAT = 900;
// A seeded game with copies: the scan shows the duplicate choices.
const SEEDED_CODE = '9780441478125';
// No game has this barcode. The scan asks for its title.
const MISS_CODE = '9781402894626';
const MISS_TITLE = 'Field Notes on Moss';
const LEND_TITLE = 'Station Eleven';
const PARTY = 'Robin';
const STATUS_TITLE = 'The Lathe of Heaven';

async function beat(page: Page, n = 1): Promise<void> {
  await page.waitForTimeout(BEAT * n);
}

async function cleanUp(): Promise<void> {
  const state = await adminState();
  for (const game of gamesWithCode(state, [MISS_CODE])) {
    await library('delete_game', { game_id: game.id });
  }
  const lent = state.games.find((b: { title: string }) => b.title === LEND_TITLE);
  for (const loan of state.loans.filter((l: { game_id: string; party: string }) => l.game_id === lent.id && l.party === PARTY)) {
    await library('delete_loan', { loan_id: loan.id });
  }
}

test('record the Library walkthrough', async ({ browser }) => {
  await cleanUp();
  const status = await gameByTitle(STATUS_TITLE);
  const seedRow = status.progress.alex?.ps4;
  const context = await browser.newContext({
    storageState: './.auth/state.json',
    viewport: DESKTOP,
    recordVideo: { dir: OUT, size: DESKTOP },
  });
  await noServiceWorker(context);
  const page = await context.newPage();
  try {
    // 1. The Library tab in the Home Keeper panel, with the game grid.
    const tab = await openTab(page, '/games');
    await expect(tab.locator('.hkl-tile').first()).toBeVisible();
    await beat(page, 2);
    await tab.locator('.hkl-grid').evaluate((el) => el.scrollIntoView({ behavior: 'smooth', block: 'start' }));
    await beat(page);

    // 2. Search, then open a game.
    await tab.locator('[data-k="q"]').pressSequentially('lathe', { delay: 90 });
    await expect(tab.locator('.hkl-tile')).toHaveCount(1);
    await beat(page);
    await tab.locator(`[data-k="b-${status.id}"]`).click();
    await expect(tab.locator('h1')).toHaveText(STATUS_TITLE);
    await beat(page);

    // 3. Set the play status and a rating on the PS4 chip.
    await expect(tab.locator('[data-k="pp-ps4"]')).toHaveAttribute('aria-pressed', 'true');
    await tab.locator('[data-k="rs-playing"]').click();
    await expect(tab.locator('[data-k="rs-playing"]')).toHaveAttribute('aria-pressed', 'true');
    await beat(page);
    await tab.locator('[data-k="star-4"]').click();
    await expect(tab.locator('.hkl-star.on')).toHaveCount(4);
    await beat(page);

    // 3a. Each platform has its own progress: add a PC chip, then go back to PS4.
    await tab.locator('[data-k="pp-add"]').selectOption('pc');
    await expect(tab.locator('[data-k="pp-pc"]')).toHaveAttribute('aria-pressed', 'true');
    await beat(page, 2);
    await tab.locator('[data-k="pp-ps4"]').click();
    await expect(tab.locator('[data-k="rs-playing"]')).toHaveAttribute('aria-pressed', 'true');
    await beat(page);

    // 3b. A copy has a platform, a format and the barcode of its case.
    const editCopy = tab.locator('[data-k^="ec-"]').first();
    await editCopy.scrollIntoViewIfNeeded();
    await editCopy.click();
    const copyDialog = tab.locator('.hkl-dialog');
    await expect(copyDialog.locator('[name="platform"]')).toBeVisible();
    await beat(page, 2);
    await copyDialog.locator('[data-k="d-cancel"]').click();
    await expect(copyDialog).toHaveCount(0);

    // 4. Scan barcodes into a shelf.
    const state = await adminState();
    const office = state.rooms.find((r: { name: string }) => r.name === 'Office');
    const tall = state.units.find((c: { room_id: string }) => c.room_id === office.id);
    const shelf = state.shelves.find((s: { unit_id: string; name: string }) => s.unit_id === tall.id && s.name === 'Shelf 3');
    // The scan setup opens by its URL, with the shelf picked.
    await openTab(page, `/scan;shelf=${shelf.id}`);
    await expect(tab.locator('.hkl-scan-head')).toContainText('Scan books');
    await beat(page);
    await tab.locator('[data-k="m-manual"]').check();
    await expect(tab.locator('[data-k="m-manual"]')).toBeChecked();
    // Each copy that the scan adds gets the platform and the format of the setup.
    await tab.locator('[data-k="sc-platform"]').selectOption('switch');
    await beat(page);
    await tab.locator('[data-k="scan-start"]').click();
    await expect(tab.locator('[data-k="barcode-input"]')).toBeVisible();
    await beat(page);
    // A stored game: the scan offers Move here, Add 2nd copy or Skip.
    await tab.locator('[data-k="barcode-input"]').pressSequentially(SEEDED_CODE, { delay: 60 });
    await tab.locator('[data-k="barcode-add"]').click();
    const dup = tab.locator('.hkl-result.dup');
    await expect(dup).toBeVisible({ timeout: 30_000 });
    await beat(page, 2);
    await dup.getByRole('button', { name: 'Skip' }).click();
    await expect(dup).toHaveCount(0);
    await beat(page);
    // A new barcode: the scan stops and asks for the title.
    await tab.locator('[data-k="barcode-input"]').pressSequentially(MISS_CODE, { delay: 60 });
    await tab.locator('[data-k="barcode-add"]').click();
    const sheet = tab.locator('.hkl-dialog.sheet');
    await expect(sheet).toBeVisible({ timeout: 30_000 });
    await beat(page, 2);
    await sheet.locator('[name="title"]').pressSequentially(MISS_TITLE, { delay: 60 });
    await beat(page);
    await sheet.locator('[data-k="d-submit"]').click();
    await expect(sheet).toHaveCount(0);
    await expect(tab.locator('.hkl-result').filter({ hasText: MISS_TITLE })).toBeVisible();
    await beat(page, 2);
    await tab.locator('[data-k="scan-done"]').click();
    await expect(tab.locator('.hkl-scan-head')).toContainText('Scan summary');
    await beat(page, 2);
    // Done opens the room of the shelf, with the new spine on it.
    await tab.locator('[data-k="scan-finish"]').click();
    await expect(tab.locator('.hkl-room h1')).toHaveText('Office');
    await beat(page, 2);

    // 5. Lend a game. The loan has a due date, so Home Keeper gets a task.
    const lend = await gameByTitle(LEND_TITLE);
    await tab.locator('[data-k="nav-games"]').click();
    await tab.locator('[data-k="q"]').fill('');
    await tab.locator('[data-k="q"]').pressSequentially('station', { delay: 90 });
    await expect(tab.locator('.hkl-tile')).toHaveCount(1);
    await tab.locator(`[data-k="b-${lend.id}"]`).click();
    await expect(tab.locator('h1')).toHaveText(LEND_TITLE);
    await beat(page);
    await tab.locator('[data-k="lend"]').click();
    const dialog = tab.locator('.hkl-dialog');
    await dialog.locator('[name="party"]').pressSequentially(PARTY, { delay: 90 });
    await dialog.locator('[name="due"]').fill('2026-12-01');
    await beat(page);
    await dialog.locator('[data-k="d-submit"]').click();
    await expect(tab.locator('a.hkl-task')).toBeVisible({ timeout: 30_000 });
    await beat(page, 2);

    // 6. The Loans view, then the task in Home Keeper.
    await tab.locator('[data-k="nav-loans"]').click();
    await expect(tab.locator('.hkl-listrow').first()).toBeVisible();
    await beat(page, 2);
    await tab.locator('.hkl-listrow').filter({ hasText: LEND_TITLE }).locator('a.hkl-task').click();
    await expect(page).toHaveURL(/\/home-keeper\/tasks\//);
    // Home Keeper 0.30.0 loads a task that a companion added only on a page load.
    await page.reload();
    await expect(page.locator('home-keeper-panel')).toContainText(`Get ${LEND_TITLE} back from ${PARTY}`, { timeout: 30_000 });
    await beat(page, 2);

    // 7. The card on a dashboard.
    await openCard(page);
    await beat(page, 3);
  } finally {
    const video = page.video();
    await context.close();
    if (video) await video.saveAs(resolve(OUT, 'walkthrough.webm'));
    await cleanUp();
    await restoreProgress(status.id, 'alex', 'ps4', seedRow);
  }
});
