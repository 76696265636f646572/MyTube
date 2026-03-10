import { ref } from "vue";

import { onEventBus } from "./eventBus";
import { fetchJson } from "./useApi";
import { useNotifications } from "./useNotifications";
import { usePlaybackState } from "./usePlaybackState";

const queue = ref([]);
const history = ref([]);
const playlists = ref([]);

let initialized = false;
let initPromise = null;
let unsubscribeWsSnapshot = null;

async function refreshPlaylists() {
  playlists.value = await fetchJson("/api/playlists");
}

async function refreshCore() {
  const [queueData, historyData] = await Promise.all([fetchJson("/api/queue"), fetchJson("/api/history")]);
  queue.value = queueData;
  history.value = historyData;
}

function applySnapshot(snapshot) {
  if (!snapshot || typeof snapshot !== "object") return;
  if (Array.isArray(snapshot.queue)) queue.value = snapshot.queue;
  if (Array.isArray(snapshot.history)) history.value = snapshot.history;
  if (Array.isArray(snapshot.playlists)) playlists.value = snapshot.playlists;
  if (snapshot.state && typeof snapshot.state === "object") {
    const { applyPlaybackState } = usePlaybackState();
    applyPlaybackState(snapshot.state);
  }
}

function subscribeSnapshot() {
  if (unsubscribeWsSnapshot) return;
  unsubscribeWsSnapshot = onEventBus("ws:snapshot", (payload) => {
    applySnapshot(payload);
  });
}

export function useLibraryState() {
  const { notifySuccess, notifyError } = useNotifications();

  async function addUrl(url) {
    try {
      const result = await fetchJson("/api/queue/add", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ url }),
      });
      if (result?.type === "playlist") {
        notifySuccess("Playlist queued", `${result.count || 0} playlist items added to queue.`);
      } else {
        notifySuccess("Added to queue", "URL added successfully.");
      }
    } catch (error) {
      notifyError("Could not add URL", error);
    }
  }

  async function playUrl(url) {
    try {
      const result = await fetchJson("/api/queue/play-now", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ url }),
      });
      if (result?.type === "playlist") {
        notifySuccess("Playing playlist", "Queue replaced and playlist playback started.");
      } else {
        notifySuccess("Playing now", "URL queued and playback started.");
      }
    } catch (error) {
      notifyError("Could not play URL", error);
    }
  }

  async function importPlaylistUrl(url) {
    try {
      const result = await fetchJson("/api/playlist/import", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ url }),
      });
      notifySuccess("Playlist imported", `${result.count || 0} items saved to playlist library.`);
    } catch (error) {
      notifyError("Could not import playlist", error);
    }
  }

  async function createPlaylist(title) {
    try {
      const created = await fetchJson("/api/playlists/custom", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ title }),
      });
      playlists.value = [created, ...playlists.value.filter((playlist) => playlist.id !== created.id)];
      notifySuccess("Playlist created", title);
      return created;
    } catch (error) {
      notifyError("Could not create playlist", error);
      return null;
    }
  }

  async function queuePlaylist(playlistId) {
    try {
      await fetchJson(`/api/playlists/${playlistId}/queue`, { method: "POST" });
      notifySuccess("Playlist queued", "Items added to queue.");
    } catch (error) {
      notifyError("Could not queue playlist", error);
    }
  }

  async function playPlaylistNow(playlistId) {
    try {
      await fetchJson(`/api/playlists/${playlistId}/play-now`, { method: "POST" });
      notifySuccess("Playing now", "Playlist queued and playback started.");
    } catch (error) {
      notifyError("Could not play playlist", error);
    }
  }

  async function renamePlaylist(playlistId, title) {
    try {
      await fetchJson(`/api/playlists/${playlistId}`, {
        method: "PATCH",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ title: title.trim() }),
      });
      await refreshPlaylists();
      notifySuccess("Playlist renamed", title.trim());
    } catch (error) {
      notifyError("Could not rename playlist", error);
    }
  }

  async function setPlaylistPinned(playlistId, pinned) {
    try {
      await fetchJson(`/api/playlists/${playlistId}`, {
        method: "PATCH",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ pinned }),
      });
      await refreshPlaylists();
      notifySuccess(pinned ? "Playlist pinned" : "Playlist unpinned");
    } catch (error) {
      notifyError(pinned ? "Could not pin playlist" : "Could not unpin playlist", error);
    }
  }

  async function deletePlaylist(playlistId) {
    try {
      await fetchJson(`/api/playlists/${playlistId}`, { method: "DELETE" });
      await refreshPlaylists();
      notifySuccess("Playlist deleted");
    } catch (error) {
      notifyError("Could not delete playlist", error);
    }
  }

  async function clearHistory() {
    try {
      await fetchJson("/api/history", { method: "DELETE" });
      notifySuccess("History cleared", "Playback history removed.");
    } catch (error) {
      notifyError("Could not clear history", error);
    }
  }

  async function clearQueue() {
    try {
      await fetchJson("/api/queue", { method: "DELETE" });
      notifySuccess("Queue cleared", "Queued tracks removed.");
    } catch (error) {
      notifyError("Could not clear queue", error);
    }
  }

  async function skipCurrent() {
    try {
      await fetchJson("/api/queue/skip", { method: "POST" });
      notifySuccess("Skipped", "Moved to the next item.");
    } catch (error) {
      notifyError("Could not skip", error);
    }
  }

  async function previousTrack() {
    try {
      await fetchJson("/api/playback/previous", { method: "POST" });
    } catch (error) {
      notifyError("Could not go back", error);
    }
  }

  async function togglePause() {
    try {
      await fetchJson("/api/playback/toggle-pause", { method: "POST" });
    } catch (error) {
      notifyError("Could not toggle pause", error);
    }
  }

  async function setRepeatMode(mode) {
    try {
      await fetchJson("/api/playback/repeat", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ mode }),
      });
    } catch (error) {
      notifyError("Could not change repeat mode", error);
    }
  }

  async function setShuffleEnabled(enabled) {
    try {
      const result = await fetchJson("/api/playback/shuffle", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ enabled }),
      });
      const { playbackState, applyPlaybackState } = usePlaybackState();
      applyPlaybackState({
        ...playbackState.value,
        shuffle_enabled: !!result?.enabled,
      });
      await refreshCore();
    } catch (error) {
      notifyError("Could not change shuffle", error);
    }
  }

  async function seekToPercent(percent) {
    try {
      await fetchJson("/api/playback/seek", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ percent }),
      });
    } catch (error) {
      notifyError("Could not seek track", error);
    }
  }

  return {
    queue,
    history,
    playlists,
    addUrl,
    playUrl,
    importPlaylistUrl,
    createPlaylist,
    queuePlaylist,
    playPlaylistNow,
    renamePlaylist,
    setPlaylistPinned,
    deletePlaylist,
    clearHistory,
    clearQueue,
    skipCurrent,
    previousTrack,
    togglePause,
    setRepeatMode,
    setShuffleEnabled,
    seekToPercent,
  };
}

export function initializeLibraryState() {
  if (initialized) return initPromise ?? Promise.resolve();
  initialized = true;
  subscribeSnapshot();
  initPromise = Promise.allSettled([refreshCore(), refreshPlaylists()]).then(() => {});
  return initPromise;
}
