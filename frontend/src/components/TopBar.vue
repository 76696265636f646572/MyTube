<template>
  <header class="rounded-xl border border-neutral-700 p-3 surface-panel">
    <!-- Desktop / tablet: full layout (single branch to avoid duplicate content in DOM) -->
    <template v-if="!isMobile">
    <div class="flex flex-col gap-2 sm:flex-row sm:items-center">
      <h1 class="text-2xl font-bold leading-tight">MyTube Radio</h1>
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
    <form class="mt-3 flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center" @submit.prevent="emitQueueUrl">
      <input
        v-model="urlInput"
        type="url"
        placeholder="https://www.youtube.com/watch?v=... or https://www.youtube.com/playlist?list=..."
        required
        class="h-10 w-full min-w-0 flex-1 rounded-md border px-3 text-sm surface-input"
      />
      <div class="flex w-full gap-2 sm:w-auto">
        <template v-if="isPlaylistUrl">
          <UButton
            type="button"
            color="success"
            variant="solid"
            size="md"
            class="flex-1 sm:flex-none"
            @click="emitImportPlaylist"
          >
            Import playlist
          </UButton>
          <UButton type="submit" color="neutral" variant="outline" size="md" class="flex-1 sm:flex-none">
            Queue Playlist
          </UButton>
          <UButton
            type="button"
            color="neutral"
            variant="outline"
            size="md"
            class="flex-1 sm:flex-none"
            @click="emitPlayUrl"
          >
            Play Playlist
          </UButton>
        </template>
        <template v-else>
          <UButton type="submit" color="primary" variant="solid" size="md" class="flex-1 sm:flex-none">
            Add URL
          </UButton>
          <UButton
            type="button"
            color="neutral"
            variant="outline"
            size="md"
            class="flex-1 sm:flex-none"
            @click="emitPlayUrl"
          >
            Play URL
          </UButton>
        </template>
      </div>
    </form>
    </template>

    <!-- Mobile: compact row -->
    <template v-else>
    <div class="flex items-center justify-between gap-2">
      <h1 class="text-xl font-bold leading-tight">MyTube Radio</h1>
      <div class="flex items-center gap-1">
        <UButton
          type="button"
          color="neutral"
          variant="ghost"
          icon="i-lucide-plus-circle"
          class="min-h-[2.75rem] min-w-[2.75rem]"
          aria-label="Add URL"
          @click="addUrlSheetOpen = true"
        />
        <UButton
          type="button"
          color="neutral"
          variant="ghost"
          icon="i-lucide-settings"
          class="min-h-[2.75rem] min-w-[2.75rem] hidden md:visible"
          aria-label="Settings"
          @click="router.push('/settings')"
        />
      </div>
    </div>

    <!-- Mobile: Add URL sheet (modal only on mobile) -->
    <UModal v-model:open="addUrlSheetOpen" :ui="{ width: 'w-full max-w-sm', content: 'rounded-t-2xl surface-panel' }">
      <template #content>
        <div class="p-4">
          <h2 class="text-lg font-semibold">Add URL</h2>
          <form class="mt-3 flex flex-col gap-3" @submit.prevent="submitAddUrlSheet">
            <input
              v-model="urlInput"
              type="url"
              placeholder="https://www.youtube.com/watch?v=..."
              required
              class="h-11 w-full rounded-md border px-3 text-sm surface-input"
            />
            <div class="flex flex-wrap gap-2">
              <template v-if="isPlaylistUrl">
                <UButton type="button" color="success" variant="solid" class="flex-1" @click="emitImportPlaylistThenClose">
                  Import playlist
                </UButton>
                <UButton type="button" color="primary" variant="solid" class="flex-1" @click="emitQueueUrlThenClose">
                  Queue Playlist
                </UButton>
                <UButton type="button" color="neutral" variant="outline" class="flex-1" @click="emitPlayUrlThenClose">
                  Play Playlist
                </UButton>
              </template>
              <template v-else>
                <UButton type="submit" color="primary" variant="solid" class="flex-1">
                  Add URL
                </UButton>
                <UButton type="button" color="neutral" variant="outline" class="flex-1" @click="emitPlayUrlThenClose">
                  Play URL
                </UButton>
              </template>
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
const { addUrl, playUrl, importPlaylistUrl } = useLibraryState();
const { searchText, onSearchTextChange, onYoutubeSearch } = useUiState();

/** Playlist page URL (playlist?list=...). Watch URLs are treated as single video. */
const isPlaylistUrl = computed(() => {
  const url = urlInput.value.trim();
  if (!url) return false;
  return url.includes("/playlist") && url.includes("list=");
});

function consumeInputUrl() {
  const url = urlInput.value.trim();
  if (!url) return null;
  urlInput.value = "";
  return url;
}

function emitImportPlaylist() {
  const url = consumeInputUrl();
  if (!url) return;
  importPlaylistUrl(url);
}

function emitQueueUrl() {
  const url = consumeInputUrl();
  if (!url) return;
  addUrl(url);
}

function emitPlayUrl() {
  const url = consumeInputUrl();
  if (!url) return;
  playUrl(url);
}

function submitAddUrlSheet() {
  emitQueueUrl();
  addUrlSheetOpen.value = false;
}

function emitQueueUrlThenClose() {
  emitQueueUrl();
  addUrlSheetOpen.value = false;
}

function emitPlayUrlThenClose() {
  emitPlayUrl();
  addUrlSheetOpen.value = false;
}

function emitImportPlaylistThenClose() {
  emitImportPlaylist();
  addUrlSheetOpen.value = false;
}
</script>
