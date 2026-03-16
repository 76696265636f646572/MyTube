<template>
  <div>
    <h2 class="text-2xl font-bold">Cookies</h2>
    <p class="mt-1 text-sm text-muted">
      Configure provider-specific cookie values for yt-dlp. You can paste Netscape cookie file content or a file path.
    </p>
    <p class="mt-2 text-sm text-muted">
      <a
        href="https://github.com/yt-dlp/yt-dlp/wiki/FAQ#how-do-i-pass-cookies-to-yt-dlp"
        target="_blank"
        rel="noopener noreferrer"
        class="text-primary hover:underline"
      >
        How to find and export cookies for yt-dlp
      </a>
    </p>

    <div v-if="loading" class="mt-6 text-sm text-muted">Loading...</div>
    <div v-else-if="loadError" class="mt-6 text-sm text-red-400">{{ loadError }}</div>

    <div v-else class="mt-6 space-y-4">
      <div
        v-for="entry in providerRows"
        :key="entry.provider"
        class="rounded-lg border border-neutral-700 p-4 surface-panel"
      >
        <div class="flex items-center justify-between gap-3">
          <div>
            <h3 class="text-base font-semibold">{{ entry.label }}</h3>
            <p class="text-xs text-muted">
              {{ entry.configured ? "Cookie value is configured." : "No cookie value configured." }}
            </p>
          </div>
          <UButton
            v-if="entry.configured"
            variant="ghost"
            color="neutral"
            size="sm"
            :loading="resettingProvider === entry.provider"
            @click="resetProvider(entry.provider)"
          >
            Reset
          </UButton>
        </div>

        <label :for="`cookies-${entry.provider}`" class="mt-3 block text-sm font-medium">
          Cookie value or cookie file path
        </label>
        <textarea
          :id="`cookies-${entry.provider}`"
          v-model="draftValues[entry.provider]"
          rows="6"
          class="mt-2 w-full rounded-md border p-3 text-sm surface-input"
          :placeholder="placeholderFor(entry.provider)"
        />

        <div class="mt-3 flex items-center justify-between gap-3">
          <p class="text-xs text-muted">Values are stored server-side and never returned to this page.</p>
          <UButton
            size="sm"
            :loading="savingProvider === entry.provider"
            :disabled="!canSave(entry.provider)"
            @click="saveProvider(entry.provider)"
          >
            Save
          </UButton>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";
import { fetchJson } from "../../composables/useApi";

const providers = ref([]);
const loading = ref(true);
const loadError = ref("");
const draftValues = ref({});
const savingProvider = ref("");
const resettingProvider = ref("");

const providerRows = computed(() => providers.value || []);

function placeholderFor(provider) {
  return `# Netscape HTTP Cookie File\n# or /path/to/${provider}-cookies.txt`;
}

function canSave(provider) {
  const value = draftValues.value[provider];
  return typeof value === "string" && value.trim().length > 0;
}

async function load() {
  loading.value = true;
  loadError.value = "";
  try {
    const response = await fetchJson("/api/settings/cookies");
    providers.value = response.providers || [];
    const nextDrafts = {};
    for (const providerInfo of providers.value) {
      nextDrafts[providerInfo.provider] = "";
    }
    draftValues.value = nextDrafts;
  } catch (e) {
    loadError.value = e?.message || "Failed to load cookie settings.";
  } finally {
    loading.value = false;
  }
}

async function saveProvider(provider) {
  if (!canSave(provider)) return;
  savingProvider.value = provider;
  loadError.value = "";
  try {
    await fetchJson("/api/settings/cookies", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        provider,
        value: draftValues.value[provider],
      }),
    });
    draftValues.value[provider] = "";
    await load();
  } catch (e) {
    loadError.value = e?.message || `Failed to save ${provider} cookies.`;
  } finally {
    savingProvider.value = "";
  }
}

async function resetProvider(provider) {
  resettingProvider.value = provider;
  loadError.value = "";
  try {
    await fetchJson(`/api/settings/cookies/${encodeURIComponent(provider)}`, {
      method: "DELETE",
    });
    draftValues.value[provider] = "";
    await load();
  } catch (e) {
    loadError.value = e?.message || `Failed to reset ${provider} cookies.`;
  } finally {
    resettingProvider.value = "";
  }
}

onMounted(load);
</script>
