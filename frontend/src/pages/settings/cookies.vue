<template>
  <section class="min-h-0 h-full rounded-xl border border-neutral-700 p-6 surface-panel overflow-auto">
    <h2 class="text-2xl font-bold">Cookies</h2>
    <p class="mt-1 text-sm text-muted">
      Configure cookies for video providers to access age-restricted or region-locked content.
    </p>

    <div class="mt-6 space-y-6">
      <!-- YouTube Provider -->
      <div class="border border-neutral-700 rounded-lg p-4 bg-neutral-800/30">
        <div class="flex items-start justify-between">
          <div>
            <h3 class="text-lg font-semibold">YouTube</h3>
            <p class="text-sm text-muted mt-1">
              Provide cookies for age-restricted or login-required videos.
            </p>
          </div>
          <span
            v-if="cookies.youtube"
            class="px-2 py-1 text-xs font-medium bg-green-900/30 text-green-400 rounded"
          >
            Configured
          </span>
        </div>

        <div class="mt-4 space-y-3">
          <div v-if="!cookies.youtube || editingYoutube">
            <label class="block text-sm font-medium mb-2">Cookie Content</label>
            <p class="text-xs text-muted mb-2">
              Paste Netscape-format cookies or provide a path to a cookie file.
            </p>
            <textarea
              v-model="youtubeInput"
              class="w-full h-24 px-3 py-2 text-sm rounded-md border border-neutral-600 surface-input font-mono"
              placeholder="# Netscape HTTP Cookie File&#10;# This is a generated file!&#10;..."
            />
            <div class="mt-2 flex gap-2">
              <button
                @click="saveYoutubeCookies"
                :disabled="!youtubeInput || isSaving"
                class="px-3 py-1 text-sm font-medium rounded bg-blue-600 hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {{ isSaving ? "Saving..." : "Save" }}
              </button>
              <button
                v-if="editingYoutube"
                @click="cancelEdit"
                class="px-3 py-1 text-sm font-medium rounded border border-neutral-600 hover:bg-neutral-700"
              >
                Cancel
              </button>
            </div>
          </div>

          <div v-else class="flex gap-2">
            <button
              @click="editingYoutube = true"
              class="px-3 py-1 text-sm font-medium rounded border border-neutral-600 hover:bg-neutral-700"
            >
              Edit
            </button>
            <button
              @click="deleteYoutubeCookies"
              :disabled="isDeleting"
              class="px-3 py-1 text-sm font-medium rounded border border-neutral-600 hover:bg-red-900/30 hover:text-red-400 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {{ isDeleting ? "Deleting..." : "Delete" }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <div class="mt-8 p-4 bg-neutral-800/30 rounded-lg border border-neutral-700">
      <h4 class="text-sm font-semibold">How to get cookies</h4>
      <ol class="text-xs text-muted mt-2 space-y-1 list-decimal list-inside">
        <li>Use a tool like <code class="bg-neutral-900 px-1">yt-dlp --cookies-from-browser chrome</code> to extract cookies</li>
        <li>Convert to Netscape format if needed</li>
        <li>Paste the content above or provide the file path</li>
      </ol>
    </div>
  </section>
</template>

<script setup>
import { ref, onMounted } from "vue";
import { fetchJson } from "../../composables/useApi.js";

const editingYoutube = ref(false);
const youtubeInput = ref("");
const isSaving = ref(false);
const isDeleting = ref(false);

const cookies = ref({
  youtube: false,
});

async function loadCookiesStatus() {
  try {
    const response = await fetchJson("/api/cookies");
    cookies.value = {
      youtube: !!response.cookies?.youtube,
    };
  } catch (error) {
    console.error("Failed to load cookies status:", error);
  }
}

async function saveYoutubeCookies() {
  isSaving.value = true;
  try {
    const response = await fetchJson("/api/cookies/youtube", {
      method: "POST",
      body: JSON.stringify({ cookie_value: youtubeInput.value }),
    });
    if (response.ok) {
      cookies.value.youtube = true;
      editingYoutube.value = false;
      youtubeInput.value = "";
    }
  } catch (error) {
    console.error("Failed to save YouTube cookies:", error);
    alert("Failed to save cookies. Check console for details.");
  } finally {
    isSaving.value = false;
  }
}

async function deleteYoutubeCookies() {
  isDeleting.value = true;
  try {
    const response = await fetchJson("/api/cookies/youtube", {
      method: "DELETE",
    });
    if (response.ok) {
      cookies.value.youtube = false;
      youtubeInput.value = "";
      editingYoutube.value = false;
    }
  } catch (error) {
    console.error("Failed to delete YouTube cookies:", error);
    alert("Failed to delete cookies. Check console for details.");
  } finally {
    isDeleting.value = false;
  }
}

function cancelEdit() {
  editingYoutube.value = false;
  youtubeInput.value = "";
}

onMounted(() => {
  loadCookiesStatus();
});
</script>
