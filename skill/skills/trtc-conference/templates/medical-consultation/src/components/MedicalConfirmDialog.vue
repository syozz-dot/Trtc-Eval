<script setup lang="ts">
import { computed } from 'vue';
import { useUIKit } from '@tencentcloud/uikit-base-component-vue3';
import MedicalButton from '@/components/MedicalButton.vue';

const props = withDefaults(
  defineProps<{
    visible: boolean;
    title: string;
    message: string;
    confirmText?: string;
    cancelText?: string;
    loading?: boolean;
    danger?: boolean;
  }>(),
  {
    loading: false,
    danger: false,
  }
);
const { t } = useUIKit();
const displayConfirmText = computed(
  () => props.confirmText || t('Medical.Common.Confirm')
);
const displayCancelText = computed(
  () => props.cancelText || t('Medical.Common.Cancel')
);

const emit = defineEmits<{
  cancel: [];
  confirm: [];
}>();
</script>

<template>
  <Teleport to="body">
    <div
      v-if="visible"
      class="fixed inset-0 z-[120] flex items-center justify-center bg-black/45 p-4"
      @click.self="emit('cancel')"
    >
      <div
        class="w-full max-w-[380px] rounded-3xl bg-card p-6 text-card-foreground shadow-[0_20px_60px_rgba(15,23,42,0.25)]"
      >
        <h3 class="text-lg font-semibold text-foreground">{{ title }}</h3>
        <p class="mt-3 text-sm leading-6 text-muted-foreground">
          {{ message }}
        </p>
        <div class="mt-6 grid grid-cols-2 gap-3">
          <MedicalButton
            variant="outline"
            :disabled="loading"
            @click="emit('cancel')"
          >
            {{ displayCancelText }}
          </MedicalButton>
          <MedicalButton
            :variant="danger ? 'danger' : 'primary'"
            :loading="loading"
            @click="emit('confirm')"
          >
            {{ loading ? t('Medical.Common.Processing') : displayConfirmText }}
          </MedicalButton>
        </div>
      </div>
    </div>
  </Teleport>
</template>
