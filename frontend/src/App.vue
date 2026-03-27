<template>
  <UApp :toaster="{ position: 'bottom-right' }">
    <div class="app-shell min-h-dvh md:h-dvh overflow-y-auto md:overflow-hidden p-3 text-neutral-100 flex flex-col gap-3">
      <TopBar />

      <div
        class="main-grid min-h-0 w-full flex-none md:flex-1 flex min-w-0 gap-3 xl:grid xl:grid-cols-[350px_minmax(0,1fr)_340px] xl:grid-rows-1"
        :class="{ 'main-grid-with-mobile-bottom': isMobile }"
      >
        <div class="min-h-0 h-full flex flex-col overflow-hidden hidden md:flex xl:flex">
          <SidebarPlaylists class="min-h-0 min-w-0 flex-1" />
        </div>

        <main class="main-content min-h-0 w-full flex-none md:flex-1 flex min-w-0 flex-col overflow-visible md:overflow-hidden">
          <!-- Desktop: single RouterView -->
          <template v-if="!isMobile">
            <div class="min-h-0 flex-1 overflow-auto">
              <RouterView v-slot="{ Component }">
                <component :is="Component" />
              </RouterView>
            </div>
          </template>
          <!-- Mobile: panes in main content (no modals), one visible at a time -->
          <template v-else>
            <div
              v-show="mobileView === MOBILE_VIEW_HOME"
              class="mobile-pane min-h-0 w-full flex-none md:flex-1 overflow-visible md:overflow-auto"
            >
              <RouterView v-slot="{ Component }">
                <component :is="Component" />
              </RouterView>
            </div>
            <div
              v-show="mobileView === MOBILE_VIEW_PLAYLISTS"
              class="mobile-pane min-h-0 w-full flex-none md:flex-1 overflow-visible md:overflow-auto rounded-xl border border-neutral-700 surface-panel"
            >
              <SidebarPlaylists class="h-full min-h-0" />
            </div>
            <div
              v-show="mobileView === MOBILE_VIEW_QUEUE"
              class="mobile-pane min-h-0 w-full flex-none md:flex-1 flex flex-col overflow-visible md:overflow-hidden rounded-xl border border-neutral-700 surface-panel"
            >
              <UTabs
                v-model="activeQueueTab"
                :items="queueSidebarTabs"
                class="min-h-0 flex-1"
                :ui="{ content: 'min-h-0 flex-1 overflow-auto' }"
                :unmount-on-hide="false"
              >
                <template #queue>
                  <QueuePanel class="min-h-0 h-full" />
                </template>
                <template #history>
                  <HistoryPanel class="min-h-0 h-full" />
                </template>
              </UTabs>
            </div>
            <div
              v-show="mobileView === MOBILE_VIEW_SONOS"
              class="mobile-pane min-h-0 w-full flex-none md:flex-1 overflow-visible md:overflow-auto rounded-xl border border-neutral-700 surface-panel"
            >
              <SonosPanel class="min-h-0 h-full" />
            </div>
          </template>
        </main>

        <aside v-if="!isMobile" class="min-h-0 h-full flex flex-col gap-3 overflow-hidden">
          <template v-if="sidebarView === SIDEBAR_QUEUE_VIEW">
            <UTabs
              v-model="activeQueueTab"
              :items="queueSidebarTabs"
              class="w-full min-h-0 flex-1 flex flex-col overflow-hidden"
              :ui="{ content: 'min-h-0 flex-1 flex flex-col overflow-hidden' }"
              :unmount-on-hide="false"
            >
              <template #queue>
                <QueuePanel class="min-h-0 flex-1" />
              </template>

              <template #history>
                <HistoryPanel class="min-h-0 flex-1" />
              </template>
            </UTabs>
          </template>

          <SonosPanel v-else class="min-h-0 flex-1" />
        </aside>
      </div>

      <!-- Mobile: fixed bottom strip — player floats above nav (Spotify-style) -->
      <div v-if="isMobile" class="mobile-bottom-fixed">
        <PlayerBar />
        <MobileNavBar />
      </div>
      <!-- Desktop: player in flow -->
      <PlayerBar v-else />

      <FullScreenPlayer />
      <DuplicateImportModal />

      <audio
        ref="audioEl"
        class="hidden"
        :src="playbackState.stream_url"
        preload="none"
      />
    </div>
  </UApp>
</template>

<script setup>
import { onMounted, provide, ref } from "vue";
import { useRoute } from "vue-router";

import DuplicateImportModal from "./components/DuplicateImportModal.vue";
import FullScreenPlayer from "./components/FullScreenPlayer.vue";
import HistoryPanel from "./components/HistoryPanel.vue";
import MobileNavBar from "./components/MobileNavBar.vue";
import PlayerBar from "./components/PlayerBar.vue";
import QueuePanel from "./components/QueuePanel.vue";
import SidebarPlaylists from "./components/SidebarPlaylists.vue";
import SonosPanel from "./components/SonosPanel.vue";
import TopBar from "./components/TopBar.vue";
import { useBreakpoint } from "./composables/useBreakpoint";
import { useLocalPlayback } from "./composables/useLocalPlayback";
import { useMediaSession } from "./composables/useMediaSession";
import { initializeLibraryState } from "./composables/useLibraryState";
import { initializeNotifications } from "./composables/useNotifications";
import { initializePlaybackState, usePlaybackState } from "./composables/usePlaybackState";
import { initializeSonosState } from "./composables/useSonosState";
import {
  MOBILE_VIEW_HOME,
  MOBILE_VIEW_PLAYLISTS,
  MOBILE_VIEW_QUEUE,
  MOBILE_VIEW_SONOS,
  SIDEBAR_QUEUE_VIEW,
  useUiState,
} from "./composables/useUiState";
import { initializeTheme } from "./composables/useTheme";

const route = useRoute();
const { isMobile } = useBreakpoint();
const { playbackState } = usePlaybackState();
const audioEl = ref(null);
const {
  startLocalPlayback,
  stopLocalPlayback,
  isLocalPlaybackActive,
  localVolume,
  isMuted,
  setLocalVolume,
  toggleMuted,
} = useLocalPlayback(audioEl);

provide("localPlayback", {
  startLocalPlayback,
  stopLocalPlayback,
  isLocalPlaybackActive,
  localVolume,
  isMuted,
  setLocalVolume,
  toggleMuted,
});

const {
  sidebarView,
  activeQueueTab,
  queueSidebarTabs,
  mobileView,
  initializeUiState,
} = useUiState();

initializeNotifications(useToast());

onMounted(async () => {
  initializeTheme();
  initializeUiState(route);
  useMediaSession();
  await Promise.allSettled([initializeLibraryState(), initializePlaybackState(), initializeSonosState()]);
});
</script>
