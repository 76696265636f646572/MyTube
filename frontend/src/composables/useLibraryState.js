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
      await fetchJson("/api/queue/add", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ url }),
      });
      notifySuccess("Added to queue", "URL added successfully.");
    } catch (error) {
      notifyError("Could not add URL", error);
    }
  }

  async function playUrl(url) {
    try {
      await fetchJson("/api/queue/play-now", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ url }),
      });
      notifySuccess("Playing now", "URL queued and playback started.");
    } catch (error) {
      notifyError("Could not play URL", error);
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

  async function clearHistory() {
    try {
      await fetchJson("/api/history", { method: "DELETE" });
      notifySuccess("History cleared", "Playback history removed.");
    } catch (error) {
      notifyError("Could not clear history", error);
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

  return {
    queue,
    history,
    playlists,
    addUrl,
    playUrl,
    createPlaylist,
    queuePlaylist,
    clearHistory,
    skipCurrent,
  };
}

export function initializeLibraryState() {
  if (initialized) return initPromise ?? Promise.resolve();
  initialized = true;
  subscribeSnapshot();
  initPromise = Promise.allSettled([refreshCore(), refreshPlaylists()]).then(() => {});
  return initPromise;
}
