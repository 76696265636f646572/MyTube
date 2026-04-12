<template>
  <aside class="min-h-0 h-full overflow-hidden rounded-xl border border-neutral-700 p-3 flex flex-col surface-panel">
    <div class="flex items-center justify-between gap-2 pr-1">
      <h2 class="text-2xl font-bold">Playlists</h2>
      <UButton
        class="justify-center cursor-pointer"
        color="neutral"
        variant="soft"
        size="md"
        icon="i-bi-plus-lg"
        @click="openCreateModal"
      >
        New playlist
      </UButton>
    </div>
    
    <div class="grid grid-cols-2 gap-2 mt-3 pr-1">
      <!-- Search for playlists -->
       <div class="flex-1">
      <UInput
          v-model="playlistSearchTerm"
          type="text"
          placeholder="Search for playlists"
        >
          
          <template v-if="playlistSearchTerm?.length" #trailing>
            <UButton
              color="neutral"
              variant="link"
              size="sm"
              class="cursor-pointer"
              icon="i-lucide-circle-x"
              aria-label="Clear input"
              @click="playlistSearchTerm = ''"
            />
          </template>
        </UInput>
      </div>
      <div class="flex justify-end shrink-0 ">
        <UDropdownMenu :items="sortOptions">
          <UButton color="neutral" variant="ghost">
            {{ sortOrder.label }}
            <UIcon name="i-bi-list-task" class="size-4" />
          </UButton>
        </UDropdownMenu>
      </div>
    </div>

    <div
      class="mt-3 min-h-0 flex-1 overflow-auto pr-1"
      @click="(e) => e.target === e.currentTarget && selectPlaylist(router, null)"
    >
      <template v-if="filteredPinnedPlaylists.length">
        <VueDraggable
          v-if="canDragReorder"
          v-model="pinnedPlaylists"
          tag="ul"
          class="space-y-2"
          :animation="150"
          :delay="200"
          :delay-on-touch-only="true"
          ghost-class="queue-drag-ghost"
          chosen-class="queue-drag-chosen"
          @end="(evt) => onReorderEnd(evt, true)"
        >
          <PlaylistItem
            v-for="playlist in pinnedPlaylists"
            :key="playlist.id"
            :playlist="playlist"
            :active-playlist-id="activePlaylistId"
            :is-remote-playlist="isRemotePlaylist"
            :thumbnail-src="playlistThumbnailSrc(playlist)"
            :label="playlistLabel(playlist)"
            @click="onPlaylistClick"
            @clear-active-playlist="clearActivePlaylist"
          />
        </VueDraggable>

        <ul v-else class="space-y-2">
          <PlaylistItem
            v-for="playlist in filteredPinnedPlaylists"
            :key="playlist.id"
            :playlist="playlist"
            :active-playlist-id="activePlaylistId"
            :is-remote-playlist="isRemotePlaylist"
            :thumbnail-src="playlistThumbnailSrc(playlist)"
            :label="playlistLabel(playlist)"
            @click="onPlaylistClick"
            @clear-active-playlist="clearActivePlaylist"
          />
        </ul>
      </template>

      <template v-if="filteredUnpinnedPlaylists.length">
        <VueDraggable
          v-if="canDragReorder"
          v-model="unpinnedPlaylists"
          tag="ul"
          :class="pinnedPlaylists.length ? 'mt-2 space-y-2' : 'space-y-2'"
          :animation="150"
          :delay="200"
          :delay-on-touch-only="true"
          ghost-class="queue-drag-ghost"
          chosen-class="queue-drag-chosen"
          @end="(evt) => onReorderEnd(evt, false)"
        >
          <PlaylistItem
            v-for="playlist in unpinnedPlaylists"
            :key="playlist.id"
            :playlist="playlist"
            :active-playlist-id="activePlaylistId"
            :is-remote-playlist="isRemotePlaylist"
            :thumbnail-src="playlistThumbnailSrc(playlist)"
            :label="playlistLabel(playlist)"
            @click="onPlaylistClick"
            @clear-active-playlist="clearActivePlaylist"
          />
        </VueDraggable>

        <ul v-else :class="filteredUnpinnedPlaylists.length ? 'mt-2 space-y-2' : 'space-y-2'">
          <PlaylistItem
            v-for="playlist in filteredUnpinnedPlaylists"
            :key="playlist.id"
            :playlist="playlist"
            :active-playlist-id="activePlaylistId"
            :is-remote-playlist="isRemotePlaylist"
            :thumbnail-src="playlistThumbnailSrc(playlist)"
            :label="playlistLabel(playlist)"
            @click="onPlaylistClick"
            @clear-active-playlist="clearActivePlaylist"
          />
        </ul>
      </template>
    </div>

    <UModal v-model:open="createModalOpen" :ui="{ width: 'max-w-sm' }">
      <template #content>
        <form class="p-4" @submit.prevent="submitCreatePlaylist">
          <h3 class="text-lg font-semibold">New playlist</h3>
          <input
            ref="createTitleInputRef"
            v-model="newTitle"
            type="text"
            class="mt-3 w-full rounded-md border px-3 py-2 text-sm surface-input"
            placeholder="Playlist name"
            required
            @keydown.enter.prevent="submitCreatePlaylist"
          />
          <div class="mt-4 flex justify-end gap-2">
            <UButton type="button" color="neutral" variant="ghost" @click="closeCreateModal">
              Cancel
            </UButton>
            <UButton type="submit" color="primary" variant="solid">
              Create
            </UButton>
          </div>
        </form>
      </template>
    </UModal>
  </aside>
