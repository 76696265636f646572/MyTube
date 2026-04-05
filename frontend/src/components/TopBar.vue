<template>
  <header class="rounded-xl border border-neutral-700 p-3 surface-panel">
    <!-- Desktop / tablet: single row, Home + search bar centered, Settings on right -->
    <template v-if="!isMobile">
    <div class="flex items-center w-full gap-3">
      <div class="flex flex-1 items-center min-w-0">
        <h1 class="text-2xl font-bold leading-tight">Airwave</h1>
      </div>
      <form
        class="flex flex-col gap-2 sm:flex-row sm:flex-nowrap sm:items-center sm:justify-center shrink-0"
        @submit.prevent="onUnifiedSubmit(false)"
      >
        <UButton
          type="button"
          color="neutral"
          variant="ghost"
          icon="i-bi-house-fill"
          class="self-start sm:self-auto"
          @click="router.push('/')"
        />
        <input
          v-model="unifiedInput"
          type="text"
          placeholder="Search or paste URL (YouTube, SoundCloud, Mixcloud, Spotify playlist, or direct MP3/audio link)…"
          class="h-10 w-full min-w-0 flex-1 rounded-md border px-3 text-sm sm:min-w-[400px] sm:max-w-[800px] surface-input"
        />
        <template v-if="isUrlInput">
          <div class="flex w-full sm:w-auto">
            <UButton
              type="submit"
              color="primary"
              variant="solid"
              size="md"
              class="flex-1 h-10 sm:flex-none"
              :class="showUrlActionDropdown ? 'rounded-r-none' : ''"
            >
              {{ primaryActionLabel }}
            </UButton>
            <UDropdownMenu
              v-if="showUrlActionDropdown"
              :items="actionDropdownItems"
              :ui="{ separator: 'hidden' }"
              @update:open="(open) => !open && resetSearch()"
            >
              <template #playlist-filter>
                <PlaylistSelectorFilter
                  v-model="playlistSearchTerm"
                  placeholder="Find a playlist"
                  @playlist-created="onImportUrlPlaylistCreated"
                />
              </template>
              <UButton type="button" color="primary" variant="solid" size="md" class="rounded-l-none border-l-0">
                <UIcon name="i-bi-chevron-down" class="size-4" />
              </UButton>
            </UDropdownMenu>
          </div>
        </template>
        <UButton
          v-else
          type="submit"
          color="primary"
          variant="solid"
          size="md"
          class="self-start sm:self-auto h-10"
          @click="onUnifiedSubmit(false)"
        >
          Search
        </UButton>
      </form>
      <div class="flex flex-1 justify-end min-w-0 items-center gap-1">
        <UButton
          type="button"
          color="neutral"
          variant="ghost"
          icon="i-bi-folder-fill"
          class="flex-shrink-0"
          aria-label="Media Browser"
          @click="router.push('/explorer')"
        />
        <UButton
          type="button"
          color="neutral"
          variant="ghost"
          icon="i-bi-gear-fill"
          class="flex-shrink-0"
          @click="router.push('/settings')"
        />
      </div>
    </div>
    </template>

    <!-- Mobile: compact row -->
    <template v-else>
    <div class="flex items-center justify-between gap-2">
      <h1 class="text-xl font-bold leading-tight">Airwave</h1>
      <div class="flex items-center gap-1">
        <UButton
          type="button"
          color="neutral"
          variant="ghost"
          icon="i-bi-folder-fill"
          class="h-10"
          aria-label="Media Browser"
          @click="router.push('/explorer')"
        />
        <UButton
          type="button"
          color="neutral"
          variant="ghost"
          icon="i-bi-plus-circle-fill"
          class="h-10"
          aria-label="Add URL"
          @click="addUrlSheetOpen = true"
        />
      </div>
    </div>

    <!-- Mobile: Search or Add URL sheet (merged input with contextual buttons) -->
    <UModal v-model:open="addUrlSheetOpen" :ui="{ width: 'w-full max-w-sm', content: 'rounded-t-2xl surface-panel' }">
      <template #content>
        <div class="p-4">
          <h2 class="text-lg font-semibold">Search or Add URL</h2>
          <form class="mt-3 flex flex-col gap-3" @submit.prevent="onUnifiedSubmit(true)">
            <input
              v-model="unifiedInput"
              type="text"
              placeholder="Search or paste URL (YouTube, SoundCloud, Mixcloud, Spotify playlist, or direct MP3/audio link)…"
              class="h-11 w-full rounded-md border px-3 text-sm surface-input"
            />
            <div class="flex w-full">
              <template v-if="isUrlInput">
                <UButton type="submit" color="primary" variant="solid" class="flex-1" :class="showUrlActionDropdown ? 'rounded-r-none' : ''">
                  {{ primaryActionLabel }}
                </UButton>
                <UDropdownMenu
                  v-if="showUrlActionDropdown"
                  :items="actionDropdownItems"
                  :ui="{ separator: 'hidden' }"
                  @update:open="(open) => !open && resetSearch()"
                >
                  <template #playlist-filter>
                    <PlaylistSelectorFilter
                      v-model="playlistSearchTerm"
                      placeholder="Find a playlist"
                      @playlist-created="onImportUrlPlaylistCreated"
                    />
                  </template>
                  <UButton type="button" color="primary" variant="solid" class="rounded-l-none border-l-0">
                    <span aria-hidden="true">|</span>
                    <UIcon name="i-bi-chevron-down" class="size-4" />
                  </UButton>
                </UDropdownMenu>
              </template>
              <UButton
                v-else
                type="submit"
                color="primary"
                variant="solid"
                class="flex-1"
              >
                Search
              </UButton>
            </div>
          </form>
        </div>
      </template>
    </UModal>
    </template>

  </header>
