<template>
  <section class="min-h-0 h-full flex flex-col rounded-xl border border-neutral-700 p-6 overflow-hidden surface-panel">
    <div v-if="loading" class="text-sm text-muted">Loading playlist...</div>
    <div v-else-if="notFound" class="text-sm text-red-300">Playlist not found.</div>
    <div v-else-if="errorMessage" class="text-sm text-red-300">{{ errorMessage }}</div>

    <template v-else>
      <template v-if="isRadioEphemeralView">
        <div class="flex flex-col gap-4 sm:flex-row sm:items-end sm:gap-6">
          <div class="shrink-0">
            <img
              v-if="firstTrackThumbnail"
              :src="firstTrackThumbnail"
              :alt="radioDisplayTitle"
              class="h-40 w-40 rounded-lg object-cover sm:h-48 sm:w-48 surface-elevated shadow-lg"
            />
            <div
              v-else
              class="flex h-40 w-40 items-center justify-center rounded-lg bg-neutral-700/50 sm:h-48 sm:w-48 surface-elevated"
            >
              <UIcon name="i-bi-music-note-beamed" class="size-16 text-muted" />
            </div>
          </div>
          <div class="min-w-0 flex-1">
            <h2 class="text-2xl font-bold tracking-tight sm:text-3xl">{{ radioDisplayTitle }}</h2>
            <p v-if="radioSeed?.artist" class="mt-1 text-sm text-muted">Seed: {{ radioSeed.artist }} — {{ radioSeed.track }}</p>
            <p class="mt-2 text-sm text-muted">
              {{ songCount }} {{ songCount === 1 ? "song" : "songs" }}, {{ formattedTotalDuration }}
            </p>
          </div>
        </div>

        <div class="mt-4 mb-2 flex flex-wrap items-center gap-2">
          <UButton
            type="button"
            color="primary"
            variant="solid"
            size="sm"
            icon="i-bi-download"
            :disabled="!entries.length || radioSaving"
            @click="saveRadioToLibrary"
          >
            Save to library
          </UButton>
          <UButton
            type="button"
            color="primary"
            variant="solid"
            size="sm"
            icon="i-bi-play-fill"
            :disabled="!playableRadioEntries.length"
            @click="playRadioAll"
          >
            Play now
          </UButton>
          <UButton
            type="button"
            color="neutral"
            variant="soft"
            size="sm"
            icon="i-bi-music-note-list"
            :disabled="!playableRadioEntries.length"
            @click="queueRadioAll"
          >
            Queue
          </UButton>
          <UInput
            v-model="songSearchTerm"
            type="text"
            class="min-w-[12rem] flex-1"
            placeholder="Search for songs in playlist"
          >
            <template v-if="songSearchTerm?.length" #trailing>
              <UButton
                color="neutral"
                variant="link"
                size="sm"
                class="cursor-pointer"
                icon="i-lucide-circle-x"
                aria-label="Clear input"
                @click="songSearchTerm = ''"
              />
            </template>
          </UInput>
        </div>

        <div v-if="radioNotice" class="mt-2 text-sm text-muted">
          {{ radioNotice }}
        </div>
        <div
          v-if="showRadioCatalogProgress"
          class="mt-4 rounded-lg border border-neutral-700/60 bg-neutral-900/30 p-4"
          role="status"
          aria-live="polite"
        >
          <div class="flex items-center gap-2 text-sm font-medium text-neutral-200">
            <UIcon
              name="i-lucide-loader-circle"
              class="size-5 shrink-0 text-muted"
              :class="{ 'animate-spin': radioSuggestionsLoading || radioCatalogActive }"
            />
            <span>{{ radioCatalogProgressTitle }}</span>
          </div>
          <p v-if="radioCatalogProgress?.message" class="mt-2 text-sm text-muted">
            {{ radioCatalogProgress.message }}
          </p>
          <UProgress
            :model-value="radioCatalogProgressBar"
            :max="100"
            size="sm"
            class="mt-3"
          />
          <p v-if="radioCatalogEtaLabel" class="mt-2 text-xs text-muted">
            {{ radioCatalogEtaLabel }}
          </p>
        </div>
        <div v-if="radioCatalogMessage" class="mt-2 text-sm text-amber-200/90">
          {{ radioCatalogMessage }}
        </div>
        <div v-if="!entries.length && !showRadioCatalogProgress" class="mt-6 text-sm text-muted">
          No suggestions yet. Try again later, or check the notice above.
        </div>
        <UScrollArea
          v-else
          :ui="{ viewport: 'mt-6 gap-2' }"
          class="h-full min-h-0 flex-1"
        >
          <ul class="space-y-2">
            <li v-for="(entry, idx) in filteredEntries" :key="`radio-${idx}-${entry.source_url || idx}`">
              <Song
                :item="entry"
                mode="search"
                :playlists="playlists"
              />
            </li>
          </ul>
        </UScrollArea>
      </template>

      <template v-else>
      <!-- Hero section -->
      <div class="flex flex-col gap-4 sm:flex-row sm:items-end sm:gap-6">
        <div class="shrink-0">
          <img
            v-if="firstTrackThumbnail"
            :src="firstTrackThumbnail"
            :alt="playlist.title || 'Playlist'"
            class="h-40 w-40 rounded-lg object-cover sm:h-48 sm:w-48 surface-elevated shadow-lg"
          />
          <div
            v-else
            class="flex h-40 w-40 items-center justify-center rounded-lg bg-neutral-700/50 sm:h-48 sm:w-48 surface-elevated"
          >
            <UIcon name="i-bi-music-note-beamed" class="size-16 text-muted" />
          </div>
        </div>
        <div class="min-w-0 flex-1">
          <h2 class="text-2xl font-bold tracking-tight sm:text-3xl">{{ playlist.title || "Untitled playlist" }}</h2>
          <p v-if="playlist.description" class="mt-1 text-sm text-muted">{{ playlist.description }}</p>
          <p class="mt-2 text-sm text-muted">
            {{ songCount }} {{ songCount === 1 ? "song" : "songs" }}, {{ formattedTotalDuration }}
          </p>
        </div>
      </div>

      <!-- Action row -->
      <div class="mt-4 mb-2 flex items-center gap-2">
        <template v-if="isRemotePlaylistView">
          <UButton
            type="button"
            color="primary"
            variant="solid"
            size="sm"
            icon="i-bi-download"
            @click="importRemotePlaylist"
          >
            Import playlist
          </UButton>
        </template>
        <template v-else>
        <UButton
          type="button"
          color="primary"
          variant="solid"
          size="lg"
          icon="i-bi-play-fill"
          :ui="{ rounded: 'rounded-full' }"
          :disabled="!entries.length"
          aria-label="Play playlist"
          @click="playPlaylistNow(playlist.id)"
        />
        <div v-if="isPlaylistSyncable(playlist) && playlist.can_edit" class="flex items-center">
          <UButton
            type="button"
            :color="playlist.sync_enabled ? 'primary' : 'neutral'"
            :variant="playlist.sync_enabled ? 'solid' : 'ghost'"
            size="lg"
            icon="i-bi-arrow-repeat"
            :class="playlist.sync_enabled ? 'cursor-pointer mr-0 rounded-r-none' : 'cursor-pointer'"
            :ui="{ rounded: 'rounded-full' }"
            :model-value="!!playlist.sync_enabled"
            aria-label="Toggle auto-sync playlist"
            @click="setSyncEnabled(!playlist.sync_enabled)"
          >
          </UButton>
           
          <UTooltip text="Remove tracks missing in upstream">
            <UButton
              type="button"
              :color="playlist.sync_remove_missing ? 'error' : 'neutral'"
              :variant="playlist.sync_remove_missing ? 'soft' : 'ghost'"
              size="lg"
              icon="i-bi-trash-fill"
              :class="playlist.sync_enabled ? 'cursor-pointer ml-0 rounded-l-none ' : 'invisible'"
              :ui="{ rounded: 'rounded-full' }"
              :model-value="!!playlist.sync_remove_missing"
              aria-label="Toggle remove tracks missing in upstream"
              @click="setSyncRemoveMissing(!playlist.sync_remove_missing)"
            >
            </UButton>
          </UTooltip>
        </div>
        <UDropdownMenu :items="dropdownItems" :ui="{ separator: 'hidden' }" @update:open="(open) => !open && resetSearch()">
          <template #playlist-filter>
            <PlaylistSelectorFilter
              v-model="playlistSearchTerm"
              placeholder="Find a playlist"
              @playlist-created="onAddToNewPlaylistFromPage"
            />
          </template>
          <UButton
            type="button"
            icon="i-bi-three-dots"
            color="neutral"
            variant="ghost"
            size="lg"
            aria-label="More actions"
            class="cursor-pointer"
          />
        </UDropdownMenu>
        </template>
        <!-- Search for songs in playlist -->
        <UInput
          v-model="songSearchTerm"
          type="text"
          placeholder="Search for songs in playlist"
        >
          
          <template v-if="songSearchTerm?.length" #trailing>
            <UButton
              color="neutral"
              variant="link"
              size="sm"
              class="cursor-pointer"
              icon="i-lucide-circle-x"
              aria-label="Clear input"
              @click="songSearchTerm = ''"
            />
          </template>
        </UInput>
      </div>

      <div v-if="isRemotePlaylistView" class="mt-6 text-sm text-muted">
        This playlist is from your YouTube account and is not in the local library yet.
      </div>
      <div
        v-if="!isRemotePlaylistView"
        class="mt-2 mb-4 flex flex-col gap-2  rounded-lg border border-neutral-700/60 bg-neutral-900/20 p-3"
      >
        <div v-if="playlist.sync_enabled && playlist.can_edit" class="text-xs text-muted">
          {{ syncStatusText }}
        </div>
      </div>
      <div v-if="!isRemotePlaylistView && !entries.length" class="mt-6 text-sm text-muted">
        This playlist has no entries yet.
      </div>

      <UScrollArea
        v-if="!isRemotePlaylistView && entries.length"
        :ui="{ viewport: 'mt-6 gap-2' }"
        class="min-h-0 flex-1"
      >
        <VueDraggable
          v-model="entries"
          tag="ul"
          class="space-y-2"
          :animation="150"
          :delay="200"
          :delay-on-touch-only="true"
          ghost-class="queue-drag-ghost"
          chosen-class="queue-drag-chosen"
          @end="onReorderEnd"
        >
          <li v-for="entry in filteredEntries" :key="entry.id">
            <Song
              :item="entry"
              mode="search"
              :playlists="playlists"
              :playlist-id="playlist.id"
              :entry-id="entry.id"
              @deleted="onEntryDeleted"
            />
          </li>
        </VueDraggable>
      </UScrollArea>
      </template>
    </template>
  </section>

  <UModal v-model:open="editModalOpen" :ui="{ width: 'max-w-sm' }">
    <template #content>
      <form class="p-4" @submit.prevent="submitEdit">
        <h3 class="text-lg font-semibold">Edit playlist</h3>
        <input
          v-model="editTitle"
          type="text"
          class="mt-3 w-full rounded-md border px-3 py-2 text-sm surface-input"
          placeholder="Playlist name"
          @keydown.enter.prevent="submitEdit"
        />
        <textarea
          v-model="editDescription"
          class="mt-3 w-full rounded-md border px-3 py-2 text-sm surface-input resize-none"
          placeholder="Description (optional)"
          rows="3"
        />
        <div class="mt-4 flex justify-end gap-2">
          <UButton type="button" color="neutral" variant="ghost" @click="editModalOpen = false">
            Cancel
          </UButton>
          <UButton type="submit" color="primary" variant="solid">
            Save
          </UButton>
        </div>
      </form>
    </template>
  </UModal>

  <UModal v-model:open="deleteModalOpen" :ui="{ width: 'max-w-sm' }">
    <template #content>
      <div class="p-4">
        <h3 class="text-lg font-semibold">Delete playlist</h3>
        <p class="mt-2 text-sm text-muted">
          Delete "{{ playlistToDelete ? (playlistToDelete.title || 'Untitled playlist') : '' }}"?
          This cannot be undone.
        </p>
        <div class="mt-4 flex justify-end gap-2">
          <UButton type="button" color="neutral" variant="ghost" @click="deleteModalOpen = false">
            Cancel
          </UButton>
          <UButton
            type="button"
            color="error"
            variant="solid"
            @click="submitDelete"
          >
            Delete
          </UButton>
        </div>
      </div>
    </template>
  </UModal>
