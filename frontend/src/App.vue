<template>
  <UApp :toaster="{ position: 'bottom-right' }">
    <template v-if="isFullScreenPlayerRoute">
      <RouterView v-slot="{ Component }">
        <component :is="Component" />
      </RouterView>
    </template>
    <div v-else class="app-shell min-h-dvh md:h-dvh overflow-y-auto md:overflow-hidden p-3 text-neutral-100 flex flex-col gap-3">
      <TopBar />

      <div
        class="main-grid min-h-0 w-full flex-none md:flex-1 flex min-w-0 gap-3 xl:grid xl:grid-cols-[minmax(0,350px)_minmax(0,1fr)_minmax(0,350px)] xl:grid-rows-1"
        :class="{ 'main-grid-with-mobile-bottom': isMobile }"
      >
        <div class="min-h-0 h-full min-w-0 max-w-[350px] flex flex-col overflow-hidden hidden md:flex xl:flex">
          <SidebarPlaylists class="min-h-0 min-w-0 flex-1" />
        </div>

        <!-- Below xl: right sidebar overlays main; xl+: children slot into 3-column grid (display:contents) -->
        <div class="main-and-right relative min-h-0 min-w-0 flex-1 flex flex-col xl:contents">
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

          <aside
            v-if="!isMobile"
            :class="{ 'max-xl:hidden': !rightSidebarOpen, 'surface-panel': rightSidebarOpen }"
            class="right-sidebar min-h-0 h-full min-w-0 flex flex-col gap-3 overflow-hidden max-xl:absolute max-xl:inset-y-0 max-xl:right-0 max-xl:z-30 max-xl:w-full max-xl:max-w-[350px] max-xl:shadow-2xl max-xl:rounded-xl xl:static xl:max-w-[350px]"
          >
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
      </div>

      <!-- Mobile: fixed bottom strip — player floats above nav (Spotify-style) -->
      <div v-if="isMobile" class="mobile-bottom-fixed">
        <PlayerBar />
        <MobileNavBar />
      </div>
      <!-- Desktop: player in flow -->
      <PlayerBar v-else />

      <DuplicateImportModal />
    </div>

    <audio
      ref="audioEl"
      class="hidden"
      preload="none"
    />
  </UApp>
</template>

<script setup>
import { computed, onMounted, provide, ref } from "vue";
import { useRoute } from "vue-router";

import DuplicateImportModal from "./components/DuplicateImportModal.vue";
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
import { initializePlaybackState } from "./composables/usePlaybackState";
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
const isFullScreenPlayerRoute = computed(() => route.path === "/fullscreen-player" || route.path === "/fullscreen-player/");
const { isMobile } = useBreakpoint();
const audioEl = ref(null);
const {
  startLocalPlayback,
  stopLocalPlayback,
  pauseLocalPlayback,
  resumeLocalPlayback,
  localPlaybackStatus,
  localPlaybackSessionDeps,
  isLocalPlaybackActive,
  localVolume,
  isMuted,
  setLocalVolume,
  toggleMuted,
} = useLocalPlayback(audioEl);

provide("localPlayback", {
  startLocalPlayback,
  stopLocalPlayback,
  pauseLocalPlayback,
  resumeLocalPlayback,
  localPlaybackStatus,
  isLocalPlaybackActive,
  localVolume,
  isMuted,
  setLocalVolume,
  toggleMuted,
});

useMediaSession({
  pauseLocalPlayback,
  resumeLocalPlayback,
  stopLocalPlayback,
  localPlaybackStatus,
  localPlaybackSessionDeps,
});

const {
  sidebarView,
  activeQueueTab,
  queueSidebarTabs,
  mobileView,
  rightSidebarOpen,
  initializeUiState,
} = useUiState();

initializeNotifications(useToast());

onMounted(async () => {
  initializeTheme();
  initializeUiState(route);
  await Promise.allSettled([initializeLibraryState(), initializePlaybackState(), initializeSonosState()]);
});
</script>
