<template>
  <aside class="flex min-h-0 h-full flex-col overflow-hidden rounded-xl border border-neutral-700 p-3 surface-panel">
    <div class="mb-3 flex items-center justify-between gap-2">
      <h2 class="text-2xl font-bold">Sonos</h2>
      <UButton type="button" color="primary" variant="soft" size="sm" @click="refreshSonosManual">
        Refresh
      </UButton>
    </div>

    <ul v-if="groupedSpeakers.length" class="min-h-0 flex-1 space-y-3 overflow-auto pr-1">
      <li
        v-for="speaker in groupedSpeakers"
        :key="speaker.uid"
        class="rounded-xl border p-3 playlist-card surface-elevated"
      >
        <div class="flex items-center gap-2">
          <div class="flex min-w-0 flex-1 items-center gap-3">
            <div class="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border playlist-card surface-panel">
              <UIcon name="i-bi-speaker-fill" class="size-5" />
            </div>

            <div class="min-w-0 flex-1">
              <div class="truncate text-sm font-semibold">
                {{ speaker.name }}
                <span v-if="speaker.group_members.length > 1" class="text-xs text-muted">(+ {{ speaker.group_members.length-1 }})</span>
              </div>
            </div>
          </div>

          <div v-if="speaker.volume != null" class="hidden shrink-0 items-center gap-1 text-sm text-muted sm:flex">
            <UIcon :name="speaker.volume > 0 ? 'i-bi-volume-up-fill' : 'i-bi-volume-mute-fill'" class="size-4" />
            <span>{{ speaker.volume }}</span>
          </div>

          <UButton
            type="button"
            color="primary"
            :variant="speaker.is_playing ? 'soft' : 'solid'"
            size="sm"
            :icon="speaker.is_playing ? 'i-bi-stop-fill' : 'i-bi-play-fill'"
            @click="speaker.is_playing ? stopOnSpeaker(speaker.ip) : playOnSpeaker(speaker.ip)"
          >
          </UButton>

          <UButton
            type="button"
            color="neutral"
            variant="ghost"
            size="sm"
            :icon="isSpeakerExpanded(speaker.ip) ? 'i-bi-chevron-up' : 'i-bi-chevron-down'"
            :aria-label="isSpeakerExpanded(speaker.ip) ? `Collapse ${speaker.name}` : `Expand ${speaker.name}`"
            @click="toggleSpeakerExpanded(speaker.ip)"
          />
        </div>

        <div v-if="speaker.volume != null" class="mt-2 flex items-center gap-1 text-xs text-muted sm:hidden">
          <UIcon :name="speaker.volume > 0 ? 'i-bi-volume-up-fill' : 'i-bi-volume-mute-fill'" class="size-3.5" />
          <span>{{ speaker.volume }}</span>
        </div>

        <div v-if="isSpeakerExpanded(speaker.ip)" class="mt-4 border-t playlist-card">
          <label
            v-if="hasLinkedVolumeControl(speaker)"
            class="mt-3 inline-flex items-center gap-2 text-sm font-medium text-muted"
          >
            <input
              type="checkbox"
              class="h-4 w-4 shrink-0 accent-primary-500"
              :checked="isGroupVolumeLinked(speaker.ip)"
              @change="setGroupVolumeLinked(speaker.ip, $event.target.checked)"
            />
            <span>Link volume</span>
          </label>

          <div v-for="member in speakerGroupMembers(speaker)" :key="member.uid" class="playlist-card">
            <div class="mt-2 grid grid-cols-[minmax(0,1fr)_auto] items-end gap-x-3 gap-y-2">
              <label
                class="min-w-0 truncate text-sm font-medium"
                :for="`sonos-volume-${member.ip}`"
              >
                {{ speakerGroupMembers(speaker).length > 1 ? `${member.name} volume` : "Volume" }}
              </label>
              <div class="flex justify-end">
                <UButton
                  type="button"
                  color="neutral"
                  variant="soft"
                  size="sm"
                  class="shrink-0 p-0 cursor-pointer"
                  icon="i-bi-gear-fill"
                  :aria-label="`Speaker settings for ${member.name}`"
                  @click="openSpeakerSettings(member)"
                />
              </div>
              <USlider
                :id="`sonos-volume-${member.ip}`"
                class="min-w-0"
                :model-value="member.volume ?? 0"
                :min="0"
                :max="100"
                color="neutral"
                size="md"
                @update:model-value="onVolumeSliderInput(speaker, member.ip, $event)"
              />
              <div class="text-sm text-muted tabular-nums">{{ member.volume ?? 0 }}</div>
            </div>

            <div class="mt-4 grid grid-cols-4 gap-2 overflow-hidden">
              <UButton
                v-for="preset in volumePresets"
                :key="preset.value"
                type="button"
                color="neutral"
                variant="outline"
                class="truncate"
                @click="updateSpeakerVolume(speaker, member.ip, preset.value)"
              >
                {{ preset.label }}
              </UButton>
            </div>
          </div>

          <div class="mt-4 flex items-center justify-between gap-3">
            <p class="min-w-0 text-xs text-muted">{{ speakerGroupSummary(speaker) }}</p>

            <UDropdownMenu :items="speakerMenuItems(speaker)" :ui="{ separator: 'hidden' }">
              <UButton
                type="button"
                icon="i-bi-three-dots"
                color="neutral"
                variant="ghost"
                size="sm"
                aria-label="Speaker actions"
                class="shrink-0"
              />
            </UDropdownMenu>
          </div>
        </div>
      </li>
    </ul>

    <div v-else class="flex flex-1 items-center justify-center rounded-xl border border-dashed p-4 text-sm text-muted">
      No Sonos speakers found.
    </div>
  </aside>

  <UModal v-model:open="groupSettingsOpen" :ui="{ width: 'max-w-lg' }">
    <template #content>
      <div class="p-4">
        <h3 class="text-lg font-semibold">Group settings</h3>
        <p class="mt-2 text-sm text-muted">
          Rebuild the group around "{{ groupSettingsAnchorSpeaker?.name || "this speaker" }}".
          Check a speaker to join it to this speaker, or uncheck it to remove it.
        </p>

        <div v-if="!groupSettingsAnchorSpeaker" class="mt-4 text-sm text-muted">
          This speaker is no longer available.
        </div>

        <div v-else class="mt-4 max-h-80 space-y-2 overflow-auto pr-1">
          <label
            v-for="speaker in sortedSpeakers"
            :key="`group-${speaker.uid}`"
            class="flex items-center justify-between gap-3 rounded-lg border p-3 playlist-card surface-elevated"
            :class="isGroupSettingsAnchor(speaker.ip) ? 'opacity-80' : ''"
          >
            <div class="min-w-0">
              <div class="flex items-center gap-2">
                <span class="truncate text-sm font-medium">{{ speaker.name }}</span>
                <UBadge
                  v-if="isGroupSettingsAnchor(speaker.ip)"
                  label="Selected speaker"
                  color="neutral"
                  variant="soft"
                />
                <span v-else-if="groupSettingsPendingIp === speaker.ip" class="text-xs text-muted">Updating...</span>
              </div>
              <div class="mt-1 truncate text-xs text-muted">{{ speaker.ip }}</div>
            </div>

            <input
              type="checkbox"
              class="h-4 w-4 shrink-0 accent-primary-500"
              :checked="isGroupSpeakerChecked(speaker.ip)"
              :disabled="isGroupSettingsRowDisabled(speaker.ip)"
              @change="onGroupSettingChange(speaker, $event.target.checked)"
            />
          </label>
        </div>

        <p v-if="groupSettingsBusy" class="mt-3 text-xs text-muted">Updating speaker group...</p>

        <div class="mt-4 flex justify-end gap-2">
          <UButton type="button" color="neutral" variant="ghost" @click="groupSettingsOpen = false">
            Close
          </UButton>
        </div>
      </div>
    </template>
  </UModal>

  <UModal v-model:open="speakerSettingsOpen" :ui="{ width: 'max-w-lg' }">
    <template #content>
      <div class="flex max-h-[min(80vh,36rem)] flex-col p-4">
        <h3 class="shrink-0 text-lg font-semibold">Speaker settings</h3>
        <p class="mt-1 shrink-0 text-sm text-muted">
          {{ speakerSettingsTitleName }}
          <span v-if="speakerSettingsSpeakerIp">({{ speakerSettingsSpeakerIp }})</span>
        </p>

        <div v-if="speakerSettingsLoading" class="mt-6 text-sm text-muted">
          Loading settings…
        </div>
        <p v-else-if="speakerSettingsLoadError" class="mt-6 text-sm text-red-400">
          {{ speakerSettingsLoadError }}
        </p>
        <ul
          v-else-if="visibleSonosSettings.length"
          class="mt-4 min-h-0 flex-1 space-y-1 overflow-y-auto pr-1"
        >
          <li
            v-for="row in visibleSonosSettings"
            :key="row.key"
            class="flex items-center gap-3 rounded-lg border border-neutral-700/80 px-3 py-2.5 playlist-card surface-elevated"
          >
            <UIcon
              :name="row.icon"
              class="size-5 shrink-0"
              :class="
                row.iconAccentWhenOn && speakerSettingsLocal[row.key] === true
                  ? 'text-amber-400'
                  : 'text-neutral-300'
              "
            />
            <div class="min-w-0 flex-1 text-sm font-medium leading-tight">
              {{ row.label }}
            </div>

            <template v-if="row.type === 'readonly'">
              <span class="shrink-0 text-sm tabular-nums text-neutral-200">
                {{ sonosReadonlyDisplay(row) }}
              </span>
            </template>
            <template v-else-if="row.type === 'boolean'">
              <input
                type="checkbox"
                role="switch"
                class="h-6 w-11 shrink-0 cursor-pointer appearance-none rounded-full border border-neutral-600 bg-neutral-700 transition-colors checked:border-primary-500 checked:bg-primary-600 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-500"
                :checked="speakerSettingsLocal[row.key]"
                :aria-label="row.label"
                @change="onSonosBoolChange(row.key, $event.target.checked)"
              />
            </template>
            <template v-else>
              <div class="flex min-w-0 max-w-[14rem] flex-1 items-center gap-2 sm:max-w-[18rem]">
                <USlider
                  class="min-w-0 flex-1"
                  :model-value="speakerSettingsLocal[row.key]"
                  :min="row.min"
                  :max="row.max"
                  color="primary"
                  size="sm"
                  @update:model-value="onSonosSliderChange(row, $event)"
                />
                <span class="w-8 shrink-0 text-right text-sm tabular-nums text-muted">
                  {{ speakerSettingsLocal[row.key] }}
                </span>
              </div>
            </template>
          </li>
        </ul>
        <p v-else class="mt-6 text-sm text-muted">
          No adjustable settings are available for this speaker.
        </p>

        <div class="mt-4 flex shrink-0 justify-end gap-2 border-t border-neutral-700/60 pt-4">
          <UButton type="button" color="neutral" variant="ghost" @click="speakerSettingsOpen = false">
            Close
          </UButton>
        </div>
      </div>
    </template>
  </UModal>