</template>

<script setup>
import { computed, nextTick, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { VueDraggable } from "vue-draggable-plus";
import PlaylistItem from "./PlaylistItem.vue";

import { useBreakpoint } from "../composables/useBreakpoint";
import { useLibraryState } from "../composables/useLibraryState";
import { useUiState } from "../composables/useUiState";

const SIDEBAR_SORT_MODE_STORAGE_KEY = "airwave:ui:sidebar-playlists:sort-mode";
const DEFAULT_SORT_MODE = "custom";

const newTitle = ref("");
const createModalOpen = ref(false);
const createTitleInputRef = ref(null);
const router = useRouter();
const { isMobile } = useBreakpoint();
const {
  playlists,
  createPlaylist,
  importPlaylistUrl,
  reorderSidebarPlaylist,
} = useLibraryState();
const { activePlaylistId, selectPlaylist } = useUiState();
const pinnedPlaylists = ref([]);
const unpinnedPlaylists = ref([]);

const playlistSearchTerm = ref("");
const sortMode = ref(DEFAULT_SORT_MODE);

function loadSortMode() {
  try {
    const raw = localStorage.getItem(SIDEBAR_SORT_MODE_STORAGE_KEY);
    if (!raw) return DEFAULT_SORT_MODE;
    return raw;
  } catch {
    return DEFAULT_SORT_MODE;
  }
}

function saveSortMode(nextMode) {
  try {
    localStorage.setItem(SIDEBAR_SORT_MODE_STORAGE_KEY, nextMode);
  } catch {
    // ignore
  }
}

sortMode.value = loadSortMode();

const SORT_OPTIONS = [
  { label: "Custom", value: "custom", icon: "i-bi-list-check" },
  { label: "Recently Played", value: "recent", icon: "i-bi-clock-fill" },
  { label: "Recently Added", value: "recently-added", icon: "i-bi-plus-lg" },
  { label: "Alphabetical", value: "alphabetical", icon: "i-bi-sort-alpha-down" },
];

const sortOrder = computed(() => {
  return SORT_OPTIONS.find((o) => o.value === sortMode.value) || SORT_OPTIONS[0];
});

watch(
  sortMode,
  (val) => {
    saveSortMode(val);
  },
  { immediate: false },
);

function isRemotePlaylist(playlist) {
  return playlist?.kind === "remote_youtube";
}

function stableIndexMap(items) {
  const map = new Map();
  items.forEach((item, idx) => {
    map.set(item?.id, idx);
  });
  return map;
}

function toEpochMillis(isoString) {
  if (!isoString) return null;
  const t = Date.parse(isoString);
  if (Number.isNaN(t)) return null;
  return t;
}

function sortWithinGroup(items, mode, stableOrder) {
  if (mode === "custom") return items.slice();
  const next = items.slice();
  next.sort((a, b) => {
    if (mode === "alphabetical") {
      const at = (a?.title || "").toLowerCase();
      const bt = (b?.title || "").toLowerCase();
      if (at < bt) return -1;
      if (at > bt) return 1;
    } else if (mode === "recent") {
      const av = toEpochMillis(a?.last_played_at);
      const bv = toEpochMillis(b?.last_played_at);
      if (av != null || bv != null) {
        if (av == null) return 1;
        if (bv == null) return -1;
        if (av !== bv) return bv - av;
      }
    } else if (mode === "recently-added") {
      const av = toEpochMillis(a?.created_at);
      const bv = toEpochMillis(b?.created_at);
      if (av != null || bv != null) {
        if (av == null) return 1;
        if (bv == null) return -1;
        if (av !== bv) return bv - av;
      }
    }

    const ai = stableOrder.get(a?.id);
    const bi = stableOrder.get(b?.id);
    if (ai == null && bi == null) return 0;
    if (ai == null) return 1;
    if (bi == null) return -1;
    return ai - bi;
  });
  return next;
}

const filteredPinnedPlaylists = computed(() => {
  const term = playlistSearchTerm.value.toLowerCase();
  const base = pinnedPlaylists.value.filter((playlist) => playlist.title.toLowerCase().includes(term));
  const stable = stableIndexMap(pinnedPlaylists.value);
  return sortWithinGroup(base, sortMode.value, stable);
});

const filteredUnpinnedPlaylists = computed(() => {
  const term = playlistSearchTerm.value.toLowerCase();
  const base = unpinnedPlaylists.value.filter((playlist) => playlist.title.toLowerCase().includes(term));
  const stable = stableIndexMap(unpinnedPlaylists.value);
  return sortWithinGroup(base, sortMode.value, stable);
});

const sortOptions = computed(() => {
  return SORT_OPTIONS.map((opt) => ({
    label: opt.label,
    icon: opt.icon,
    onSelect: () => {
      sortMode.value = opt.value;
    },
  }));
});

const canDragReorder = computed(() => {
  // Touch + draggable fights row clicks; reorder from desktop/tablet sidebar only.
  if (isMobile.value) return false;
  return sortMode.value === "custom" && !playlistSearchTerm.value.trim() && playlistSearchTerm.value.length === 0;
});

function onPlaylistClick(playlist) {
  if (isRemotePlaylist(playlist)) {
    importPlaylistUrl(playlist.source_url);
    return;
  }
  const playlistId = playlist?.id;
  if (activePlaylistId.value === playlistId) {
    selectPlaylist(router, null);
  } else {
    selectPlaylist(router, playlistId);
  }
}

function clearActivePlaylist() {
  selectPlaylist(router, null);
}

function playlistLabel(playlist) {
  if (playlist?.kind === "remote_youtube") return "youtube";
  return playlist?.kind || "playlist";
}

watch(
  [playlists, sortMode],
  ([items]) => {
    const next = Array.isArray(items) ? items : [];
    if (sortMode.value === "custom") {
      pinnedPlaylists.value = next.filter((playlist) => !!playlist?.pinned);
      unpinnedPlaylists.value = next.filter((playlist) => !playlist?.pinned);
    } else {
      unpinnedPlaylists.value = next;
      pinnedPlaylists.value = [];
    }
  },
  { immediate: true },
);

function openCreateModal() {
  newTitle.value = "";
  createModalOpen.value = true;
  nextTick(() => createTitleInputRef.value?.focus?.());
}

function closeCreateModal() {
  createModalOpen.value = false;
  newTitle.value = "";
}

function submitCreatePlaylist() {
  const title = newTitle.value.trim();
  if (!title) return;
  createPlaylist(title);
  closeCreateModal();
}

async function onReorderEnd(evt, pinned) {
  if (!canDragReorder.value) return;
  const { oldIndex, newIndex } = evt;
  if (oldIndex === newIndex) return;
  const list = pinned ? pinnedPlaylists.value : unpinnedPlaylists.value;
  const playlist = list[newIndex];
  if (!playlist?.id) return;
  await reorderSidebarPlaylist(playlist.id, newIndex, pinned);
}

function playlistThumbnailSrc(playlist) {
  if (!playlist) return "";
  return playlist.thumbnail_url || "";
}
</script>
