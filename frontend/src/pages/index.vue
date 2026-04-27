<template>
  <section class="home-page min-h-0 h-full min-w-0 overflow-auto rounded-xl border border-neutral-700 p-4 md:p-6 surface-panel">
    <!-- Hero -->
    <div class="home-hero mb-6 md:mb-8">
      <h1 class="text-3xl font-bold tracking-tight md:text-4xl">Airwave</h1>
      <p class="mt-2 max-w-xl text-sm text-muted md:text-base">
        Shared live audio from YouTube, SoundCloud, and Mixcloud. Add tracks and playlists to the queue, stream to browsers and Sonos.
      </p>

      <!-- Now playing summary -->
      <div
        v-if="nowPlayingTitle"
        class="home-now-playing mt-4 flex items-center gap-3 rounded-lg border p-3 surface-elevated"
      >
        <img
          v-if="nowPlayingThumbnail"
          :src="nowPlayingThumbnail"
          alt=""
          class="h-12 w-12 shrink-0 rounded object-cover"
        />
        <div class="min-w-0 flex-1">
          <p class="truncate text-sm font-medium">Now playing</p>
          <p class="truncate text-xs text-muted">{{ nowPlayingTitle }}{{ nowPlayingChannel ? ` · ${nowPlayingChannel}` : "" }}</p>
        </div>
        <UButton
          v-if="!isMobile"
          type="button"
          color="primary"
          variant="soft"
          size="sm"
          icon="i-bi-search"
          @click="goToSearch"
        >
          Search
        </UButton>
      </div>

      <!-- Quick CTAs when nothing playing -->
      <div v-else class="mt-4 flex flex-wrap gap-2">
        <UButton type="button" color="primary" variant="solid" size="md" icon="i-bi-search" @click="goToSearch">
          Search providers
        </UButton>
        <UButton type="button" color="neutral" variant="outline" size="md" icon="i-bi-music-note-list" @click="goToPlaylists">
          Browse playlists
        </UButton>
      </div>
    </div>

    <!-- Summary chips -->
    <div class="home-stats mb-6 flex flex-wrap gap-2">
      <span class="home-stat-chip rounded-full border px-3 py-1 text-xs font-medium surface-elevated">
        {{ queueCount }} in queue
      </span>
      <span class="home-stat-chip rounded-full border px-3 py-1 text-xs font-medium surface-elevated">
        {{ historyCount }} in history
      </span>
      <span class="home-stat-chip rounded-full border px-3 py-1 text-xs font-medium surface-elevated">
        {{ playlistCount }} playlists
      </span>
      <span
        v-if="playbackStatusLabel"
        class="home-stat-chip rounded-full border px-3 py-1 text-xs font-medium surface-elevated"
      >
        {{ playbackStatusLabel }}
      </span>
    </div>

    <!-- Grid: playlists | queue/history | sonos -->
    <div class="home-grid min-w-0 grid gap-4 md:grid-cols-2 lg:grid-cols-3">
      <!-- Featured playlists -->
      <div class="home-section min-w-0 rounded-xl border p-4 surface-elevated">
        <div class="mb-3 flex items-center justify-between">
          <h2 class="text-lg font-semibold">Playlists</h2>
          <UButton
            type="button"
            color="neutral"
            variant="ghost"
            size="xs"
            icon="i-bi-chevron-right"
            @click="goToPlaylists"
          >
            View all
          </UButton>
        </div>
        <ul v-if="featuredPlaylists.length" class="space-y-2">
          <PlaylistItem
            v-for="playlist in featuredPlaylists"
            :key="playlist.id"
            :playlist="playlist"
            :active-playlist-id="activePlaylistId"
            :is-remote-playlist="isRemotePlaylist"
            :thumbnail-src="playlist.thumbnail_url"
            :label="playlistLabel(playlist)"
            @click="openPlaylist(playlist)"
            @clear-active-playlist="clearActivePlaylist"
          />
        </ul>
        <div v-else class="py-6 text-center text-sm text-muted">
          No playlists yet. Import from a provider URL or create one in the sidebar.
        </div>
      </div>

      <!-- Queue preview -->
      <div class="home-section min-w-0 rounded-xl border p-4 surface-elevated">
        <div class="mb-3 flex items-center justify-between">
          <h2 class="text-lg font-semibold">Up next</h2>
          <UButton
            type="button"
            color="neutral"
            variant="ghost"
            size="xs"
            icon="i-bi-chevron-right"
            @click="goToQueue"
          >
            View queue
          </UButton>
        </div>
        <ul v-if="queuePreview.length" class="space-y-2">
          <li v-for="item in queuePreview" :key="item.id">
            <Song :item="item" mode="queue" :playlists="playlists" />
          </li>
        </ul>
        <div v-else class="py-6 text-center text-sm text-muted">
          Queue is empty. Add a URL from the top bar.
        </div>
      </div>

      <!-- History preview -->
      <div class="home-section min-w-0 rounded-xl border p-4 surface-elevated">
        <div class="mb-3 flex items-center justify-between">
          <h2 class="text-lg font-semibold">Recently played</h2>
          <UButton
            type="button"
            color="neutral"
            variant="ghost"
            size="xs"
            icon="i-bi-chevron-right"
            @click="goToHistory"
          >
            View history
          </UButton>
        </div>
        <ul v-if="historyPreview.length" class="space-y-2">
          <li v-for="item in historyPreview" :key="item.id">
            <Song :item="item" mode="history" :playlists="playlists" />
          </li>
        </ul>
        <div v-else class="py-6 text-center text-sm text-muted">
          No playback history yet.
        </div>
      </div>

      <!-- Sonos card -->
      <div v-if="speakers.length > 0" class="home-section home-sonos-card min-w-0 rounded-xl border p-4 surface-elevated lg:col-span-2">
        <div class="flex items-center justify-between">
          <div>
            <h2 class="text-lg font-semibold">Sonos</h2>
            <p class="text-sm text-muted">{{ speakers.length }} speaker{{ speakers.length === 1 ? "" : "s" }} available</p>
          </div>
          <div class="flex gap-2">
            <UButton
              v-if="firstCoordinator"
              type="button"
              color="primary"
              variant="solid"
              size="sm"
              @click="playOnSpeaker(firstCoordinator.ip)"
            >
              Play on {{ firstCoordinator.name }}
            </UButton>
            <UButton type="button" color="neutral" variant="outline" size="sm" @click="openSonos">
              Open Sonos
            </UButton>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup>
