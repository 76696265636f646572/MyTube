<template>
  <UApp :toaster="{ position: 'bottom-right' }">
    <div class="h-dvh overflow-hidden bg-neutral-950 p-3 text-neutral-100 flex flex-col gap-3">
      <TopBar />

      <div class="min-h-0 flex-1 grid gap-3 xl:grid-cols-[260px_minmax(0,1fr)_340px]">
        <SidebarPlaylists class="h-full" />

        <main class="min-h-0 h-full">
          <RouterView v-slot="{ Component }">
            <component :is="Component" />
          </RouterView>
        </main>

        <aside class="min-h-0 h-full flex flex-col gap-3">
          <template v-if="sidebarView === SIDEBAR_QUEUE_VIEW">
            <UTabs
              v-model="activeQueueTab"
              :items="queueSidebarTabs"
              class="w-full min-h-0 h-full"
              :ui="{ content: 'h-full min-h-0' }"
              :unmount-on-hide="false"
            >
              <template #queue>
                <QueuePanel class="h-full" />
              </template>

              <template #history>
                <HistoryPanel class="h-full" />
              </template>
            </UTabs>
          </template>

          <SonosPanel v-else class="h-full" />
        </aside>
      </div>

      <PlayerBar />
    </div>
  </UApp>
</template>

<script setup>
import { onMounted } from "vue";
import { useRoute } from "vue-router";

import HistoryPanel from "./components/HistoryPanel.vue";
import PlayerBar from "./components/PlayerBar.vue";
import QueuePanel from "./components/QueuePanel.vue";
import SidebarPlaylists from "./components/SidebarPlaylists.vue";
import SonosPanel from "./components/SonosPanel.vue";
import TopBar from "./components/TopBar.vue";
import { initializeLibraryState } from "./composables/useLibraryState";
import { initializeNotifications } from "./composables/useNotifications";
import { initializePlaybackState } from "./composables/usePlaybackState";
import { initializeSonosState } from "./composables/useSonosState";
import {
  SIDEBAR_QUEUE_VIEW,
  useUiState,
} from "./composables/useUiState";

const route = useRoute();
const { sidebarView, activeQueueTab, queueSidebarTabs, initializeUiState } = useUiState();
initializeNotifications(useToast());

onMounted(async () => {
  initializeUiState(route);
  await Promise.allSettled([initializeLibraryState(), initializePlaybackState(), initializeSonosState()]);
});
</script>
