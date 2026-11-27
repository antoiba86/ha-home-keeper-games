import { library } from '../ha-ws';
import { gameByTitle, expect, openTab, test } from './helpers';

/**
 * The Play log view: the rows of a person, the sessions of a row, and a logged
 * session that a delete takes away again. The seed has the sessions of Alex.
 */
const TITLE = 'Outer Wilds';

test.describe('Play log', { tag: '@responsive' }, () => {
  test('lists the play time of a person and opens the sessions of a game', async ({ page }) => {
    const game = await gameByTitle(TITLE);
    const tab = await openTab(page, '/playlog');
    await expect(tab.locator('[data-k="nav-playlog"]')).toHaveAttribute('aria-current', 'page');
    await expect(tab.locator('.hkl-card-head h2')).toHaveText('Alex: play log');
    const row = tab.locator(`[data-k="pl-${game.id}|pc"]`);
    await expect(row).toContainText(TITLE);
    await expect(row).toContainText('3 h 30 min');
    await row.click();
    await expect(row).toHaveAttribute('aria-expanded', 'true');
    await expect(tab.locator('.hkl-session')).toHaveCount(3);
    await expect(tab.locator('.hkl-session').first()).toContainText('1 h 35 min');

    await tab.locator('[data-k="lp-sam"]').click();
    await expect(page).toHaveURL(/\/home-keeper\/games\/playlog;person=sam$/);
    await expect(tab.locator('.hkl-card-head h2')).toHaveText('Sam: play log');
  });

  test('logs a session and deletes it', async ({ page }) => {
    const game = await gameByTitle('Celeste');
    const tab = await openTab(page, '/playlog');
    await tab.locator('[data-k="log-session"]').click();
    const dialog = tab.locator('.hkl-dialog');
    await dialog.locator('[name="game_id"]').selectOption(game.id);
    await dialog.locator('[name="platform"]').selectOption('switch');
    await dialog.locator('[name="minutes"]').fill('25');
    await dialog.locator('[data-k="d-submit"]').click();
    const row = tab.locator(`[data-k="pl-${game.id}|switch"]`);
    await expect(row).toContainText('25 min');
    await row.click();
    const session = tab.locator('.hkl-session');
    await expect(session).toHaveCount(1);
    await session.locator('[data-act="delete-session"]').click();
    await tab.locator('.hkl-dialog [data-k="d-submit"]').click();
    await expect(tab.locator('.hkl-session')).toHaveCount(0);
    // The delete takes the minutes off. Clear the progress row that the log made.
    await library('set_progress', { game_id: game.id, person_id: 'alex', platform: 'switch', play_status: 'none' });
  });
});
