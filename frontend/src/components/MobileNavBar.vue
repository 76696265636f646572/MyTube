<template>
  <nav
    class="mobile-nav-bar flex shrink-0 items-center justify-around gap-1 border-t border-neutral-700 bg-[var(--app-surface)] py-2"
    aria-label="Main navigation"
  >
    <UButton
      type="button"
      :color="isActiveHome ? 'primary' : 'neutral'"
      :variant="isActiveHome ? 'soft' : 'ghost'"
      class="flex min-h-[2.75rem] min-w-[2.75rem] flex-col gap-0.5 p-2"
      aria-label="Home"
      @click="goHome"
    >
      <UIcon name="i-bi-house-fill" class="size-5" />
      <span class="text-xs">Home</span>
    </UButton>
    <UButton
      type="button"
      :color="isActiveSearch ? 'primary' : 'neutral'"
      :variant="isActiveSearch ? 'soft' : 'ghost'"
      class="flex min-h-[2.75rem] min-w-[2.75rem] flex-col gap-0.5 p-2"
      aria-label="Search"
      @click="goSearch"
    >
      <UIcon name="i-bi-search" class="size-5" />
      <span class="text-xs">Search</span>
    </UButton>
    <UButton
      type="button"
      :color="mobileView === MOBILE_VIEW_PLAYLISTS ? 'primary' : 'neutral'"
      :variant="mobileView === MOBILE_VIEW_PLAYLISTS ? 'soft' : 'ghost'"
      class="flex min-h-[2.75rem] min-w-[2.75rem] flex-col gap-0.5 p-2"
      aria-label="Playlists"
      @click="mobileView = MOBILE_VIEW_PLAYLISTS"
    >
      <UIcon name="i-bi-list" class="size-5" />
      <span class="text-xs">Playlists</span>
    </UButton>
    <UButton
      type="button"
      :color="mobileView === MOBILE_VIEW_QUEUE ? 'primary' : 'neutral'"
      :variant="mobileView === MOBILE_VIEW_QUEUE ? 'soft' : 'ghost'"
      class="flex min-h-[2.75rem] min-w-[2.75rem] flex-col gap-0.5 p-2"
      aria-label="Queue and history"
      @click="mobileView = MOBILE_VIEW_QUEUE"
    >
      <UIcon name="i-bi-music-note-list" class="size-5" />
      <span class="text-xs">Queue</span>
    </UButton>
    <UButton
      type="button"
      :color="mobileView === MOBILE_VIEW_SPEAKERS ? 'primary' : 'neutral'"
      :variant="mobileView === MOBILE_VIEW_SPEAKERS ? 'soft' : 'ghost'"
      class="flex min-h-[2.75rem] min-w-[2.75rem] flex-col gap-0.5 p-2"
      aria-label="Speakers"
      @click="mobileView = MOBILE_VIEW_SPEAKERS"
    >
      <UIcon name="i-bi-speaker-fill" class="size-5" />
      <span class="text-xs">Speakers</span>
    </UButton>
    <UButton
      type="button"
      :color="isActiveSettings ? 'primary' : 'neutral'"
      :variant="isActiveSettings ? 'soft' : 'ghost'"
      class="flex min-h-[2.75rem] min-w-[2.75rem] flex-col gap-0.5 p-2"
      aria-label="Settings"
      @click="goSettings"
    >
      <UIcon name="i-bi-gear-fill" class="size-5" />
      <span class="text-xs">Settings</span>
    </UButton>
  </nav>
</template>

<script setup>
import { computed } from "vue";
import { useRoute, useRouter } from "vue-router";

import {
  MOBILE_VIEW_HOME,
  MOBILE_VIEW_PLAYLISTS,
  MOBILE_VIEW_QUEUE,
  MOBILE_VIEW_SPEAKERS,
  useUiState,
} from "../composables/useUiState";

const router = useRouter();
const route = useRoute();
const { mobileView } = useUiState();

/** Only one nav item is ever active: route-based (Home/Search/Settings) only when home pane is shown. */
const isActiveHome = computed(() => mobileView.value === MOBILE_VIEW_HOME && route.path === "/");
const isActiveSearch = computed(() => mobileView.value === MOBILE_VIEW_HOME && route.path === "/search");
const isActiveSettings = computed(() => mobileView.value === MOBILE_VIEW_HOME && route.path === "/settings");

function goHome() {
  mobileView.value = MOBILE_VIEW_HOME;
  if (route.path !== "/") router.push("/");
}

function goSearch() {
  mobileView.value = MOBILE_VIEW_HOME;
  router.push("/search");
}

function goSettings() {
  mobileView.value = MOBILE_VIEW_HOME;
  router.push("/settings");
}
</script>
