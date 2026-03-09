<template>
  <aside class="min-h-0 overflow-hidden rounded-xl border border-neutral-700 bg-neutral-900 p-3">
    <div class="mb-3 flex items-center justify-between gap-2">
      <h2 class="text-2xl font-bold">Sonos</h2>
      <button type="button" class="rounded-md border border-neutral-700 bg-neutral-800 px-2 py-1 text-sm hover:bg-neutral-700" @click="$emit('refresh')">
        Refresh
      </button>
    </div>

    <ul class="max-h-[66vh] space-y-2 overflow-auto pr-1">
      <li v-for="speaker in speakers" :key="speaker.uid" class="rounded-md border border-neutral-700 p-2">
        <div class="flex items-center justify-between gap-2">
          <div>
            <div class="text-lg font-semibold leading-5">{{ speaker.name }}</div>
            <div class="text-xs text-neutral-400">{{ speaker.ip }}</div>
          </div>
          <button type="button" class="rounded-md border border-neutral-700 bg-neutral-800 px-2 py-1 text-sm hover:bg-neutral-700" @click="$emit('play', speaker.ip)">
            Play
          </button>
        </div>

        <div class="mt-2 flex flex-wrap items-center gap-2">
          <select v-model="groupTargets[speaker.ip]" class="min-w-[130px] flex-1 rounded-md border border-neutral-700 bg-neutral-800 px-2 py-1 text-sm">
            <option :value="speaker.ip">Group target</option>
            <option
              v-for="coordinator in coordinators(speaker.ip)"
              :key="coordinator.ip"
              :value="coordinator.ip"
            >
              {{ coordinator.name }}
            </option>
          </select>
          <button
            type="button"
            class="rounded-md border border-neutral-700 bg-neutral-800 px-2 py-1 text-sm hover:bg-neutral-700"
            @click="$emit('group', { coordinatorIp: groupTargets[speaker.ip], memberIp: speaker.ip })"
          >
            Group
          </button>
          <button type="button" class="rounded-md border border-neutral-700 bg-neutral-900 px-2 py-1 text-sm hover:bg-neutral-800" @click="$emit('ungroup', speaker.ip)">
            Ungroup
          </button>
        </div>

        <label class="mt-2 grid grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-2 text-sm">
          <span>Volume</span>
          <input
            type="range"
            min="0"
            max="100"
            :value="speaker.volume ?? 0"
            @change="$emit('set-volume', { ip: speaker.ip, volume: Number($event.target.value) })"
          />
          <span>{{ speaker.volume ?? 0 }}</span>
        </label>
      </li>
    </ul>
  </aside>
</template>

<script setup>
import { reactive } from "vue";

const props = defineProps({
  speakers: {
    type: Array,
    default: () => [],
  },
});

defineEmits(["refresh", "play", "group", "ungroup", "set-volume"]);

const groupTargets = reactive({});

function coordinators(currentIp) {
  return props.speakers.filter((speaker) => speaker.ip !== currentIp && speaker.is_coordinator);
}
</script>