</template>

<script setup>
import { computed, onUnmounted, ref, watch } from "vue";

import { useBreakpoint } from "../composables/useBreakpoint";
import { debounce } from "../composables/useDebounce";
import { useNotifications } from "../composables/useNotifications";
import { useSonosState } from "../composables/useSonosState";
import { MOBILE_VIEW_SONOS, SIDEBAR_SONOS_VIEW, useUiState } from "../composables/useUiState";


/** Display order and control metadata for Sonos settings modal (keys match API). */
const SONOS_SETTINGS = [
  { key: "balance", label: "Balance", icon: "i-bi-sliders", type: "slider", min: -100, max: 100 },
  { key: "bass", label: "Bass", icon: "i-bi-sliders", type: "slider", min: -10, max: 10 },
  { key: "cross_fade", label: "Crossfade", icon: "i-bi-shuffle", type: "boolean" },
  { key: "loudness", label: "Loudness", icon: "i-bi-megaphone-fill", type: "boolean", iconAccentWhenOn: true },
  { key: "mic_enabled", label: "Microphone", icon: "i-bi-mic-fill", type: "readonly", readonlyVariant: "boolean" },
  { key: "music_surround_level", label: "Music surround level", icon: "i-bi-music-note-beamed", type: "slider", min: -15, max: 15 },
  { key: "night_mode", label: "Night sound", icon: "i-bi-moon-stars-fill", type: "boolean" },
  { key: "speech_enhancement", label: "Speech enhancement", icon: "i-bi-chat-square-text-fill", type: "boolean" },
  { key: "sub_enabled", label: "Subwoofer", icon: "i-bi-speaker-fill", type: "boolean", iconAccentWhenOn: true },
  { key: "sub_gain", label: "Subwoofer level", icon: "i-bi-sliders", type: "slider", min: -15, max: 15 },
  { key: "surround_enabled", label: "Surround audio", icon: "i-bi-broadcast", type: "boolean", iconAccentWhenOn: true },
  { key: "surround_level", label: "Surround level", icon: "i-bi-sliders", type: "slider", min: -15, max: 15 },
  { key: "surround_full_volume_enabled", label: "Surround music full volume", icon: "i-bi-music-note", type: "boolean" },
  { key: "treble", label: "Treble", icon: "i-bi-sliders", type: "slider", min: -10, max: 10 },
  { key: "audio_delay", label: "Audio delay", icon: "i-bi-clock-history", type: "slider", min: 0, max: 5 },
  { key: "audio_input_format", label: "Audio input format", icon: "i-bi-hdmi", type: "readonly", readonlyVariant: "string" },
];

