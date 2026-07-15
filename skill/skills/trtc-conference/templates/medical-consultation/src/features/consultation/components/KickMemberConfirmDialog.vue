<script setup lang="ts">
import { useUIKit } from '@tencentcloud/uikit-base-component-vue3';
import LoadingSpinner from '@/components/LoadingSpinner.vue';

defineProps<{
  target: { userId: string; userName: string } | null;
  kickingUserId?: string | null;
}>();

const emit = defineEmits<{
  cancel: [];
  confirm: [];
}>();

const { t } = useUIKit();
</script>

<template>
  <div
    v-if="target"
    class="fixed inset-0 z-[110] bg-black/45 flex items-center justify-center p-4"
    @click.self="emit('cancel')"
  >
    <div
      class="w-full max-w-[360px] rounded-2xl bg-white shadow-[0_16px_40px_rgba(15,23,42,0.24)] p-5"
    >
      <h3 class="text-base font-semibold text-[#0F172A]">{{ t('Medical.Member.ConfirmKickTitle') }}</h3>
      <p class="mt-2 text-sm text-[#64748B] leading-6">
        {{ t('Medical.Member.ConfirmKickMessage', { userName: target.userName }) }}
      </p>
      <div class="mt-5 grid grid-cols-2 gap-3">
        <button
          @click="emit('cancel')"
          :disabled="!!kickingUserId"
          class="h-10 rounded-xl border border-[#E2E8F0] text-[#475569] font-medium disabled:opacity-60"
        >
          {{ t('Medical.Member.CancelButton') }}
        </button>
        <button
          @click="emit('confirm')"
          :disabled="!!kickingUserId"
          class="h-10 rounded-xl bg-red-500 text-white font-medium hover:bg-red-600 disabled:opacity-60"
        >
          <LoadingSpinner v-if="kickingUserId" class="mr-1" />
          {{ kickingUserId ? t('Medical.Member.ProcessingButton') : t('Medical.Member.ConfirmButton') }}
        </button>
      </div>
    </div>
  </div>
</template>
