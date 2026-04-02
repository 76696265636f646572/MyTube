<template>
  <section
    v-if="showResponsiveLayout"
    class="min-h-0 h-full rounded-xl border border-neutral-700 surface-panel overflow-hidden"
  >
    <div v-if="showMobileMenu" class="flex h-full flex-col overflow-auto p-4 sm:p-6">
      <div>
        <h1 class="text-2xl font-bold">Settings</h1>
        <p class="mt-2 text-sm text-muted">Choose a section to manage app preferences and tools.</p>
      </div>

      <nav class="mt-6 grid gap-3" aria-label="Settings sections">
        <RouterLink
          v-for="item in settingsItems"
          :key="item.to"
          :to="item.to"
          class="rounded-xl border border-neutral-700 p-4 transition-colors surface-panel hover:border-neutral-500 hover:bg-neutral-700/20"
        >
          <div class="flex items-start justify-between gap-3">
            <div>
              <div class="text-base font-semibold text-white">{{ item.label }}</div>
              <p class="mt-1 text-sm text-muted">{{ item.description }}</p>
            </div>
            <UIcon name="i-bi-chevron-right" class="mt-1 size-4 shrink-0 text-muted" />
          </div>
        </RouterLink>
      </nav>
    </div>

    <div v-else class="flex h-full min-h-0 flex-col overflow-hidden">
      <div class="flex items-center gap-2 border-b border-neutral-700 px-4 py-3 sm:px-6">
        <UButton
          type="button"
          variant="ghost"
          color="neutral"
          icon="i-bi-arrow-left"
          label="Settings"
          @click="goToSettingsMenu"
        />
      </div>
      <div class="min-h-0 flex-1 overflow-auto p-4 sm:p-6">
        <RouterView />
      </div>
    </div>
  </section>

  <section v-else class="min-h-0 h-full flex rounded-xl border border-neutral-700 overflow-hidden surface-panel">
    <nav class="flex shrink-0 flex-col border-r border-neutral-700 w-48 py-4 surface-panel">
      <RouterLink
        to="/settings"
        class="px-4 py-2 text-sm font-medium"
        :class="
          $route.path === '/settings' || $route.path === '/settings/' || $route.path === '/settings/general'
            ? 'bg-neutral-700/50 text-white'
            : 'text-muted hover:text-white hover:bg-neutral-700/30'
        "
      >
        General
      </RouterLink>
      <RouterLink
        to="/settings/update"
        class="px-4 py-2 text-sm font-medium"
        :class="
          $route.path === '/settings/update'
            ? 'bg-neutral-700/50 text-white'
            : 'text-muted hover:text-white hover:bg-neutral-700/30'
        "
      >
        Update
      </RouterLink>
      <RouterLink
        to="/settings/cookies"
        class="px-4 py-2 text-sm font-medium"
        :class="
          $route.path === '/settings/cookies'
            ? 'bg-neutral-700/50 text-white'
            : 'text-muted hover:text-white hover:bg-neutral-700/30'
        "
      >
        Cookies
      </RouterLink>
    </nav>
    <div class="min-h-0 flex-1 overflow-auto p-6">
      <RouterView />
    </div>
  </section>
</template>

<script setup>
import { computed } from "vue";
import { RouterLink, RouterView, useRoute, useRouter } from "vue-router";

import { useBreakpoint } from "../composables/useBreakpoint";

const route = useRoute();
const router = useRouter();
const { isMobile, isTabletLayout } = useBreakpoint();

const settingsItems = [
  {
    label: "General",
    description: "Theme and appearance preferences.",
    to: "/settings/general",
  },
  {
    label: "Update",
    description: "Manage bundled binaries and install updates.",
    to: "/settings/update",
  },
  {
    label: "Cookies",
    description: "Configure provider cookies for yt-dlp.",
    to: "/settings/cookies",
  },
];

const showResponsiveLayout = computed(() => isMobile.value || isTabletLayout.value);
const showMobileMenu = computed(() => route.path === "/settings" || route.path === "/settings/");

function goToSettingsMenu() {
  router.replace("/settings");
}
</script>
