// The state that the tab views read. The views are free functions over `ViewCtx`.

import type { ImportSummary, Lib, Platform, ScanResult, Session } from './types';
import type { Index, TabRoute } from './utils';

export interface ScanEntry {
  key: number;
  barcode: string;
  pending: boolean;
  res: ScanResult | null;
  error?: string;
  /** What the user picked for a duplicate. */
  choice?: 'move' | 'add_copy' | 'skip';
  /** The user gave the title of the new game of a scan. */
  named?: boolean;
  /** The user removed the new game of a scan. */
  removed?: boolean;
}

export interface ScanSession {
  method: 'camera' | 'manual';
  roomId: string | null;
  /** The platform and the format of each copy that the scan adds. */
  platform: string;
  format: string;
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
  importReview: boolean;
  replaceProgress: boolean;
  summary: ImportSummary | null;
  busy: boolean;
  error: string;
  done: boolean;
}

export interface PlayLogState {
  /** The person whose sessions are in `sessions`. */
  person: string | null;
  /** Null until `list_sessions` replies. */
  sessions: Session[] | null;
  error: string;
  /** The open rows, by `PlayLogRow.key`. */
  open: Record<string, boolean>;
}

export interface UiState {
  limit: number;
  notesTab: 'shared' | 'private';
  editNotes: boolean;
  /** The person and the platform that the progress form of a game edits. */
  progressPerson: string | null;
  progressPlatform: Platform | null;
  scan: ScanSession;
  import: ImportState;
  todoEntities: Array<{ entity_id: string; name?: string }>;
  playlog: PlayLogState;
  exportPerson: string;
}

export interface ViewCtx {
  lib: Lib;
  idx: Index;
  route: TabRoute;
  me: string | null;
  today: string;
  ui: UiState;
  /** The game list path to go back to from a game. */
  gamesPath: string;
  taskLink: (id: string) => string;
  areaName: (id: string) => string;
  todoName: (entityId: string) => string;
}