const SONOS_SLIDER_DEBOUNCE_MS = 420;
const VOLUME_SLIDER_DEBOUNCE_MS = 420;

const volumePresets = [
  { label: "Mute", value: 0 },
  { label: "10%", value: 10 },
  { label: "30%", value: 30 },
  { label: "75%", value: 75 },
];

const {
  speakers,
  refreshSonosManual,
  setSonosAutoRefreshEnabled,
  playOnSpeaker,
  stopOnSpeaker,
  groupSpeaker,
  ungroupSpeaker,
  setSpeakerVolume,
  previewSonosVolumes,
  commitSpeakerVolume,
  loadSpeakerSettings,
  updateSpeakerSetting,
} = useSonosState();
const { notifyError } = useNotifications();
const { isMobile } = useBreakpoint();
const { sidebarView, mobileView } = useUiState();

const expandedSpeakerIps = ref({});
const linkedVolumeSpeakerIps = ref({});
const groupSettingsOpen = ref(false);
const groupSettingsAnchorIp = ref("");
const groupSettingsSelection = ref({});
const groupSettingsBusy = ref(false);
const groupSettingsPendingIp = ref("");
const speakerSettingsOpen = ref(false);
const speakerSettingsSpeakerIp = ref("");
const speakerSettingsLoading = ref(false);
const speakerSettingsLoadError = ref("");
const speakerSettingsLocal = ref(null);
const speakerSettingsMetaName = ref("");
const sliderDebouncers = new Map();
const volumeDebouncers = new Map();