import { computed } from "vue";
import { useRouter } from "vue-router";

import PlaylistItem from "../components/PlaylistItem.vue";
import Song from "../components/Song.vue";
import { useBreakpoint } from "../composables/useBreakpoint";
import { useLibraryState } from "../composables/useLibraryState";
import { usePlaybackState } from "../composables/usePlaybackState";
import { useSonosState } from "../composables/useSonosState";
import {
  HISTORY_TAB,
  MOBILE_VIEW_PLAYLISTS,
  MOBILE_VIEW_QUEUE,
  MOBILE_VIEW_SPEAKERS,
  SIDEBAR_QUEUE_VIEW,
  SIDEBAR_SPEAKERS_VIEW,
  useUiState,
} from "../composables/useUiState";

const router = useRouter();
const { isMobile } = useBreakpoint();
const { queue, history, playlists, importPlaylistUrl } = useLibraryState();
const { playbackState } = usePlaybackState();
const { speakers, playOnSpeaker } = useSonosState();
const {
  activePlaylistId,
  activeQueueTab,
  selectPlaylist,
  sidebarView,
  mobileView,
} = useUiState();

const queueCount = computed(() => (Array.isArray(queue.value) ? queue.value.length : 0));
const historyCount = computed(() => (Array.isArray(history.value) ? history.value.length : 0));
const playlistCount = computed(() => (Array.isArray(playlists.value) ? playlists.value.length : 0));

const nowPlayingTitle = computed(() => playbackState.value?.now_playing_title ?? null);
const nowPlayingChannel = computed(() => playbackState.value?.now_playing_channel ?? null);
const nowPlayingThumbnail = computed(() => playbackState.value?.now_playing_thumbnail_url ?? null);

const playbackStatusLabel = computed(() => {
  const state = playbackState.value;
  if (!state) return "";
  if (state.mode === "idle") return "Idle";
  if (state.paused) return "Paused";
  return "Playing";
});

const featuredPlaylists = computed(() => {
  const list = Array.isArray(playlists.value) ? playlists.value : [];
  const pinned = list.filter((p) => !!p.pinned);
  const unpinned = list.filter((p) => !p.pinned);
  return [...pinned, ...unpinned].slice(0, 6);
});

const queuePreview = computed(() => {
  const q = Array.isArray(queue.value) ? queue.value : [];
  return q.slice(0, 5);
});

const historyPreview = computed(() => {
  const h = Array.isArray(history.value) ? history.value : [];
  return h.slice(0, 5);
});

const firstCoordinator = computed(() => {
  const list = speakers.value;
  return list.find((s) => s.is_coordinator) ?? list[0] ?? null;
});

function goToSearch() {
  router.push({ path: "/search" });
}

function goToPlaylists() {
  if (isMobile.value) {
    mobileView.value = MOBILE_VIEW_PLAYLISTS;
  } else {
    router.push({ path: "/playlists" }).catch(() => {});
  }
}

function goToQueue() {
  if (isMobile.value) {
    mobileView.value = MOBILE_VIEW_QUEUE;
  } else {
    sidebarView.value = SIDEBAR_QUEUE_VIEW;
  }
}

function goToHistory() {
  if (isMobile.value) {
    mobileView.value = MOBILE_VIEW_QUEUE;
    activeQueueTab.value = HISTORY_TAB;
  } else {
    sidebarView.value = SIDEBAR_QUEUE_VIEW;
    activeQueueTab.value = HISTORY_TAB;
  }
}

function isRemotePlaylist(playlist) {
  return playlist?.kind === "remote_youtube";
}

function playlistLabel(playlist) {
  if (playlist?.kind === "remote_youtube") return "youtube";
  return playlist?.kind || "playlist";
}

function openPlaylist(playlist) {
  if (isRemotePlaylist(playlist)) {
    importPlaylistUrl(playlist.source_url);
    return;
  }
  selectPlaylist(router, playlist?.id);
}

function clearActivePlaylist() {
  selectPlaylist(router, null);
}

function openSonos() {
  if (isMobile.value) {
    mobileView.value = MOBILE_VIEW_SPEAKERS;
  } else {
    sidebarView.value = SIDEBAR_SPEAKERS_VIEW;
  }
}
</script>
