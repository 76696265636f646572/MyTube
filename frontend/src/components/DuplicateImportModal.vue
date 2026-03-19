<template>
  <UModal v-model:open="open" :ui="{ width: 'max-w-sm' }">
    <template #content>
      <div class="p-4">
        <h3 class="text-lg font-semibold">Some already added</h3>
        <p class="mt-2 text-sm text-muted">
          Some of these are already in your '{{ targetPlaylistTitle }}' playlist.
        </p>
        <div class="mt-4 flex justify-end gap-2">
          <UButton type="button" color="neutral" variant="ghost" @click="handleAddAll">
            Add all
          </UButton>
          <UButton type="button" color="primary" variant="solid" :ui="{ rounded: 'rounded-full' }" @click="handleAddNewOnes">
            Add new ones
          </UButton>
        </div>
      </div>
    </template>
  </UModal>
</template>

<script setup>
import { useDuplicateModal } from "../composables/useDuplicateModal";

const { open, targetPlaylistTitle, handleAddAll, handleAddNewOnes } = useDuplicateModal();
</script>
