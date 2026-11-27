import { expect, openCard, test, userState } from './helpers';

/**
 * The card on a dashboard for Sam, a user who is not an admin. The card shows the
 * progress of Sam, the shared progress of the household, and nothing private: the
 * backend projection leaves out the prices, the values and the loan parties.
 */
test.describe('Card for a user who is not an admin', { tag: '@responsive' }, () => {
  test.use({ storageState: './.auth/sam.json' });

  test('shows only the data of that person and no price', async ({ page }) => {
    const card = await openCard(page);
    await expect(card.locator('.head h2')).toHaveText('Library: Sam');
    await expect(card).toContainText('The Legend of Zelda: Tears of the Kingdom');
    await expect(card).toContainText('112 min played');
    await expect(card).toContainText('Sea of Stars');
    // The progress of Alex shows only as household activity, never as Sam's.
    await expect(card.locator('.sec').filter({ hasText: 'Playing' }).first()).not.toContainText('Outer Wilds');
    await expect(card).toContainText('Alex: completed Hades');
    await expect(card).not.toContainText('€');

    const state = await userState();
    expect(state.me).toMatchObject({ person_id: 'sam', is_admin: false });
    for (const copy of state.copies) {
      expect(copy).not.toHaveProperty('price');
      expect(copy).not.toHaveProperty('value');
      expect(copy).not.toHaveProperty('acquired_from');
    }
    for (const loan of state.loans) expect(loan).not.toHaveProperty('party');
    for (const game of state.games) {
      const people = game.progress as Record<string, Record<string, Record<string, unknown>>>;
      for (const [pid, rows] of Object.entries(people)) {
        if (pid === 'sam') continue;
        for (const row of Object.values(rows)) expect(row).not.toHaveProperty('review');
      }
    }
  });

  test('the Home Keeper panel is not open to the user', async ({ page }) => {
    await page.goto('/home-keeper/games', { waitUntil: 'domcontentloaded' });
    await expect(page.locator('home-keeper-games-tab')).toHaveCount(0);
  });
});
