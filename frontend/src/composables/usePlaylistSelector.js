import { computed, ref, unref } from "vue";

/**
 * Shared logic for playlist selector dropdown with search.
 * @param {import('vue').MaybeRefOrGetter<Array>} playlists - Playlist list (ref, computed, or getter)
 * @returns {{ playlistSearchTerm: import('vue').Ref<string>, localPlaylists: import('vue').ComputedRef<Array>, filteredPlaylists: import('vue').ComputedRef<Array>, resetSearch: () => void }}
 */
export function usePlaylistSelector(playlists) {
  const playlistSearchTerm = ref("");

  const localPlaylists = computed(() => {
    const list = typeof playlists === "function" ? playlists() : unref(playlists);
    return (list ?? []).filter((p) => p?.kind !== "remote_youtube");
  });

  const filteredPlaylists = computed(() => {
    const term = playlistSearchTerm.value.toLowerCase().trim();
    if (!term) return localPlaylists.value;
    return localPlaylists.value.filter((p) => (p.title || "").toLowerCase().includes(term));
  });

  function resetSearch() {
    playlistSearchTerm.value = "";
  }

  return { playlistSearchTerm, localPlaylists, filteredPlaylists, resetSearch };
}