const groupedSpeakers = computed(() => (
  sortedSpeakers.value.filter((speaker) => speaker.is_coordinator)
));

const sortedSpeakers = computed(() => (
  [...speakers.value].sort((left, right) => (
    left.name.localeCompare(right.name, undefined, { sensitivity: "base" }) || left.ip.localeCompare(right.ip)
  ))
));

const groupSettingsAnchorSpeaker = computed(() => (
  sortedSpeakers.value.find((speaker) => speaker.ip === groupSettingsAnchorIp.value) ?? null
));

const speakerSettingsTarget = computed(() => (
  sortedSpeakers.value.find((speaker) => speaker.ip === speakerSettingsSpeakerIp.value) ?? null
));

const speakerSettingsTitleName = computed(() => (
  speakerSettingsMetaName.value || speakerSettingsTarget.value?.name || "Speaker"
));

const visibleSonosSettings = computed(() => {
  const local = speakerSettingsLocal.value;
  if (!local) {
    return [];
  }
  return SONOS_SETTINGS.filter((row) => local[row.key] !== null && local[row.key] !== undefined);
});

const isPanelVisible = computed(() => (
  isMobile.value ? mobileView.value === MOBILE_VIEW_SONOS : sidebarView.value === SIDEBAR_SONOS_VIEW
));

