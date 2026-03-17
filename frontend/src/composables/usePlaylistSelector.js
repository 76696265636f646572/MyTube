import { computed, ref, unref } from "vue";

/**
 * Shared logic for playlist selector dropdown with search.
 * @param {import('vue').MaybeRefOrGetter<Array>} playlists - Playlist list (ref, computed, or getter)
 * @returns {{ playlistSearchTerm: import('vue').Ref<string>, filteredPlaylists: import('vue').ComputedRef<Array>, resetSearch: () => void }}
 */
export function usePlaylistSelector(playlists) {
  const playlistSearchTerm = ref("");

  const filteredPlaylists = computed(() => {
    const term = playlistSearchTerm.value.toLowerCase().trim();
    const list = typeof playlists === "function" ? playlists() : unref(playlists);
    const localPlaylists = (list ?? []).filter((p) => p?.kind !== "remote_youtube");
    if (!term) return localPlaylists;
    return localPlaylists.filter((p) => (p.title || "").toLowerCase().includes(term));
  });

  function resetSearch() {
    playlistSearchTerm.value = "";
  }

  return { playlistSearchTerm, filteredPlaylists, resetSearch };
}
