<template>
  <aside class="min-h-0 h-full overflow-hidden rounded-xl border border-neutral-700 bg-neutral-900 p-3 flex flex-col">
    <div class="mb-3 flex items-center justify-between gap-2">
      <h2 class="text-2xl font-bold">Sonos</h2>
      <UButton type="button" color="primary" variant="soft" size="sm" @click="refreshSonosManual">
        Refresh
      </UButton>
    </div>

    <ul class="min-h-0 flex-1 space-y-2 overflow-auto pr-1">
      <li v-for="speaker in speakers" :key="speaker.uid" class="rounded-md border border-neutral-700 p-2">
        <div class="flex items-center justify-between gap-2">
          <div>
            <div class="text-lg font-semibold leading-5">{{ speaker.name }}</div>
            <div class="text-xs text-neutral-400">{{ speaker.ip }}</div>
          </div>
          <UButton type="button" color="primary" variant="solid" size="sm" @click="playOnSpeaker(speaker.ip)">
            Play
          </UButton>
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
          <UButton
            type="button"
            color="neutral"
            variant="outline"
            size="sm"
            @click="groupSpeaker({ coordinatorIp: groupTargets[speaker.ip], memberIp: speaker.ip })"
          >
            Group
          </UButton>
          <UButton
            v-if="isGrouped(speaker)"
            type="button"
            color="warning"
            variant="ghost"
            size="sm"
            @click="ungroupSpeaker(speaker.ip)"
          >
            Ungroup
          </UButton>
        </div>

        <label class="mt-2 grid grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-2 text-sm">
          <span>Volume</span>
          <USlider
            :model-value="speaker.volume ?? 0"
            :min="0"
            :max="100"
            color="neutral"
            size="md"
            @update:model-value="setSpeakerVolume({ ip: speaker.ip, volume: Number($event ?? 0) })"
          />
          <span>{{ speaker.volume ?? 0 }}</span>
        </label>
      </li>
    </ul>
  </aside>
</template>

<script setup>
import { reactive } from "vue";

import { useSonosState } from "../composables/useSonosState";

const {
  speakers,
  refreshSonosManual,
  playOnSpeaker,
  groupSpeaker,
  ungroupSpeaker,
  setSpeakerVolume,
} = useSonosState();

const groupTargets = reactive({});

function coordinators(currentIp) {
  return speakers.value.filter((speaker) => speaker.ip !== currentIp && speaker.is_coordinator);
}

function isGrouped(speaker) {
  if (speaker?.coordinator_uid && speaker?.uid && speaker.coordinator_uid !== speaker.uid) {
    return true;
  }
  return Array.isArray(speaker?.group_member_uids) && speaker.group_member_uids.length > 1;
}
</script>
