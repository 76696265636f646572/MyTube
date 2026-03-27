import { ref } from "vue";

import { onEventBus } from "./eventBus";
import { useDuplicateModal } from "./useDuplicateModal";
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

  async function startSpotifyImportFromUrl(url, router) {
    try {
      const result = await fetchJson("/api/spotify/import", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ url }),
      });
      const pid = result?.playlist_id;
      if (pid && router) {
        notifySuccess("Spotify playlist", "Matching tracks from providers…");
        await router.push(`/spotify-import/${pid}`);
      }
    } catch (error) {
      notifyError("Could not import Spotify playlist", error);
    }
  }

  async function importPlaylistIntoPlaylist(url, targetPlaylistId) {
    if (!targetPlaylistId) return;
    const { showDuplicateModal } = useDuplicateModal();
    try {
      const result = await fetchJson("/api/playlist/import", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ url, target_playlist_id: targetPlaylistId, import_mode: "check" }),
      });
      if (result?.has_duplicates) {
        showDuplicateModal({
          targetPlaylistTitle: result.target_playlist_title,
          onAddAll: async () => {
            const r = await fetchJson("/api/playlist/import", {
              method: "POST",
              headers: { "content-type": "application/json" },
              body: JSON.stringify({
                url,
                target_playlist_id: targetPlaylistId,
                import_mode: "add_all",
              }),
            });
            notifySuccess("Playlist imported", `${r.count ?? result.total ?? 0} items added to playlist.`);
          },
          onAddNewOnes: async () => {
            const r = await fetchJson("/api/playlist/import", {
              method: "POST",
              headers: { "content-type": "application/json" },
              body: JSON.stringify({
                url,
                target_playlist_id: targetPlaylistId,
                import_mode: "skip_duplicates",
              }),
            });
            if (r?.skipped_duplicates && r?.count === 0) {
              notifySuccess("Already added", "All items are already in the playlist.");
            } else {
              notifySuccess("Playlist imported", `${r.count ?? r.new_count ?? 0} new items added.`);
            }
          },
        });
      } else {
        notifySuccess("Playlist imported", `${result.count || 0} items added to playlist.`);
      }
    } catch (error) {
      notifyError("Could not import playlist", error);
    }
  }

  async function addUrlToPlaylist(playlistId, url) {
    const { showDuplicateModal } = useDuplicateModal();
    try {
      const result = await fetchJson(`/api/playlists/${playlistId}/entries`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ url, import_mode: "check" }),
      });
      if (result?.has_duplicates) {
        showDuplicateModal({
          targetPlaylistTitle: result.target_playlist_title,
          onAddAll: async () => {
            await fetchJson(`/api/playlists/${playlistId}/entries`, {
              method: "POST",
              headers: { "content-type": "application/json" },
              body: JSON.stringify({ url, import_mode: "add_all" }),
            });
            notifySuccess("Saved to playlist", "Item added to playlist.");
          },
          onAddNewOnes: async () => {
            const r = await fetchJson(`/api/playlists/${playlistId}/entries`, {
              method: "POST",
              headers: { "content-type": "application/json" },
              body: JSON.stringify({ url, import_mode: "skip_duplicates" }),
            });
            if (r?.skipped_duplicates) {
              notifySuccess("Already added", "This item is already in the playlist.");
            } else {
              notifySuccess("Saved to playlist", "Item added to playlist.");
            }
          },
        });
      } else {
        notifySuccess("Saved to playlist", "Item added to playlist.");
      }
    } catch (error) {
      notifyError("Could not save to playlist", error);
    }
  }

  async function addEntriesToPlaylist(playlistId, entries, { onComplete } = {}) {
    if (!playlistId || !entries?.length) return;
    const { showDuplicateModal } = useDuplicateModal();
    const payload = entries.map((e) => ({
      source_url: e.source_url,
      normalized_url: e.normalized_url ?? e.source_url,
      provider: e.provider ?? null,
      provider_item_id: e.provider_item_id ?? null,
      title: e.title ?? null,
      channel: e.channel ?? null,
      duration_seconds: e.duration_seconds ?? null,
      thumbnail_url: e.thumbnail_url ?? null,
    }));
    const runComplete = () => {
      if (typeof onComplete === "function") onComplete();
    };
    try {
      const result = await fetchJson(`/api/playlists/${playlistId}/entries/batch`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ entries: payload, import_mode: "check" }),
      });
      if (result?.has_duplicates) {
        showDuplicateModal({
          targetPlaylistTitle: result.target_playlist_title,
          onAddAll: async () => {
            const r = await fetchJson(`/api/playlists/${playlistId}/entries/batch`, {
              method: "POST",
              headers: { "content-type": "application/json" },
              body: JSON.stringify({ entries: payload, import_mode: "add_all" }),
            });
            notifySuccess("Added to playlist", `${r.count ?? 0} items added.`);
            runComplete();
          },
          onAddNewOnes: async () => {
            const r = await fetchJson(`/api/playlists/${playlistId}/entries/batch`, {
              method: "POST",
              headers: { "content-type": "application/json" },
              body: JSON.stringify({ entries: payload, import_mode: "skip_duplicates" }),
            });
            if (r?.skipped_duplicates && r?.count === 0) {
              notifySuccess("Already added", "All items are already in the playlist.");
            } else {
              notifySuccess("Added to playlist", `${r.count ?? 0} new items added.`);
            }
            runComplete();
          },
        });
      } else {
        notifySuccess("Added to playlist", `${result?.count ?? entries.length} items added.`);
        runComplete();
      }
    } catch (error) {
      notifyError("Could not add to playlist", error);
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

  async function updatePlaylist(playlistId, { title, description }) {
    try {
      const body = {};
      if (title !== undefined) body.title = title.trim();
      if (description !== undefined) body.description = description.trim();
      if (Object.keys(body).length === 0) return;
      await fetchJson(`/api/playlists/${playlistId}`, {
        method: "PATCH",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
      });
      await refreshPlaylists();
      notifySuccess("Playlist updated");
    } catch (error) {
      notifyError("Could not update playlist", error);
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

  async function reorderQueueItem(itemId, newPosition) {
    try {
      await fetchJson(`/api/queue/${itemId}/reorder`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ new_position: newPosition }),
      });
      await refreshCore();
    } catch (error) {
      notifyError("Could not reorder queue", error);
    }
  }

  async function reorderPlaylistEntry(entryId, newPosition) {
    try {
      await fetchJson(`/api/playlists/entries/${entryId}/reorder`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ new_position: newPosition }),
      });
    } catch (error) {
      notifyError("Could not reorder playlist", error);
    }
  }

  async function reorderSidebarPlaylist(playlistId, newPosition, pinned) {
    try {
      await fetchJson("/api/playlists/reorder", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          playlist_id: String(playlistId),
          new_position: newPosition,
          pinned: !!pinned,
        }),
      });
      await refreshPlaylists();
    } catch (error) {
      notifyError("Could not reorder playlists", error);
      await refreshPlaylists();
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
    startSpotifyImportFromUrl,
    importPlaylistIntoPlaylist,
    addUrlToPlaylist,
    addEntriesToPlaylist,
    createPlaylist,
    queuePlaylist,
    playPlaylistNow,
    updatePlaylist,
    setPlaylistPinned,
    deletePlaylist,
    clearHistory,
    clearQueue,
    reorderQueueItem,
    reorderPlaylistEntry,
    reorderSidebarPlaylist,
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
