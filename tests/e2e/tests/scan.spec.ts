import { library } from '../ha-ws';
import type { Locator, Page } from '@playwright/test';
import { resolve } from 'node:path';
import { adminState, gameByTitle, gamesWithCode, expect, fakeCamera, openTab, test } from './helpers';

/**
 * The Scan flow with Enter barcode. A new barcode adds a game that the test deletes after
 * it runs.
 */
const NEW_CODE = '9780553418606';
const SEEDED_CODE = '9780441478125';
const SEEDED_TITLE = 'The Left Hand of Darkness';
/** No seeded game has this barcode. */
const MISS_CODE = '9781402894626';
const MISS_TITLE = 'Field Notes on Moss';
const COVER = resolve(__dirname, '../seed/covers/13be6b0e5c354e1981a89fe2766196e0-552257a9.jpg');

async function shelfId(room: string, unit: string, shelf: string): Promise<string> {
  const state = await adminState();
  const r = state.rooms.find((x: { name: string }) => x.name === room);
  const c = state.units.find((x: { name: string; room_id: string }) => x.name === unit && x.room_id === r.id);
  return state.shelves.find((x: { name: string; unit_id: string }) => x.name === shelf && x.unit_id === c.id).id;
}

async function deleteNewGame(): Promise<void> {
  const state = await adminState();
  for (const game of gamesWithCode(state, [NEW_CODE, MISS_CODE])) {
    await library('delete_game', { game_id: game.id });
  }
}

test.describe('Scan', { tag: '@responsive' }, () => {
  test.beforeEach(deleteNewGame);
  test.afterEach(deleteNewGame);

  test('Enter barcode with a new barcode asks for its title before the next scan', async ({ page }) => {
    const shelf = await shelfId('Office', 'Tall unit', 'Shelf 3');
    const tab = await openTab(page, `/scan;shelf=${shelf}`);
    await tab.locator('[data-k="m-manual"]').check();
    await tab.locator('[data-k="scan-start"]').click();
    await tab.locator('[data-k="barcode-input"]').fill('978-1402-894626');
    await tab.locator('[data-k="barcode-add"]').click();

    const sheet = tab.locator('.hkl-dialog.sheet');
    await expect(sheet).toBeVisible({ timeout: 30_000 });
    await expect(sheet.locator('h2')).toHaveText('No game has this barcode');
    await expect(sheet.locator('[data-k="d-barcode"]')).toHaveText(`Barcode ${MISS_CODE}`);
    await expect(sheet.locator('[name="title"]')).toBeFocused();
    const submit = sheet.locator('[data-k="d-submit"]');
    await expect(submit).toBeDisabled();
    await expect(sheet.locator('[name="franchise"]')).toBeHidden();
    await page.keyboard.press('Escape');
    await expect(sheet).toBeVisible();

    await sheet.locator('[name="title"]').fill(MISS_TITLE);
    await expect(submit).toBeEnabled();
    await sheet.locator('[data-k="d-more-toggle"]').click();
    await sheet.locator('[name="franchise"]').fill('Moss');
    await sheet.locator('[name="format"]').selectOption('digital');
    await sheet.locator('[data-k="d-cover"]').setInputFiles(COVER);
    await expect(sheet.locator('[data-k="d-cover-name"]')).toHaveText('13be6b0e5c354e1981a89fe2766196e0-552257a9.jpg');
    await submit.click();
    await expect(sheet).toHaveCount(0);
    await expect(tab.locator('.hkl-result').filter({ hasText: MISS_TITLE })).toContainText('No game has this barcode');

    const state = await adminState();
    const [game] = gamesWithCode(state, [MISS_CODE]);
    expect(game).toMatchObject({ title: MISS_TITLE, franchise: 'Moss', needs_details: true });
    expect(game.cover.kind).toBe('custom');
    const copies = state.copies.filter((c: { game_id: string }) => c.game_id === game.id);
    expect(copies.map((c: { shelf_id: string; format: string }) => [c.shelf_id, c.format])).toEqual([[null, 'digital']]);
  });

  test('Remove this scan deletes the new game', async ({ page }) => {
    const tab = await openTab(page, '/scan');
    await tab.locator('[data-k="m-manual"]').check();
    await tab.locator('[data-k="scan-start"]').click();
    await tab.locator('[data-k="barcode-input"]').fill(MISS_CODE);
    await tab.locator('[data-k="barcode-add"]').click();
    const sheet = tab.locator('.hkl-dialog.sheet');
    await expect(sheet).toBeVisible({ timeout: 30_000 });
    await sheet.locator('[data-k="d-remove"]').click();
    await expect(sheet).toHaveCount(0);
    await expect(tab.locator('[data-k^="removed-"]')).toHaveText('Removed');
    const state = await adminState();
    expect(gamesWithCode(state, [MISS_CODE])).toEqual([]);
  });

  test('a duplicate shows its actions and Skip changes nothing', async ({ page }) => {
    const seeded = await gameByTitle(SEEDED_TITLE);
    expect(gamesWithCode(await adminState(), [SEEDED_CODE]).map((g) => g.id)).toEqual([seeded.id]);
    const before = (await adminState()).copies.filter((c: { game_id: string }) => c.game_id === seeded.id);
    const shelf = await shelfId('Office', 'Tall unit', 'Shelf 3');
    const tab = await openTab(page, `/scan;shelf=${shelf};step=camera`);
    await tab.locator('[data-k="m-manual"]').check().catch(() => undefined);
    const input = tab.locator('[data-k="barcode-input"]');
    if (!(await input.isVisible())) await tab.locator('[data-k="scan-manual"]').click();
    await input.fill(SEEDED_CODE);
    await tab.locator('[data-k="barcode-add"]').click();
    const row = tab.locator('.hkl-result.dup');
    await expect(row).toContainText('Already in Office › Tall unit › Shelf 1, Living room › Unit A › Shelf 2');
    await expect(row.getByRole('button', { name: 'Move here' })).toBeVisible();
    await expect(row.getByRole('button', { name: 'Add 2nd copy' })).toBeVisible();
    await row.getByRole('button', { name: 'Skip' }).click();
    await expect(tab.locator('.hkl-result').filter({ hasText: seeded.title }).locator('.hkl-pill')).toHaveText('Skipped');
    const after = (await adminState()).copies.filter((c: { game_id: string }) => c.game_id === seeded.id);
    expect(after).toEqual(before);
  });
});