watch(isPanelVisible, (visible) => {
  void setSonosAutoRefreshEnabled(visible);
}, { immediate: true });

watch(groupSettingsOpen, (open) => {
  if (open) return;
  groupSettingsAnchorIp.value = "";
  groupSettingsSelection.value = {};
  groupSettingsBusy.value = false;
  groupSettingsPendingIp.value = "";
});

watch(speakerSettingsOpen, (open) => {
  if (open) return;
  speakerSettingsSpeakerIp.value = "";
  speakerSettingsLoading.value = false;
  speakerSettingsLoadError.value = "";
  speakerSettingsLocal.value = null;
  speakerSettingsMetaName.value = "";
  sliderDebouncers.clear();
});

watch([speakerSettingsOpen, speakerSettingsSpeakerIp], async ([open, ip]) => {
  if (!open || !ip) {
    return;
  }
  speakerSettingsLoading.value = true;
  speakerSettingsLoadError.value = "";
  try {
    const data = await loadSpeakerSettings(ip);
    speakerSettingsMetaName.value = data.speaker_name || "";
    speakerSettingsLocal.value = { ...data.settings };
  } catch (error) {
    speakerSettingsLoadError.value = error?.message || "Could not load settings";
    speakerSettingsLocal.value = null;
  } finally {
    speakerSettingsLoading.value = false;
  }
});

onUnmounted(() => {
  stopPanelRefresh();
  volumeDebouncers.clear();
});

function stopPanelRefresh() {
  void setSonosAutoRefreshEnabled(false);
}

function toggleSpeakerExpanded(ip) {
  expandedSpeakerIps.value = {
    ...expandedSpeakerIps.value,
    [ip]: !expandedSpeakerIps.value[ip],
  };
}

function isSpeakerExpanded(ip) {
  return !!expandedSpeakerIps.value[ip];
}

function hasLinkedVolumeControl(speaker) {
  return speakerGroupMembers(speaker).length > 1;
}

function isGroupVolumeLinked(ip) {
  return !!linkedVolumeSpeakerIps.value[ip];
}

function setGroupVolumeLinked(ip, linked) {
  linkedVolumeSpeakerIps.value = {
    ...linkedVolumeSpeakerIps.value,
    [ip]: !!linked,
  };
}

function clampSonosVolume(rawVolume) {
  const volume = Array.isArray(rawVolume) ? Number(rawVolume[0] ?? 0) : Number(rawVolume ?? 0);
  const clampedVolume = Math.max(0, Math.min(100, volume));
  return Number.isFinite(clampedVolume) ? clampedVolume : null;
}

function volumeSliderDebounceKey(speaker, memberIp) {
  return isGroupVolumeLinked(speaker.ip) ? `linked:${speaker.ip}` : `vol:${memberIp}`;
}

function getVolumeSliderDebouncer(speaker, memberIp) {
  const key = volumeSliderDebounceKey(speaker, memberIp);
  if (!volumeDebouncers.has(key)) {
    volumeDebouncers.set(
      key,
      debounce((targetIps, vol) => {
        void Promise.all(targetIps.map((ip) => commitSpeakerVolume({ ip, volume: vol })));
      }, VOLUME_SLIDER_DEBOUNCE_MS),
    );
  }
  return volumeDebouncers.get(key);
}

