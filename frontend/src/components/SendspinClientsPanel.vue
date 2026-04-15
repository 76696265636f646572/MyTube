<template>
  <aside class="flex min-h-0 h-full flex-col overflow-hidden rounded-xl border border-neutral-700 p-3 surface-panel">
    <div class="mb-3 flex items-center justify-between gap-2">
      <h2 class="text-2xl font-bold">Clients</h2>
    </div>

    <div v-if="clients.length" class="min-h-0 flex-1 space-y-3 overflow-auto pr-1">
      <!-- Group volume -->
      <div v-if="clients.length > 1" class="rounded-xl border p-3 playlist-card surface-elevated">
        <div class="grid grid-cols-[minmax(0,1fr)_auto] items-end gap-x-3 gap-y-2">
          <label class="min-w-0 truncate text-sm font-medium" for="sendspin-group-volume">
            Group volume
          </label>
          <div class="text-sm text-muted tabular-nums">{{ groupVolume }}</div>
          <USlider
            id="sendspin-group-volume"
            class="min-w-0"
            :model-value="groupVolume"
            :min="0"
            :max="100"
            color="primary"
            size="md"
            @update:model-value="onGroupVolumeChange"
          />
        </div>
      </div>

      <!-- Per-client cards -->
      <div
        v-for="client in clients"
        :key="client.client_id"
        class="rounded-xl border p-3 playlist-card surface-elevated"
      >
        <div class="flex items-center gap-2">
          <div class="flex min-w-0 flex-1 items-center gap-3">
            <div class="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border playlist-card surface-panel">
              <UIcon :name="clientIcon(client)" class="size-5" />
            </div>
            <div class="min-w-0 flex-1">
              <div class="truncate text-sm font-semibold">
                {{ client.name || "Unknown client" }}
                <span v-if="isThisBrowser(client)" class="text-xs text-primary-400">(this browser)</span>
              </div>
              <div v-if="client.codec" class="text-xs text-muted">{{ client.codec }}</div>
            </div>
          </div>

          <div v-if="client.volume != null" class="hidden shrink-0 items-center gap-1 text-sm text-muted sm:flex">
            <UIcon :name="client.volume > 0 && !client.muted ? 'i-bi-volume-up-fill' : 'i-bi-volume-mute-fill'" class="size-4" />
            <span>{{ client.volume }}</span>
          </div>

          <UButton
            type="button"
            color="neutral"
            variant="ghost"
            size="sm"
            :icon="isExpanded(client.client_id) ? 'i-bi-chevron-up' : 'i-bi-chevron-down'"
            :aria-label="isExpanded(client.client_id) ? `Collapse ${client.name}` : `Expand ${client.name}`"
            @click="toggleExpanded(client.client_id)"
          />
        </div>

        <div v-if="client.volume != null" class="mt-2 flex items-center gap-1 text-xs text-muted sm:hidden">
          <UIcon :name="client.volume > 0 && !client.muted ? 'i-bi-volume-up-fill' : 'i-bi-volume-mute-fill'" class="size-3.5" />
          <span>{{ client.volume }}</span>
        </div>

        <div v-if="isExpanded(client.client_id)" class="mt-4 border-t playlist-card">
          <div class="mt-2 grid grid-cols-[minmax(0,1fr)_auto] items-end gap-x-3 gap-y-2">
            <label
              class="min-w-0 truncate text-sm font-medium"
              :for="`sendspin-volume-${client.client_id}`"
            >
              Volume
            </label>
            <div class="text-sm text-muted tabular-nums">{{ client.volume ?? 0 }}</div>
            <USlider
              :id="`sendspin-volume-${client.client_id}`"
              class="min-w-0"
              :model-value="client.volume ?? 0"
              :min="0"
              :max="100"
              color="neutral"
              size="md"
              @update:model-value="onVolumeChange(client.client_id, $event)"
            />
          </div>

          <div class="mt-4 grid grid-cols-4 gap-2 overflow-hidden">
            <UButton
              v-for="preset in volumePresets"
              :key="preset.value"
              type="button"
              color="neutral"
              variant="outline"
              class="truncate"
              @click="setClientVolume(client.client_id, preset.value)"
            >
              {{ preset.label }}
            </UButton>
          </div>

          <div v-if="client.device_info" class="mt-4 space-y-1 text-xs text-muted">
            <p v-if="client.device_info.product_name">{{ client.device_info.product_name }}</p>
            <p v-if="client.device_info.manufacturer">{{ client.device_info.manufacturer }}</p>
            <p v-if="client.device_info.software_version">v{{ client.device_info.software_version }}</p>
          </div>

          <div v-if="client.static_delay_ms != null" class="mt-3 text-xs text-muted">
            Delay: {{ client.static_delay_ms }}ms
          </div>
        </div>
      </div>
    </div>

    <div v-else class="flex flex-1 items-center justify-center rounded-xl border border-dashed p-4 text-sm text-muted">
      No SendSpin clients connected.
    </div>
  </aside>