function pageVar<T>(page: Page, name: string): Promise<T> {
  return page.evaluate((key) => (window as unknown as Record<string, T>)[key], name);
}

/** True when the video is in the page, plays, and has a live camera track. */
function playing(video: Locator): Promise<boolean> {
  return video.evaluate((v: HTMLVideoElement) => {
    const tracks = (v.srcObject as MediaStream | null)?.getVideoTracks() ?? [];
    return v.isConnected && !v.paused && tracks.length > 0 && tracks.every((tr) => tr.readyState === 'live');
  });
}

test.describe('Scan camera', { tag: '@responsive' }, () => {
  test.beforeEach(deleteNewGame);
  test.afterEach(deleteNewGame);

  test('the camera keeps its picture after a scan, and stops at the summary', async ({ page }) => {
    await fakeCamera(page);
    const shelf = await shelfId('Office', 'Tall unit', 'Shelf 3');
    const tab = await openTab(page, `/scan;shelf=${shelf}`);
    await tab.locator('[data-k="scan-start"]').click();
    const video = tab.locator('[data-slot="video"] video');
    await expect.poll(() => playing(video)).toBe(true);
    // Count the pauses. A video that leaves the page pauses, and a phone app can refuse to play it again.
    await video.evaluate((v: HTMLVideoElement) => {
      const w = window as unknown as Record<string, number>;
      w.__hklPauses = 0;
      v.addEventListener('pause', () => w.__hklPauses++);
    });

    // The scan changes the library, and Home Keeper redraws its panel.
    await page.evaluate((code) => ((window as unknown as Record<string, unknown>).__hklCode = code), SEEDED_CODE);
    const row = tab.locator('.hkl-result.dup').filter({ hasText: SEEDED_TITLE });
    await expect(row).toContainText('Already in', { timeout: 30_000 });
    await expect.poll(() => playing(video)).toBe(true);
    expect(await pageVar<number>(page, '__hklPauses')).toBe(0);
    const t0 = await video.evaluate((v: HTMLVideoElement) => v.currentTime);
    await expect.poll(() => video.evaluate((v: HTMLVideoElement) => v.currentTime)).toBeGreaterThan(t0);
    expect(await pageVar<number>(page, '__hklGum')).toBe(1);

    await tab.locator('[data-k="scan-done"]').click();
    await expect(tab.locator('.hkl-scan-head')).toContainText('Scan summary');
    await expect
      .poll(() => page.evaluate(() => (window as unknown as { __hklStream: MediaStream }).__hklStream.getVideoTracks()[0].readyState))
      .toBe('ended');
  });
});

