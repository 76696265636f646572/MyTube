<template>
  <header class="rounded-xl border border-neutral-700 p-3 surface-panel">
    <!-- Desktop / tablet: full layout (single branch to avoid duplicate content in DOM) -->
    <template v-if="!isMobile">
    <div class="flex flex-col gap-2 sm:flex-row sm:items-center">
      <h1 class="text-2xl font-bold leading-tight">AirWave</h1>
      <div class="flex w-full flex-col gap-2 sm:ml-auto sm:w-auto sm:flex-row sm:flex-wrap sm:justify-end">
        <UButton
          type="button"
          color="neutral"
          variant="ghost"
          icon="i-lucide-house"
          class="self-start sm:self-auto"
          @click="router.push('/')"
        />
        <UButton
          type="button"
          color="neutral"
          variant="ghost"
          icon="i-lucide-settings"
          class="self-start sm:self-auto"
          @click="router.push('/settings')"
        />
        <input
          :value="searchText"
          type="search"
          placeholder="Search local + YouTube"
          class="h-10 w-full min-w-0 rounded-md border px-3 text-sm sm:w-[320px] surface-input"
          @input="onSearchTextChange($event.target.value)"
          @keydown.enter.prevent="onYoutubeSearch(router, route, searchText)"
        />
        <UButton
          type="button"
          color="primary"
          variant="solid"
          size="md"
          class="self-start sm:self-auto"
          @click="onYoutubeSearch(router, route, searchText)"
        >
          Search
        </UButton>
      </div>
    </div>
    <form class="mt-3 flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center" @submit.prevent="runPrimaryAction">
      <input
        v-model="urlInput"
        type="url"
        placeholder="https://www.youtube.com/watch?v=... or https://www.youtube.com/playlist?list=..."
        required
        class="h-10 w-full min-w-0 flex-1 rounded-md border px-3 text-sm surface-input"
      />
      <div class="flex w-full sm:w-auto">
        <UButton type="submit" color="primary" variant="solid" size="md" class="flex-1 rounded-r-none sm:flex-none">
          {{ primaryActionLabel }}
        </UButton>
        <UDropdownMenu :items="actionDropdownItems">
          <UButton type="button" color="primary" variant="solid" size="md" class="rounded-l-none border-l-0">
            <UIcon name="i-lucide-chevron-down" class="size-4" />
          </UButton>
        </UDropdownMenu>
      </div>
    </form>
    </template>

    <!-- Mobile: compact row -->
    <template v-else>
    <div class="flex items-center justify-between gap-2">
      <h1 class="text-xl font-bold leading-tight">AirWave</h1>
      <div class="flex items-center gap-1">
        <UButton
          type="button"
          color="neutral"
          variant="ghost"
          icon="i-lucide-plus-circle"
          class="h-10"
          aria-label="Add URL"
          @click="addUrlSheetOpen = true"
        />
      </div>
    </div>

    <!-- Mobile: Add URL sheet (modal only on mobile) -->
    <UModal v-model:open="addUrlSheetOpen" :ui="{ width: 'w-full max-w-sm', content: 'rounded-t-2xl surface-panel' }">
      <template #content>
        <div class="p-4">
          <h2 class="text-lg font-semibold">Add URL</h2>
          <form class="mt-3 flex flex-col gap-3" @submit.prevent="runPrimaryActionThenClose">
            <input
              v-model="urlInput"
              type="url"
              placeholder="https://www.youtube.com/watch?v=..."
              required
              class="h-11 w-full rounded-md border px-3 text-sm surface-input"
            />
            <div class="flex w-full">
              <UButton type="submit" color="primary" variant="solid" class="flex-1 rounded-r-none">
                {{ primaryActionLabel }}
              </UButton>
              <UDropdownMenu :items="actionDropdownItems">
                <UButton type="button" color="primary" variant="solid" class="rounded-l-none border-l-0">
                  <span aria-hidden="true">|</span>
                  <UIcon name="i-lucide-chevron-down" class="size-4" />
                </UButton>
              </UDropdownMenu>
            </div>
          </form>
        </div>
      </template>
    </UModal>
    </template>
  </header>
</template>

<script setup>
import { computed, ref } from "vue";
import { useRoute, useRouter } from "vue-router";