</template>

<script setup>
import { inject, ref, watch } from "vue";

import { debounce } from "../composables/useDebounce";
import { fetchJson } from "../composables/useApi";

const VOLUME_DEBOUNCE_MS = 420;
const STORAGE_KEY_CLIENT_ID = "airwave:sendspin:client-id";

const { sendspinClients: clients, sendspinGroup } = inject("sendspinPlayer");

const expandedIds = ref({});
const volumeDebouncers = new Map();

const volumePresets = [
  { label: "Mute", value: 0 },
  { label: "10%", value: 10 },
  { label: "30%", value: 30 },
  { label: "75%", value: 75 },
];

const groupVolume = ref(0);

watch(sendspinGroup, (g) => {
  if (g && typeof g.volume === "number") {
    groupVolume.value = g.volume;
  }
}, { immediate: true, deep: true });

function isThisBrowser(client) {
  if (typeof window === "undefined") return false;
  try {
    const storedId = window.localStorage.getItem(STORAGE_KEY_CLIENT_ID);
    return storedId && storedId === client.client_id;
  } catch {
    return false;
  }
}

function clientIcon(client) {
  if (isThisBrowser(client)) return "i-bi-browser-chrome";
  const roles = client.roles || [];
  if (roles.some((r) => r.startsWith("player"))) return "i-bi-speaker-fill";
  return "i-bi-display";
}

function isExpanded(clientId) {
  return !!expandedIds.value[clientId];
}

function toggleExpanded(clientId) {
  expandedIds.value = {
    ...expandedIds.value,
    [clientId]: !expandedIds.value[clientId],
  };
}

function getVolumeDebouncer(clientId) {
  if (!volumeDebouncers.has(clientId)) {
    volumeDebouncers.set(
      clientId,
      debounce((id, vol) => {
        void commitClientVolume(id, vol);
      }, VOLUME_DEBOUNCE_MS),
    );
  }
  return volumeDebouncers.get(clientId);
}

async function commitClientVolume(clientId, volume) {
  try {
    await fetchJson(`/api/sendspin/clients/${encodeURIComponent(clientId)}/volume`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ volume }),
    });
  } catch {
    /* ignore */
  }
}

function onVolumeChange(clientId, rawValue) {
  const vol = clampVolume(rawValue);
  if (vol === null) return;
  getVolumeDebouncer(clientId)(clientId, vol);
}

async function setClientVolume(clientId, volume) {
  const vol = clampVolume(volume);
  if (vol === null) return;
  await commitClientVolume(clientId, vol);
}

const groupVolumeDebouncer = debounce(async (vol) => {
  try {
    await fetchJson("/api/sendspin/group/volume", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ volume: vol }),
    });
  } catch {
    /* ignore */
  }
}, VOLUME_DEBOUNCE_MS);

function onGroupVolumeChange(rawValue) {
  const vol = clampVolume(rawValue);
  if (vol === null) return;
  groupVolume.value = vol;
  groupVolumeDebouncer(vol);
}

function clampVolume(rawVolume) {
  const volume = Array.isArray(rawVolume) ? Number(rawVolume[0] ?? 0) : Number(rawVolume ?? 0);
  const clamped = Math.max(0, Math.min(100, volume));
  return Number.isFinite(clamped) ? clamped : null;
}
</script>
