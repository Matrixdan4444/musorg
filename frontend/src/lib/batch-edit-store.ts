import { getBatchEditAlbumDetail, getBatchEditAlbums } from "@/lib/api/music";
import type { AlbumsPayload, BatchEditAlbumDetailPayload } from "@/types/music";

type Listener = () => void;

interface AlbumsResourceState {
  data: AlbumsPayload | null;
  loading: boolean;
  error: string | null;
  loaded: boolean;
  requestId: number;
  promise: Promise<AlbumsPayload> | null;
}

interface DetailResourceState {
  data: BatchEditAlbumDetailPayload | null;
  loading: boolean;
  error: string | null;
  loaded: boolean;
  requestId: number;
  promise: Promise<BatchEditAlbumDetailPayload> | null;
}

const EMPTY_DETAIL_STATE: DetailResourceState = {
  data: null,
  loading: false,
  error: null,
  loaded: false,
  requestId: 0,
  promise: null,
};

class BatchEditStore {
  private albumsState: AlbumsResourceState = {
    data: null,
    loading: false,
    error: null,
    loaded: false,
    requestId: 0,
    promise: null,
  };

  private albumListeners = new Set<Listener>();
  private detailStatesByAlbumId: Record<string, DetailResourceState> = {};
  private detailListenersByAlbumId = new Map<string, Set<Listener>>();

  subscribeAlbums = (listener: Listener) => {
    this.albumListeners.add(listener);
    return () => this.albumListeners.delete(listener);
  };

  subscribeAlbumDetail = (albumId: string, listener: Listener) => {
    const listeners = this.detailListenersByAlbumId.get(albumId) ?? new Set<Listener>();
    listeners.add(listener);
    this.detailListenersByAlbumId.set(albumId, listeners);
    return () => {
      const current = this.detailListenersByAlbumId.get(albumId);
      if (!current) {
        return;
      }
      current.delete(listener);
      if (current.size === 0) {
        this.detailListenersByAlbumId.delete(albumId);
      }
    };
  };

  getAlbumsSnapshot = () => this.albumsState;

  getAlbumDetailSnapshot = (albumId: string | null) => {
    if (!albumId) {
      return EMPTY_DETAIL_STATE;
    }
    return this.detailStatesByAlbumId[albumId] ?? EMPTY_DETAIL_STATE;
  };

  async ensureAlbums(errorMessage: string, force = false) {
    if (!force) {
      if (this.albumsState.promise) {
        return this.albumsState.promise;
      }
      if (this.albumsState.data) {
        return this.albumsState.data;
      }
    }

    const requestId = this.albumsState.requestId + 1;
    const promise = getBatchEditAlbums();
    this.albumsState = {
      ...this.albumsState,
      loading: true,
      error: null,
      requestId,
      promise,
    };
    this.emitAlbums();

    try {
      const payload = await promise;
      if (this.albumsState.requestId !== requestId) {
        return payload;
      }
      this.albumsState = {
        data: payload,
        loading: false,
        error: null,
        loaded: true,
        requestId,
        promise: null,
      };
      this.emitAlbums();
      return payload;
    } catch (err) {
      if (this.albumsState.requestId !== requestId) {
        throw err;
      }
      this.albumsState = {
        ...this.albumsState,
        loading: false,
        error: err instanceof Error ? err.message : errorMessage,
        loaded: true,
        promise: null,
      };
      this.emitAlbums();
      throw err;
    }
  }

  async ensureAlbumDetail(albumId: string, errorMessage: string, force = false) {
    const current = this.detailStatesByAlbumId[albumId] ?? EMPTY_DETAIL_STATE;
    if (!force) {
      if (current.promise) {
        return current.promise;
      }
      if (current.data) {
        return current.data;
      }
    }

    const requestId = current.requestId + 1;
    const promise = getBatchEditAlbumDetail(albumId);
    this.detailStatesByAlbumId = {
      ...this.detailStatesByAlbumId,
      [albumId]: {
        ...current,
        loading: true,
        error: null,
        requestId,
        promise,
      },
    };
    this.emitAlbumDetail(albumId);

    try {
      const payload = await promise;
      const latest = this.detailStatesByAlbumId[albumId];
      if (!latest || latest.requestId !== requestId) {
        return payload;
      }
      this.detailStatesByAlbumId = {
        ...this.detailStatesByAlbumId,
        [albumId]: {
          data: payload,
          loading: false,
          error: null,
          loaded: true,
          requestId,
          promise: null,
        },
      };
      this.emitAlbumDetail(albumId);
      return payload;
    } catch (err) {
      const latest = this.detailStatesByAlbumId[albumId];
      if (!latest || latest.requestId !== requestId) {
        throw err;
      }
      this.detailStatesByAlbumId = {
        ...this.detailStatesByAlbumId,
        [albumId]: {
          ...latest,
          loading: false,
          error: err instanceof Error ? err.message : errorMessage,
          loaded: true,
          promise: null,
        },
      };
      this.emitAlbumDetail(albumId);
      throw err;
    }
  }

  private emitAlbums() {
    for (const listener of this.albumListeners) {
      listener();
    }
  }

  private emitAlbumDetail(albumId: string) {
    const listeners = this.detailListenersByAlbumId.get(albumId);
    if (!listeners) {
      return;
    }
    for (const listener of listeners) {
      listener();
    }
  }
}

export const batchEditStore = new BatchEditStore();