</template>

<script setup>
import { computed, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import { VueDraggable } from "vue-draggable-plus";
import Song from "../../components/Song.vue";
import PlaylistSelectorFilter from "../../components/PlaylistSelectorFilter.vue";
import { fetchJson } from "../../composables/useApi";
import { formatTotalDuration } from "../../composables/useDuration";
import { useLibraryState } from "../../composables/useLibraryState";
import { useNotifications } from "../../composables/useNotifications";
import { usePlaylistSelector } from "../../composables/usePlaylistSelector";
import { decodeRadioPlaylistSeed, isRadioPlaylistRouteId } from "../../utils/radioPlaylistRoute";

const {
  playlists,
  importPlaylistUrl,
  reorderPlaylistEntry,
  addUrl,
  playUrl,
  playPlaylistNow,
  clearQueue,
  queuePlaylist,
  addEntriesToPlaylist,
  createPlaylist,
  updatePlaylist,
  setPlaylistPinned,
  deletePlaylist,
} = useLibraryState();
const { notifySuccess, notifyError } = useNotifications();
const { playlistSearchTerm, filteredPlaylists, resetSearch } = usePlaylistSelector(() => playlists.value);
const route = useRoute();
const router = useRouter();
const playlist = ref({});
const entries = ref([]);
const radioSeed = ref(null);
const radioNotice = ref(null);
const radioCatalogMessage = ref(null);
/** Snapshot while MusicAtlas catalog ingestion is running (from API catalog_ingestion). */
const radioCatalogProgress = ref(null);
const radioSuggestionsLoading = ref(false);
const radioSaving = ref(false);
const loading = ref(false);
const notFound = ref(false);
const errorMessage = ref("");
const editModalOpen = ref(false);
const editTitle = ref("");
const editDescription = ref("");
const playlistToEdit = ref(null);
const deleteModalOpen = ref(false);
const playlistToDelete = ref(null);
const firstTrackThumbnail = computed(() => {
  if(playlist.value?.thumbnail_url) return playlist.value.thumbnail_url;
  const first = entries.value[0];
  if (first?.thumbnail_url) return first.thumbnail_url;
  if (first?.provider === "youtube" && first?.provider_item_id) {
    return `https://i.ytimg.com/vi/${first.provider_item_id}/hqdefault.jpg`;
  }
});
const songSearchTerm = ref("");

function playlistIdFromRoute() {
  const value = route.params.id;
  if (Array.isArray(value)) return value[0] || "";
  return typeof value === "string" ? value : "";
}

function playlistUpstreamSource(pl) {
  if (!pl) return "";
  return String(pl.source_url ?? pl.source ?? "").trim();
}

/** True when the playlist has an http(s) upstream (yt-dlp or Spotify web); excludes custom and app-internal URLs. */
function isPlaylistSyncable(pl) {
  const src = playlistUpstreamSource(pl);
  if (!src) return false;
  const lower = src.toLowerCase();
  if (lower.startsWith("custom://")) return false;
  if (lower.startsWith("airwave-pending://")) return false;
  return lower.startsWith("http://") || lower.startsWith("https://");
}

const isRadioEphemeralView = computed(() => isRadioPlaylistRouteId(playlistIdFromRoute()));

const songCount = computed(() => {
  if (isRadioEphemeralView.value) return entries.value.length;
  return entries.value.length || playlist.value?.entry_count || 0;
});

const radioDisplayTitle = computed(() => {
  const t = (radioSeed.value?.track || "").trim();
  return t ? `${t} Radio` : "Radio";
});

const radioCatalogActive = computed(
  () => !!(radioCatalogProgress.value && !radioCatalogProgress.value.terminal),
);

const showRadioCatalogProgress = computed(
  () => radioSuggestionsLoading.value || radioCatalogActive.value,
);

const radioCatalogProgressTitle = computed(() => {
  if (radioCatalogActive.value) {
    const st = (radioCatalogProgress.value?.status || "").trim();
    if (st) return `Adding track to MusicAtlas catalog...`;
    return "Adding track to MusicAtlas catalog…";
  }
  if (radioSuggestionsLoading.value) return "Loading suggestions…";
  return "";
});

function normalizeCatalogPercent(raw) {
  if (typeof raw !== "number" || !Number.isFinite(raw)) return null;
  if (raw >= 0 && raw <= 1) return Math.round(raw * 100);
  if (raw >= 0 && raw <= 100) return Math.round(raw);
  return Math.min(100, Math.max(0, Math.round(raw)));
}

const radioCatalogProgressBar = computed(() => {
  if (radioCatalogActive.value) {
    return normalizeCatalogPercent(radioCatalogProgress.value?.percent_complete);
  }
  if (radioSuggestionsLoading.value) {
    return null;
  }
  return null;
});

function formatEtaSeconds(raw) {
  if (typeof raw !== "number" || !Number.isFinite(raw) || raw < 0) return null;
  const n = Math.round(raw);
  if (n < 60) return `${n}s`;
  const m = Math.floor(n / 60);
  const r = n % 60;
  return r ? `${m}m ${r}s` : `${m}m`;
}

const radioCatalogEtaLabel = computed(() => {
  if (!radioCatalogActive.value) return "";
  const eta = radioCatalogProgress.value?.eta_seconds;
  const label = formatEtaSeconds(eta);
  return label ? `About ${label} remaining` : "";
});

function normalizeCatalogIngestion(raw) {
  if (!raw || typeof raw !== "object") return null;
  return {
    job_id: raw.job_id ?? null,
    status: raw.status != null ? String(raw.status) : "",
    message: raw.message != null ? String(raw.message) : "",
    percent_complete: typeof raw.percent_complete === "number" ? raw.percent_complete : null,
    eta_seconds: typeof raw.eta_seconds === "number" ? raw.eta_seconds : null,
    terminal: !!raw.terminal,
  };
}

const playableRadioEntries = computed(() =>
  entries.value.filter((e) => {
    const u = (e.source_url || "").trim();
    return u.startsWith("http://") || u.startsWith("https://");
  }),
);

const isRemotePlaylistView = computed(() => playlist.value?.kind === "remote_youtube");
const syncStatusText = computed(() => {
  const pl = playlist.value || {};
  if (!pl?.sync_enabled) return "Sync disabled.";
  const status = pl.last_sync_status || "";
  const okAt = pl.last_sync_succeeded_at;
  const startedAt = pl.last_sync_started_at;
  const okAtText = okAt ? new Date(okAt).toLocaleString() : null;
  const startedAtText = startedAt ? new Date(startedAt).toLocaleString() : null;
  if (status === "running") return "Sync in progress…";
  if (status === "error") {
    const err = pl.last_sync_error ? ` Error: ${pl.last_sync_error}` : "";
    return startedAtText ? `Last sync failed at ${startedAtText}.${err}` : `Last sync failed.${err}`;
  }
  if (okAtText) return `Last synced at ${okAtText}.`;
  return "Sync enabled. Waiting for next scheduled run.";
});

const totalDurationSeconds = computed(() =>
  entries.value.reduce((sum, e) => sum + (e.duration_seconds || 0), 0)
);

const formattedTotalDuration = computed(() => formatTotalDuration(totalDurationSeconds.value));

const filteredEntries = computed(() => {
  const term = songSearchTerm.value.toLowerCase().trim();
  if (!term) return entries.value;
  return entries.value.filter((e) => {
    const title = (e.title || "").toLowerCase();
    const channel = (e.channel || "").toLowerCase();
    const url = (e.source_url || "").toLowerCase();
    return title.includes(term) || channel.includes(term) || url.includes(term);
  });
});

function onEntryDeleted(entryId) {
  const id = Number(entryId);
  if (!Number.isFinite(id)) return;
  const idx = entries.value.findIndex((e) => e?.id === id);
  if (idx === -1) return;
  entries.value.splice(idx, 1);
  if (playlist.value && typeof playlist.value === "object") {
    const current = Number(playlist.value.entry_count);
    if (Number.isFinite(current) && current > 0) {
      playlist.value = { ...playlist.value, entry_count: current - 1 };
    }
  }
}

const dropdownItems = computed(() => {
  const pl = playlist.value;
  if (!pl?.id) return [];
  const items = [
      { label: "Queue", icon: "i-bi-music-note-list", class: "cursor-pointer", onSelect: () => queuePlaylist(pl.id) },
      { label: "Play now", icon: "i-bi-play-fill", class: "cursor-pointer", onSelect: () => playPlaylistNow(pl.id) },
  ];
  const otherPlaylists = (filteredPlaylists.value ?? []).filter((p) => p.id !== pl.id);
  if (entries.value.length > 0) {
    const addToPlaylistChildren = [
      { type: "label", slot: "playlist-filter" },
      ...otherPlaylists.map((p) => ({
        label: p.title || "Untitled playlist",
        onSelect: () => addAllEntriesToPlaylist(p.id, entries.value),
      })),
    ];
    items.push(
      {
        label: "Add to playlist",
        icon: "i-bi-plus",
        children: [addToPlaylistChildren],
      },
    );
  }
  const pinned = !!pl.pinned;
  items.push(
    { label: "Edit", icon: "i-bi-pencil-fill", class: "cursor-pointer", onSelect: () => openEditModal(pl) },
    {
      label: pinned ? "Unpin" : "Pin",
      icon: pinned ? "i-bi-pin" : "i-bi-pin-fill",
      class: "cursor-pointer",
      onSelect: () => setPlaylistPinned(pl.id, !pinned),
    },
    {
      label: "Delete",
      icon: "i-bi-trash-fill",
      class: "cursor-pointer",
      onSelect: () => openDeleteModal(pl),
      color: "error",
    },
  );
  return items;
});

async function addAllEntriesToPlaylist(targetPlaylistId, entriesToAdd) {
  const list = entriesToAdd ?? entries.value;
  await addEntriesToPlaylist(targetPlaylistId, list, { onComplete: loadPlaylist });
  resetSearch();
}

function onAddToNewPlaylistFromPage(created) {
  if (created?.id != null) addAllEntriesToPlaylist(created.id, entries.value);
}

function importRemotePlaylist() {
  if (!playlist.value?.source_url) return;
  importPlaylistUrl(playlist.value.source_url);
}

function openEditModal(pl) {
  playlistToEdit.value = pl;
  editModalOpen.value = true;
}

function openDeleteModal(pl) {
  playlistToDelete.value = pl;
  deleteModalOpen.value = true;
}

async function submitEdit() {
  const title = editTitle.value.trim();
  if (!title || !playlistToEdit.value) return;
  await updatePlaylist(playlistToEdit.value.id, {
    title,
    description: editDescription.value.trim(),
  });
  editModalOpen.value = false;
  playlistToEdit.value = null;
  loadPlaylist();
}

async function setSyncEnabled(enabled) {
  const pl = playlist.value;
  if (!pl?.id || !pl.can_edit) return;
  const updated = await updatePlaylist(pl.id, { sync_enabled: !!enabled }, { notify: false });
  if (updated) playlist.value = { ...pl, ...updated };
}

async function setSyncRemoveMissing(enabled) {
  const pl = playlist.value;
  if (!pl?.id || !pl.can_edit) return;
  const updated = await updatePlaylist(pl.id, { sync_remove_missing: !!enabled }, { notify: false });
  if (updated) playlist.value = { ...pl, ...updated };
}

async function submitDelete() {
  const pl = playlistToDelete.value;
  if (!pl) return;
  deleteModalOpen.value = false;
  playlistToDelete.value = null;
  await deletePlaylist(pl.id);
  router.push("/playlists");
}

let requestId = 0;

watch(playlistToEdit, (p) => {
  editTitle.value = p ? (p.title || "") : "";
  editDescription.value = p ? (p.description || "") : "";
});

const RADIO_CATALOG_MAX_MS = 120_000;
const RADIO_POLL_MS = 2000;

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function youtubeVideoIdFromWatchUrl(url) {
  try {
    const u = new URL(url);
    if (u.hostname.includes("youtube.com")) {
      const v = u.searchParams.get("v");
      return v ? v.trim() : null;
    }
    if (u.hostname === "youtu.be") {
      const id = u.pathname.replace(/^\//, "").trim();
      return id || null;
    }
  } catch {
    return null;
  }
  return null;
}

function buildPrependedSeedRow(seed) {
  const url = (seed.source_url || "").trim();
  if (!url.startsWith("http://") && !url.startsWith("https://")) return null;
  if ((seed.provider || "").toLowerCase() !== "youtube") return null;
  const vid = youtubeVideoIdFromWatchUrl(url);
  const thumb = vid ? `https://i.ytimg.com/vi/${vid}/hqdefault.jpg` : null;
  return {
    id: null,
    title: seed.title || seed.track,
    source_url: url,
    provider: "youtube",
    provider_item_id: vid,
    status: "suggested",
    queue_position: null,
    source_type: "video",
    channel: seed.channel || seed.artist,
    duration_seconds: null,
    thumbnail_url: thumb,
    playlist_id: null,
  };
}

function mergeRadioEntries(seed, apiItems) {
  const list = Array.isArray(apiItems) ? [...apiItems] : [];
  const row = buildPrependedSeedRow(seed);
  if (row?.source_url) {
    const dup = list.some((e) => (e.source_url || "").trim() === row.source_url);
    if (!dup) list.unshift(row);
  }
  return list;
}

function trimRadioMessage(value) {
  return String(value ?? "").trim() || null;
}

function radioNoticeFromBody(body) {
  if (!body || typeof body !== "object") return null;
  return trimRadioMessage(body.notice) || trimRadioMessage(body.message);
}

async function fetchRadioSuggestionsBody(seed, activeRequestId) {
  const params = new URLSearchParams({ artist: seed.artist, track: seed.track });
  const body = await fetchJson(`/api/musicatlas/suggestions?${params.toString()}`);
  if (activeRequestId !== requestId) return null;
  return body;
}

async function loadRadioPlaylist(playlistId, seed, activeRequestId) {
  radioNotice.value = null;
  radioCatalogMessage.value = null;
  radioCatalogProgress.value = null;
  entries.value = [];

  let body = await fetchRadioSuggestionsBody(seed, activeRequestId);
  if (!body) return;

  radioNotice.value = radioNoticeFromBody(body);

  let ing = body.catalog_ingestion;
  const initialItems = Array.isArray(body.items) ? body.items : [];

  if (ing?.job_id && !ing.terminal) {
    radioCatalogProgress.value = normalizeCatalogIngestion(ing);
    const started = Date.now();
    while (ing && !ing.terminal && Date.now() - started < RADIO_CATALOG_MAX_MS) {
      if (activeRequestId !== requestId) return;
      await sleep(RADIO_POLL_MS);
      if (activeRequestId !== requestId) return;
      const pollParams = new URLSearchParams({
        catalog_job_id: String(ing.job_id),
        artist: seed.artist,
        track: seed.track,
      });
      const polled = await fetchJson(`/api/musicatlas/suggestions?${pollParams.toString()}`);
      if (activeRequestId !== requestId) return;
      ing = polled.catalog_ingestion;
      radioCatalogProgress.value = ing ? normalizeCatalogIngestion(ing) : null;
    }
    radioCatalogProgress.value = null;
    body = await fetchRadioSuggestionsBody(seed, activeRequestId);
    if (!body) return;
    radioNotice.value = radioNoticeFromBody(body);
    if (ing?.terminal) {
      radioCatalogMessage.value =
        trimRadioMessage(ing.message) ||
        trimRadioMessage(ing.status) ||
        radioNoticeFromBody(body);
    } else {
      radioCatalogMessage.value = radioNoticeFromBody(body) || "Catalog ingestion timed out.";
    }
  } else if (ing?.job_id && ing.terminal && initialItems.length === 0) {
    // Catalog job already finished on first response; initial similar_tracks can still be empty — refetch once.
    body = await fetchRadioSuggestionsBody(seed, activeRequestId);
    if (!body) return;
    radioNotice.value = radioNoticeFromBody(body);
    radioCatalogMessage.value =
      trimRadioMessage(ing.message) ||
      trimRadioMessage(ing.status) ||
      radioNoticeFromBody(body);
  }

  const items = Array.isArray(body.items) ? body.items : [];
  entries.value = mergeRadioEntries(seed, items);
  radioCatalogProgress.value = null;
  if (entries.value.length > 0) {
    radioCatalogMessage.value = null;
  }
}

async function playRadioAll() {
  const list = playableRadioEntries.value;
  if (!list.length) {
    notifyError("Nothing to play", new Error("No playable URLs in this radio list."));
    return;
  }
  const queueCleared = await clearQueue({ notify: false });
  if (!queueCleared) {
    notifyError("Could not start playback", new Error("Could not clear the queue."));
    return;
  }
  const started = await playUrl(list[0].source_url, { notify: false });
  if (!started) {
    notifyError("Could not start playback", new Error("Could not start playback."));
    return;
  }
  for (let i = 1; i < list.length; i += 1) {
    const queued = await addUrl(list[i].source_url, { notify: false });
    if (!queued) {
      notifyError("Could not start playback", new Error("Could not queue the rest of the radio list."));
      return;
    }
  }
  notifySuccess("Playing now", "Radio list is now playing.");
}

async function queueRadioAll() {
  const list = playableRadioEntries.value;
  if (!list.length) {
    notifyError("Nothing to queue", new Error("No playable URLs in this radio list."));
    return;
  }
  for (const row of list) {
    const queued = await addUrl(row.source_url, { notify: false });
    if (!queued) {
      notifyError("Could not add to queue", new Error("Could not queue the full radio list."));
      return;
    }
  }
  notifySuccess("Added to queue", `${list.length} tracks queued.`);
}

async function saveRadioToLibrary() {
  const seed = radioSeed.value;
  if (!seed?.track || !entries.value.length) return;
  radioSaving.value = true;
  try {
    const title = `${seed.track} Radio`;
    const created = await createPlaylist(title);
    if (!created?.id) return;
    await addEntriesToPlaylist(created.id, entries.value, {
      onComplete: () => {
        router.push(`/playlist/${created.id}`);
      },
    });
  } catch (error) {
    notifyError("Could not save playlist", error);
  } finally {
    radioSaving.value = false;
  }
}

async function loadPlaylist() {
  const playlistId = playlistIdFromRoute().trim();
  const activeRequestId = ++requestId;

  songSearchTerm.value = "";

  if (!playlistId.startsWith("remote:radio:")) {
    radioSeed.value = null;
    radioNotice.value = null;
    radioCatalogMessage.value = null;
    radioCatalogProgress.value = null;
    radioSuggestionsLoading.value = false;
  }

  if (!playlistId) {
    playlist.value = {};
    entries.value = [];
    loading.value = false;
    notFound.value = true;
    errorMessage.value = "";
    return;
  }

  notFound.value = false;
  errorMessage.value = "";

  if (playlistId.startsWith("remote:radio:")) {
    loading.value = false;
    const seed = decodeRadioPlaylistSeed(playlistId);
    if (!seed) {
      if (activeRequestId !== requestId) return;
      playlist.value = {};
      entries.value = [];
      radioSeed.value = null;
      notFound.value = true;
      return;
    }
    radioSeed.value = seed;
    playlist.value = {
      id: playlistId,
      title: `${seed.track} Radio`,
      kind: "remote_radio",
    };
    entries.value = [];
    radioSuggestionsLoading.value = true;
    try {
      await loadRadioPlaylist(playlistId, seed, activeRequestId);
    } catch (error) {
      if (activeRequestId !== requestId) return;
      const message = error instanceof Error ? error.message : String(error || "Request failed");
      errorMessage.value = message;
      entries.value = [];
    } finally {
      if (activeRequestId === requestId) {
        radioSuggestionsLoading.value = false;
        radioCatalogProgress.value = null;
      }
    }
    return;
  }

  loading.value = true;

  if (playlistId.startsWith("remote:youtube:")) {
    const match = (playlists.value || []).find((item) => item?.id === playlistId);
    if (activeRequestId !== requestId) return;
    if (!match) {
      playlist.value = {};
      entries.value = [];
      loading.value = false;
      notFound.value = true;
      return;
    }
    playlist.value = match;
    entries.value = [];
    loading.value = false;
    return;
  }

  try {
    const playlistPayload = await fetchJson(`/api/playlists/${encodeURIComponent(playlistId)}`);
    if (activeRequestId !== requestId) return;
    playlist.value = playlistPayload || {};
  } catch (error) {
    if (activeRequestId !== requestId) return;
    const message = error instanceof Error ? error.message : String(error || "Request failed");
    notFound.value = message.toLowerCase().includes("404");
    errorMessage.value = notFound.value ? "" : message;
    playlist.value = {};
    entries.value = [];
    loading.value = false;
    return;
  }

  try {
    const entriesPayload = await fetchJson(`/api/playlists/${encodeURIComponent(playlistId)}/entries`);
    if (activeRequestId !== requestId) return;
    entries.value = Array.isArray(entriesPayload) ? entriesPayload : [];
  } catch (error) {
    if (activeRequestId !== requestId) return;
    entries.value = [];
    errorMessage.value = error instanceof Error ? error.message : "Could not load playlist entries";
  } finally {
    if (activeRequestId === requestId) {
      loading.value = false;
    }
  }
}

function onReorderEnd(evt) {
  const { oldIndex, newIndex } = evt;
  if (oldIndex === newIndex) return;
  const entry = entries.value[newIndex];
  if (!entry?.id) return;
  reorderPlaylistEntry(entry.id, newIndex);
}

watch(
  () => route.params.id,
  () => {
    loadPlaylist();
  },
  { immediate: true },
);
</script>
