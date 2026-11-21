// The state that the tab views read. The views are free functions over `ViewCtx`.

import type { ImportSummary, Lib, ScanResult } from './types';
import type { Index, TabRoute } from './utils';

export interface ScanEntry {
  key: number;
  barcode: string;
  pending: boolean;
  res: ScanResult | null;
  error?: string;
  /** What the user picked for a duplicate. */
  choice?: 'move' | 'add_copy' | 'skip';
  /** The user gave the title of the new book of a scan. */
  named?: boolean;
  /** The user removed the new book of a scan. */
  removed?: boolean;
}

export interface ScanSession {
  method: 'camera' | 'manual';
  roomId: string | null;
  results: ScanEntry[];
  manualOpen: boolean;
  markRead: boolean;
  cameraError: '' | 'insecure' | 'denied' | 'unsupported';
  /** True when the camera runs but its picture stopped. A tap starts it again. */
  stalled: boolean;
  torch: boolean | null;
  party: string;
  personId: string | null;
  due: string;
  addTask: boolean;
}

export interface ImportState {
  personId: string | null;
  shelfId: string;
  fileName: string;
  content: string;
  rowCount: number;
  importNotes: boolean;
  replaceReading: boolean;
  summary: ImportSummary | null;
  busy: boolean;
  error: string;
  done: boolean;
}

export interface UiState {
  limit: number;
  notesTab: 'shared' | 'private';
  editNotes: boolean;
  readingPerson: string | null;
  scan: ScanSession;
  import: ImportState;
  todoEntities: Array<{ entity_id: string; name?: string }>;
  exportPerson: string;
}

export interface ViewCtx {
  lib: Lib;
  idx: Index;
  route: TabRoute;
  me: string | null;
  today: string;
  ui: UiState;
  /** The book list path to go back to from a book. */
  booksPath: string;
  taskLink: (id: string) => string;
  areaName: (id: string) => string;
  todoName: (entityId: string) => string;
}
