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

    <div class="mt-8 max-w-sm">
      <label for="audio-delay" class="block text-sm font-medium">Audio delay</label>
      <p class="mt-1 text-xs text-muted">
        Adds a fixed delay to compensate for network latency between this browser and other SendSpin players.
      </p>
      <div class="mt-3 flex items-center gap-3">
        <USlider
          id="audio-delay"
          :model-value="delayValue"
          :min="0"
          :max="5000"
          :step="50"
          color="neutral"
          size="md"
          class="flex-1"
          aria-label="Audio delay (ms)"
          @update:model-value="onDelayChange"
        />
        <span class="w-16 text-right text-sm text-muted tabular-nums">{{ delayValue }}ms</span>
      </div>
    </div>
  </section>
</template>

<script setup>
import { inject, ref, watch } from "vue";

import { useTheme } from "../../composables/useTheme";

const { currentTheme, supportedThemes, setTheme } = useTheme();

const sendspinPlayer = inject("sendspinPlayer", null);

const delayValue = ref(sendspinPlayer?.staticDelay?.value ?? 0);

if (sendspinPlayer?.staticDelay) {
  watch(sendspinPlayer.staticDelay, (v) => {
    delayValue.value = v;
  });
}

function onThemeChange(value) {
  setTheme(value);
}

function onDelayChange(rawValue) {
  const val = Array.isArray(rawValue) ? Number(rawValue[0] ?? 0) : Number(rawValue ?? 0);
  if (!Number.isFinite(val)) return;
  delayValue.value = val;
  sendspinPlayer?.setSyncDelay?.(val);
}
</script>