function onVolumeSliderInput(speaker, memberIp, rawVolume) {
  const clampedVolume = clampSonosVolume(rawVolume);
  if (clampedVolume === null) {
    return;
  }
  const targetIps = isGroupVolumeLinked(speaker.ip)
    ? speakerGroupMembers(speaker).map((m) => m.ip)
    : [memberIp];
  previewSonosVolumes(targetIps, clampedVolume);
  getVolumeSliderDebouncer(speaker, memberIp)(targetIps, clampedVolume);
}

async function updateSpeakerVolume(speaker, memberIp, rawVolume) {
  const clampedVolume = clampSonosVolume(rawVolume);
  if (clampedVolume === null) {
    return;
  }

  if (!isGroupVolumeLinked(speaker.ip)) {
    await setSpeakerVolume({ ip: memberIp, volume: clampedVolume });
    return;
  }

  const groupMembers = speakerGroupMembers(speaker);
  await Promise.all(groupMembers.map((member) => setSpeakerVolume({ ip: member.ip, volume: clampedVolume })));
}

function isSpeakerGroupedUnderAnotherCoordinator(speaker) {
  return !!(speaker?.coordinator_uid && speaker?.uid && speaker.coordinator_uid !== speaker.uid);
}

function buildGroupSelection(anchorSpeaker, options = {}) {
  const selection = {};
  for (const speaker of speakers.value) {
    selection[speaker.ip] = false;
  }

  if (!anchorSpeaker?.ip) {
    return selection;
  }

  selection[anchorSpeaker.ip] = true;

  if (options.reanchorIfNeeded && isSpeakerGroupedUnderAnotherCoordinator(anchorSpeaker)) {
    return selection;
  }

  const memberUids = new Set(Array.isArray(anchorSpeaker.group_member_uids) ? anchorSpeaker.group_member_uids : []);
  if (!memberUids.size && anchorSpeaker.uid) {
    memberUids.add(anchorSpeaker.uid);
  }

  for (const speaker of speakers.value) {
    if (speaker.ip === anchorSpeaker.ip || memberUids.has(speaker.uid)) {
      selection[speaker.ip] = true;
    }
  }

  return selection;
}

function openGroupSettings(speaker) {
  groupSettingsAnchorIp.value = speaker.ip;
  groupSettingsSelection.value = buildGroupSelection(speaker, { reanchorIfNeeded: true });
  groupSettingsBusy.value = false;
  groupSettingsPendingIp.value = "";
  groupSettingsOpen.value = true;
}

function openSpeakerSettings(speaker) {
  speakerSettingsSpeakerIp.value = speaker.ip;
  speakerSettingsOpen.value = true;
}

function sonosReadonlyDisplay(row) {
  const local = speakerSettingsLocal.value;
  if (!local) {
    return "—";
  }
  const v = local[row.key];
  if (row.readonlyVariant === "boolean") {
    return v ? "On" : "Off";
  }
  return v === null || v === undefined || v === "" ? "—" : String(v);
}

function getSonosSliderDebouncer(key) {
  if (!sliderDebouncers.has(key)) {
    sliderDebouncers.set(
      key,
      debounce((targetIp, setting, value) => {
        void commitSonosSliderWrite(targetIp, setting, value);
      }, SONOS_SLIDER_DEBOUNCE_MS),
    );
  }
  return sliderDebouncers.get(key);
}

async function commitSonosSliderWrite(ip, setting, value) {
  if (!ip || ip !== speakerSettingsSpeakerIp.value || !speakerSettingsLocal.value) {
    return;
  }
  const before = { ...speakerSettingsLocal.value };
  try {
    const res = await updateSpeakerSetting(ip, setting, value);
    if (res && typeof res.value !== "undefined" && res.value !== null) {
      speakerSettingsLocal.value = {
        ...speakerSettingsLocal.value,
        [setting]: res.value,
      };
    }
  } catch (error) {
    speakerSettingsLocal.value = before;
    notifyError("Could not update speaker setting", error);
    try {
      const data = await loadSpeakerSettings(ip);
      speakerSettingsLocal.value = { ...data.settings };
      speakerSettingsMetaName.value = data.speaker_name || speakerSettingsMetaName.value;
    } catch {
      /* ignore */
    }
  }
}

