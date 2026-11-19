// The entry point of `games-tab.js`, the ES module that the Home Keeper panel
// imports for the Library tab.
import { HomeKeeperGamesTab } from './tab';

export const TAB_TAG = 'home-keeper-games-tab';

if (!customElements.get(TAB_TAG)) {
  customElements.define(TAB_TAG, HomeKeeperGamesTab);
}

export { HomeKeeperGamesTab };