import { useBreakpoint } from "../composables/useBreakpoint";
import { useLibraryState } from "../composables/useLibraryState";
import { useUiState } from "../composables/useUiState";

const { isMobile } = useBreakpoint();
const urlInput = ref("");
const addUrlSheetOpen = ref(false);
const router = useRouter();
const route = useRoute();
const { queue, addUrl, playUrl, importPlaylistUrl } = useLibraryState();
const { searchText, onSearchTextChange, onYoutubeSearch } = useUiState();

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

const actionContext = computed(() => {
  const rawUrl = urlInput.value.trim();
  if (!rawUrl) return "single";
  if (isCanonicalPlaylistPath(rawUrl)) return "canonical-playlist";
  if (hasPlaylistId(rawUrl) && isStartRadioUrl(rawUrl)) return "start-radio";
  if (hasPlaylistId(rawUrl)) return "playlist-capable";
  return "single";
});

const defaultActionId = computed(() => {
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
  let base = [
    { id: ACTION_IDS.PLAY_URL, label: "Play" },
    { id: ACTION_IDS.ADD_URL, label: "Queue" },
  ];
  if (actionContext.value === "start-radio") {
    base = [
      { id: ACTION_IDS.ADD_URL, label: "Queue" },
      { id: ACTION_IDS.PLAY_URL, label: "Play" },
      { id: ACTION_IDS.PLAY_PLAYLIST, label: "Play Playlist" },
      { id: ACTION_IDS.QUEUE_PLAYLIST, label: "Queue Playlist" },
      { id: ACTION_IDS.IMPORT_PLAYLIST, label: "Import playlist" },
    ];
  } else if (actionContext.value === "playlist-capable" || actionContext.value === "canonical-playlist") {
    base = [
      { id: ACTION_IDS.PLAY_URL, label: "Play" },
      { id: ACTION_IDS.PLAY_PLAYLIST, label: "Play Playlist" },
      { id: ACTION_IDS.QUEUE_PLAYLIST, label: "Queue Playlist" },
      { id: ACTION_IDS.IMPORT_PLAYLIST, label: "Import playlist" },
      { id: ACTION_IDS.ADD_URL, label: "Queue" },
    ];
  }
  // filter default action from base
  base = base.filter((action) => action.id !== defaultActionId.value);
  return base;
});

const primaryActionLabel = computed(() => {
  if (defaultActionId.value === ACTION_IDS.QUEUE_PLAYLIST) return "Queue Playlist";
  if (defaultActionId.value === ACTION_IDS.ADD_URL) return "Queue";
  if (defaultActionId.value === ACTION_IDS.PLAY_PLAYLIST) return "Play Playlist";
  return "Play";
});

const actionDropdownItems = computed(() => [
  ...availableActions.value.map((action) => ({
    label: action.label,
    onSelect: () => runAction(action.id, addUrlSheetOpen.value),
  })),
]);

function consumeInputUrl() {
  const url = urlInput.value.trim();
  if (!url) return null;
  urlInput.value = "";
  return url;
}

function runAction(actionId, closeAfter = false) {
  const rawUrl = consumeInputUrl();
  if (!rawUrl) return;

  const isStartRadio = isStartRadioUrl(rawUrl);
  const urlForSingle = isStartRadio ? getVideoOnlyUrl(rawUrl) : rawUrl;
  const urlForPlaylist = isStartRadio ? rawUrl : getCanonicalPlaylistUrl(rawUrl);

  if (actionId === ACTION_IDS.PLAY_PLAYLIST) {
    playUrl(urlForPlaylist);
  } else if (actionId === ACTION_IDS.QUEUE_PLAYLIST) {
    addUrl(urlForPlaylist);
  } else if (actionId === ACTION_IDS.IMPORT_PLAYLIST) {
    importPlaylistUrl(urlForPlaylist);
  } else if (actionId === ACTION_IDS.ADD_URL) {
    addUrl(urlForSingle);
  } else {
    playUrl(urlForSingle);
  }

  if (closeAfter) {
    addUrlSheetOpen.value = false;
  }
}

function runPrimaryAction() {
  runAction(defaultActionId.value, false);
}

function runPrimaryActionThenClose() {
  runAction(defaultActionId.value, true);
}
</script>
