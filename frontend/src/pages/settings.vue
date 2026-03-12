<template>
  <section class="min-h-0 h-full flex rounded-xl border border-neutral-700 overflow-hidden surface-panel">
    <nav class="flex shrink-0 flex-col border-r border-neutral-700 w-48 py-4 surface-panel">
      <RouterLink
        to="/settings"
        class="px-4 py-2 text-sm font-medium"
        :class="
          $route.path === '/settings' || $route.path === '/settings/'
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
import { RouterLink, RouterView } from "vue-router";
</script>
