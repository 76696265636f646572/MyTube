<template>
  <section class="min-h-0 h-full rounded-xl border border-neutral-700 p-6 surface-panel overflow-auto">
    <h2 class="text-2xl font-bold">General</h2>
    <p class="mt-1 text-sm text-muted">
      Theme selection is saved in local storage and applied immediately.
    </p>

    <div class="mt-6 max-w-sm">
      <label for="theme-select" class="block text-sm font-medium">Theme</label>
      <select
        id="theme-select"
        :value="currentTheme"
        class="mt-2 h-10 w-full rounded-md border px-3 text-sm surface-input"
        @change="onThemeChange($event.target.value)"
      >
        <option v-for="t in supportedThemes" :key="t" :value="t">
          {{ t.charAt(0).toUpperCase() + t.slice(1) }}
        </option>
      </select>
    </div>
  </section>
</template>

<script setup>
import { useTheme } from "../../composables/useTheme";

const { currentTheme, supportedThemes, setTheme } = useTheme();

function onThemeChange(value) {
  setTheme(value);
}
</script>