function onSonosSliderChange(row, raw) {
  if (!speakerSettingsLocal.value || row.type !== "slider") {
    return;
  }
  const n = Array.isArray(raw) ? Number(raw[0]) : Number(raw);
  if (!Number.isFinite(n)) {
    return;
  }
  const clamped = Math.round(Math.max(row.min, Math.min(row.max, n)));
  speakerSettingsLocal.value = {
    ...speakerSettingsLocal.value,
    [row.key]: clamped,
  };
  getSonosSliderDebouncer(row.key)(speakerSettingsSpeakerIp.value, row.key, clamped);
}

async function onSonosBoolChange(key, checked) {
  const ip = speakerSettingsSpeakerIp.value;
  if (!ip || !speakerSettingsLocal.value) {
    return;
  }
  const before = speakerSettingsLocal.value[key];
  speakerSettingsLocal.value = {
    ...speakerSettingsLocal.value,
    [key]: !!checked,
  };
  try {
    await updateSpeakerSetting(ip, key, !!checked);
  } catch (error) {
    speakerSettingsLocal.value = {
      ...speakerSettingsLocal.value,
      [key]: before,
    };
    notifyError("Could not update speaker setting", error);
    try {
      const data = await loadSpeakerSettings(ip);
      speakerSettingsLocal.value = { ...data.settings };
      speakerSettingsMetaName.value = data.speaker_name || speakerSettingsMetaName.value;
    } catch {
      /* ignore */
    }
  }
}

function speakerMenuItems(speaker) {
  return [
    {
      label: "Group settings",
      icon: "i-bi-collection-fill",
      class: "cursor-pointer",
      onSelect: () => openGroupSettings(speaker),
    },
    {
      label: "Speaker settings",
      icon: "i-bi-gear-fill",
      class: "cursor-pointer",
      onSelect: () => openSpeakerSettings(speaker),
    },
  ];
}

function speakerGroupMembers(speaker) {
  if (Array.isArray(speaker?.group_members) && speaker.group_members.length > 0) {
    return speaker.group_members;
  }
  return speakers.value.filter((candidate) => speaker?.group_member_uids?.includes(candidate.uid));
}

function speakerGroupSummary(speaker) {
  const groupMembers = speakerGroupMembers(speaker);
  if (groupMembers.length > 1) {
    return `${groupMembers.length} speakers in group`;
  }
  return "Standalone speaker";
}

function isGroupSettingsAnchor(ip) {
  return ip === groupSettingsAnchorIp.value;
}

function isGroupSpeakerChecked(ip) {
  return !!groupSettingsSelection.value[ip];
}

function isGroupSettingsRowDisabled(ip) {
  return groupSettingsBusy.value || isGroupSettingsAnchor(ip);
}

function syncGroupSelectionToAnchor() {
  groupSettingsSelection.value = buildGroupSelection(groupSettingsAnchorSpeaker.value);
}

async function onGroupSettingChange(speaker, checked) {
  const anchorSpeaker = groupSettingsAnchorSpeaker.value;
  if (!anchorSpeaker || speaker.ip === anchorSpeaker.ip || groupSettingsBusy.value) {
    return;
  }

  groupSettingsBusy.value = true;
  groupSettingsPendingIp.value = speaker.ip;

  let ok = true;

  if (checked) {
    if (isSpeakerGroupedUnderAnotherCoordinator(anchorSpeaker)) {
      ok = await ungroupSpeaker(anchorSpeaker.ip, { notifySuccessMessage: false });
    }
    if (ok) {
      ok = await groupSpeaker({ coordinatorIp: anchorSpeaker.ip, memberIp: speaker.ip });
    }
  } else {
    ok = await ungroupSpeaker(speaker.ip);
  }

  if (ok) {
    syncGroupSelectionToAnchor();
  }

  groupSettingsBusy.value = false;
  groupSettingsPendingIp.value = "";
}
</script>