test.describe('Scan camera with a new barcode', { tag: '@responsive' }, () => {
  test.beforeEach(deleteNewGame);
  test.afterEach(deleteNewGame);

  test('the camera shows Scan paused and reads no code until the title is saved', async ({ page }) => {
    await fakeCamera(page);
    const tab = await openTab(page, '/scan');
    await tab.locator('[data-k="scan-start"]').click();
    const video = tab.locator('[data-slot="video"] video');
    await expect.poll(() => playing(video)).toBe(true);
    await page.evaluate((code) => ((window as unknown as Record<string, unknown>).__hklCode = code), MISS_CODE);
    const sheet = tab.locator('.hkl-dialog.sheet');
    await expect(sheet).toBeVisible({ timeout: 30_000 });
    await expect(tab.locator('[data-k="cam-paused"]')).toHaveText('Scan paused');

    // A code read now adds no game.
    await page.evaluate((code) => ((window as unknown as Record<string, unknown>).__hklCode = code), NEW_CODE);
    await expect.poll(() => page.evaluate(() => (window as unknown as Record<string, string>).__hklCode)).toBe('');
    await expect(tab.locator('.hkl-result')).toHaveCount(1);

    await sheet.locator('[name="title"]').fill(MISS_TITLE);
    await sheet.locator('[data-k="d-submit"]').click();
    await expect(sheet).toHaveCount(0);
    await expect(tab.locator('[data-k="cam-paused"]')).toHaveCount(0);
    expect(await playing(video)).toBe(true);
    const state = await adminState();
    expect(gamesWithCode(state, [NEW_CODE])).toEqual([]);
  });
});

test.describe('Scan camera recovery', { tag: '@responsive' }, () => {
  test('a refused play() shows the restart button, and a tap starts the picture again', async ({ page }) => {
    await fakeCamera(page);
    const tab = await openTab(page, '/scan');
    await tab.locator('[data-k="scan-start"]').click();
    const video = tab.locator('[data-slot="video"] video');
    await expect.poll(() => playing(video)).toBe(true);
    await video.evaluate((v: HTMLVideoElement) => v.setAttribute('data-first', ''));

    await page.evaluate(() => ((window as unknown as Record<string, unknown>).__hklRefusePlay = true));
    await video.evaluate((v: HTMLVideoElement) => v.pause());
    const restart = tab.locator('[data-k="cam-restart"]');
    await expect(restart).toHaveText('The camera stopped. Tap to start it again.');

    await page.evaluate(() => ((window as unknown as Record<string, unknown>).__hklRefusePlay = false));
    await restart.click();
    await expect(restart).toHaveCount(0);
    await expect.poll(() => playing(video)).toBe(true);
    await expect(video).toHaveAttribute('data-first', '');
    expect(await pageVar<number>(page, '__hklGum')).toBe(1);
  });

  test('a tap opens a new camera when the camera track ended', async ({ page }) => {
    await fakeCamera(page);
    const tab = await openTab(page, '/scan');
    await tab.locator('[data-k="scan-start"]').click();
    const video = tab.locator('[data-slot="video"] video');
    await expect.poll(() => playing(video)).toBe(true);
    await page.evaluate(() => {
      const track = (window as unknown as { __hklStream: MediaStream }).__hklStream.getVideoTracks()[0];
      track.stop();
      track.dispatchEvent(new Event('ended'));
    });
    await tab.locator('[data-k="cam-restart"]').click();
    await expect(tab.locator('[data-k="cam-restart"]')).toHaveCount(0);
    await expect.poll(() => playing(video)).toBe(true);
    expect(await pageVar<number>(page, '__hklGum')).toBe(2);
  });

  test('the debug view shows the camera state and log', async ({ page }) => {
    await fakeCamera(page);
    const tab = await openTab(page, '/scan;debug=1');
    await tab.locator('[data-k="scan-start"]').click();
    await expect(page).toHaveURL(/step=camera;debug=1/);
    const debug = tab.locator('[data-k="cam-debug"]');
    await expect(debug).toContainText('video: paused=false');
    await expect(debug).toContainText('track: live');
    await expect(debug).toContainText('detector: native');
    await expect(debug).toContainText('getUserMedia ok');
    await expect(debug).toContainText(/tab \d+ of \d+: in page=true/);
  });
});

test.describe('Scan on a page that is not HTTPS', { tag: '@responsive' }, () => {
  test('the camera is blocked with the HTTPS message, and Enter barcode still starts', async ({ page }) => {
    await page.addInitScript(() => Object.defineProperty(window, 'isSecureContext', { value: false }));
    const tab = await openTab(page, '/scan');
    await expect(tab.locator('[data-k="m-https"]')).toContainText('The camera needs HTTPS.');
    await expect(tab.locator('[data-k="scan-start"]')).toBeDisabled();
    await tab.locator('[data-k="m-manual"]').check();
    await expect(tab.locator('[data-k="m-https"]')).toHaveCount(0);
    await tab.locator('[data-k="scan-start"]').click();
    await expect(page).toHaveURL(/step=camera/);
    await expect(tab.locator('[data-k="barcode-input"]')).toBeVisible();
  });
});