</template>

<script setup>
import { computed, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import PlaylistSelectorFilter from "./PlaylistSelectorFilter.vue";
import { useBreakpoint } from "../composables/useBreakpoint";
import { useLibraryState } from "../composables/useLibraryState";
import { usePlaylistSelector } from "../composables/usePlaylistSelector";
import { useUiState } from "../composables/useUiState";

const { isMobile } = useBreakpoint();
const unifiedInput = ref("");
const addUrlSheetOpen = ref(false);
const router = useRouter();
const route = useRoute();
const { queue, playlists, addUrl, playUrl, importPlaylistUrl, startSpotifyImportFromUrl, importPlaylistIntoPlaylist, addUrlToPlaylist } = useLibraryState();
const { playlistSearchTerm, filteredPlaylists, resetSearch } = usePlaylistSelector(playlists);
const { searchText, onSearchTextChange, onSearchSubmit } = useUiState();

const ACTION_IDS = {
  PLAY_URL: "play-url",
  PLAY_PLAYLIST: "play-playlist",
  QUEUE_PLAYLIST: "queue-playlist",
  IMPORT_PLAYLIST: "import-playlist",
  ADD_URL: "add-url",
};

function parseInputUrl(rawUrl) {
  const url = rawUrl.trim();
  if (!url) return null;
  try {
    return new URL(url);
  } catch {
    return null;
  }
}

function hasPlaylistId(rawUrl) {
  const parsed = parseInputUrl(rawUrl);
  if (parsed) {
    return !!parsed.searchParams.get("list");
  }
  return rawUrl.includes("list=");
}

function isStartRadioUrl(rawUrl) {
  const parsed = parseInputUrl(rawUrl);
  if (!parsed) return false;
  return parsed.searchParams.get("start_radio") === "1";
}

function getVideoOnlyUrl(rawUrl) {
  const parsed = parseInputUrl(rawUrl);
  if (!parsed) return rawUrl;
  const videoId = parsed.searchParams.get("v");
  if (!videoId) return rawUrl;
  const host = parsed.hostname.toLowerCase();
  const knownYoutubeHost = host === "youtube.com"
    || host === "www.youtube.com"
    || host === "m.youtube.com"
    || host === "music.youtube.com"
    || host === "youtu.be"
    || host === "www.youtu.be";
  if (!knownYoutubeHost) return rawUrl;
  return `https://www.youtube.com/watch?v=${encodeURIComponent(videoId)}`;
}

function isCanonicalPlaylistPath(rawUrl) {
  const parsed = parseInputUrl(rawUrl);
  if (!parsed) return false;
  return parsed.pathname.includes("/playlist") && !!parsed.searchParams.get("list");
}

function isSoundCloudSetUrl(rawUrl) {
  const parsed = parseInputUrl(rawUrl);
  if (!parsed) return false;
  const host = parsed.hostname.toLowerCase();
  const isSoundCloud = host === "soundcloud.com" || host === "www.soundcloud.com" || host === "m.soundcloud.com";
  return isSoundCloud && parsed.pathname.toLowerCase().includes("/sets/");
}

function isSpotifyPlaylistUrl(rawUrl) {
  const parsed = parseInputUrl(rawUrl);
  if (!parsed) return false;
  const host = parsed.hostname.toLowerCase();
  if (host !== "open.spotify.com" && host !== "www.spotify.com") return false;
  return /^\/playlist\//i.test(parsed.pathname);
}

function getCanonicalPlaylistUrl(rawUrl) {
  const parsed = parseInputUrl(rawUrl);
  if (!parsed) return rawUrl;

  const playlistId = parsed.searchParams.get("list");
  if (!playlistId) return rawUrl;

  const host = parsed.hostname.toLowerCase();
  const knownYoutubeHost = host === "youtube.com"
    || host === "www.youtube.com"
    || host === "m.youtube.com"
    || host === "music.youtube.com"
    || host === "youtu.be"
    || host === "www.youtu.be";
  if (!knownYoutubeHost) return rawUrl;

  return `https://www.youtube.com/playlist?list=${encodeURIComponent(playlistId)}`;
}

const isUrlInput = computed(
  () => unifiedInput.value.trim().toLowerCase().startsWith("http"),
);

const actionContext = computed(() => {
  const rawUrl = unifiedInput.value.trim();
  if (!rawUrl) return "single";
  if (isSpotifyPlaylistUrl(rawUrl)) return "spotify-playlist";
  if (isSoundCloudSetUrl(rawUrl)) return "playlist-capable";
  if (isCanonicalPlaylistPath(rawUrl)) return "canonical-playlist";
  if (hasPlaylistId(rawUrl) && isStartRadioUrl(rawUrl)) return "start-radio";
  if (hasPlaylistId(rawUrl)) return "playlist-capable";
  return "single";
});

const defaultActionId = computed(() => {
  if (actionContext.value === "spotify-playlist") {
    return ACTION_IDS.IMPORT_PLAYLIST;
  }
  const hasQueueItems = Array.isArray(queue.value) && queue.value.length > 0;
  if (hasQueueItems) {
    if (actionContext.value === "canonical-playlist") {
      return ACTION_IDS.QUEUE_PLAYLIST;
    }
    return ACTION_IDS.ADD_URL;
  }
  if (actionContext.value === "canonical-playlist") return ACTION_IDS.PLAY_PLAYLIST;
  return ACTION_IDS.PLAY_URL;
});

const availableActions = computed(() => {
  if (actionContext.value === "spotify-playlist") {
    return [];
  }
  let base = [
    { id: ACTION_IDS.PLAY_URL, label: "Play", icon: "i-bi-play-fill" },
    { id: ACTION_IDS.ADD_URL, label: "Queue", icon: "i-bi-music-note-list" },
  ];
  if (actionContext.value === "start-radio") {
    base = [
      { id: ACTION_IDS.ADD_URL, label: "Queue", icon: "i-bi-music-note-list" },
      { id: ACTION_IDS.PLAY_URL, label: "Play", icon: "i-bi-play-fill" },
      { id: ACTION_IDS.PLAY_PLAYLIST, label: "Play Playlist", icon: "i-bi-play-fill" },
      { id: ACTION_IDS.QUEUE_PLAYLIST, label: "Queue Playlist", icon: "i-bi-music-note-list" },
      { id: ACTION_IDS.IMPORT_PLAYLIST, label: "Import playlist", icon: "i-bi-download" },
    ];
  } else if (actionContext.value === "playlist-capable" || actionContext.value === "canonical-playlist") {
    base = [
      { id: ACTION_IDS.PLAY_URL, label: "Play", icon: "i-bi-play-fill" },
      { id: ACTION_IDS.PLAY_PLAYLIST, label: "Play Playlist", icon: "i-bi-play-fill" },
      { id: ACTION_IDS.QUEUE_PLAYLIST, label: "Queue Playlist", icon: "i-bi-music-note-list" },
      { id: ACTION_IDS.IMPORT_PLAYLIST, label: "Import playlist", icon: "i-bi-download" },
      { id: ACTION_IDS.ADD_URL, label: "Queue", icon: "i-bi-music-note-list" },
    ];
  }
  // filter default action from base
  base = base.filter((action) => action.id !== defaultActionId.value);
  return base;
});

const primaryActionLabel = computed(() => {
  if (actionContext.value === "spotify-playlist") return "Import playlist";
  if (defaultActionId.value === ACTION_IDS.QUEUE_PLAYLIST) return "Queue Playlist";
  if (defaultActionId.value === ACTION_IDS.ADD_URL) return "Queue";
  if (defaultActionId.value === ACTION_IDS.PLAY_PLAYLIST) return "Play Playlist";
  return "Play";
});

const showUrlActionDropdown = computed(
  () => isUrlInput.value && actionContext.value !== "spotify-playlist",
);

const isPlaylistOrRadioContext = computed(
  () =>
    actionContext.value === "start-radio"
    || actionContext.value === "playlist-capable"
    || actionContext.value === "canonical-playlist",
);

const actionDropdownItems = computed(() => {
  const items = availableActions.value.map((action) => ({
    label: action.label,
    icon: action.icon,
    onSelect: () => {
      const url = unifiedInput.value.trim();
      if (url) runAction(action.id, addUrlSheetOpen.value, url);
    },
  }));

  if (isPlaylistOrRadioContext.value && Array.isArray(playlists.value)) {
    const rawUrl = unifiedInput.value.trim();
    const urlForPlaylist = isStartRadioUrl(rawUrl) ? rawUrl : getCanonicalPlaylistUrl(rawUrl);
    const playlistChildren = [
      { type: "label", slot: "playlist-filter" },
      ...filteredPlaylists.value.map((p) => ({
        label: p.title,
        onSelect: () => {
          importPlaylistIntoPlaylist(urlForPlaylist, p.id);
          unifiedInput.value = "";
          addUrlSheetOpen.value = false;
        },
      })),
    ];
    items.push(
      {
        label: "Import into playlist",
        icon: "i-bi-download",
        children: [playlistChildren],
      },
    );
  }

  return items;
});

function runAction(actionId, closeAfter = false, urlOverride = null) {
  const rawUrl = urlOverride ?? unifiedInput.value.trim();
  if (!rawUrl) return;
  unifiedInput.value = "";

  const isStartRadio = isStartRadioUrl(rawUrl);
  const urlForSingle = isStartRadio ? getVideoOnlyUrl(rawUrl) : rawUrl;
  const urlForPlaylist = isStartRadio ? rawUrl : getCanonicalPlaylistUrl(rawUrl);

  if (actionId === ACTION_IDS.PLAY_PLAYLIST) {
    playUrl(urlForPlaylist);
  } else if (actionId === ACTION_IDS.QUEUE_PLAYLIST) {
    addUrl(urlForPlaylist);
  } else if (actionId === ACTION_IDS.IMPORT_PLAYLIST) {
    if (isSpotifyPlaylistUrl(rawUrl)) {
      startSpotifyImportFromUrl(rawUrl.trim(), router);
    } else {
      importPlaylistUrl(urlForPlaylist);
    }
  } else if (actionId === ACTION_IDS.ADD_URL) {
    addUrl(urlForSingle);
  } else {
    playUrl(urlForSingle);
  }

  if (closeAfter) {
    addUrlSheetOpen.value = false;
  }
}

function runPrimaryAction(closeAfter = false) {
  runAction(defaultActionId.value, closeAfter, unifiedInput.value.trim());
}

function onImportUrlPlaylistCreated(created) {
  if (created?.id == null) return;
  const rawUrl = unifiedInput.value.trim();
  if (!rawUrl) return;
  const urlForPlaylist = isStartRadioUrl(rawUrl) ? rawUrl : getCanonicalPlaylistUrl(rawUrl);
  importPlaylistIntoPlaylist(urlForPlaylist, created.id);
  unifiedInput.value = "";
  addUrlSheetOpen.value = false;
}

function onUnifiedSubmit(closeAfter = false) {
  const raw = unifiedInput.value.trim();
  if (!raw) return;
  if (isUrlInput.value) {
    runPrimaryAction(closeAfter);
  } else {
    onSearchSubmit(router, route, raw);
    if (closeAfter) addUrlSheetOpen.value = false;
  }
}

watch(
  unifiedInput,
  (val) => {
    if (!val.trim().toLowerCase().startsWith("http")) {
      onSearchTextChange(val);
    }
  },
  { immediate: false },
);
</script>
