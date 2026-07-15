<script setup lang="ts">
import { Check, ChevronDown, Languages } from 'lucide-vue-next';
import { useUIKit } from '@tencentcloud/uikit-base-component-vue3';
import { computed, onBeforeUnmount, ref } from 'vue';
import {
  medicalLanguage,
  setMedicalLanguage,
  type MedicalLanguage,
} from '@/i18n/state';

const menuVisible = ref(false);
const rootRef = ref<HTMLElement | null>(null);
const { t } = useUIKit();

const languageOptions: Array<{
  labelKey: string;
  shortLabel: string;
  value: MedicalLanguage;
}> = [
  { labelKey: 'Medical.Language.Chinese', shortLabel: 'ZH', value: 'zh-CN' },
  { labelKey: 'Medical.Language.English', shortLabel: 'EN', value: 'en-US' },
];

const currentLanguage = computed(
  () =>
    languageOptions.find(item => item.value === medicalLanguage.value) ||
    languageOptions[0]
);

function toggleMenu() {
  menuVisible.value = !menuVisible.value;
}

function selectLanguage(language: MedicalLanguage) {
  setMedicalLanguage(language);
  menuVisible.value = false;
}

function handleDocumentClick(event: MouseEvent) {
  if (!rootRef.value?.contains(event.target as Node)) {
    menuVisible.value = false;
  }
}

function handleEscape(event: KeyboardEvent) {
  if (event.key === 'Escape') {
    menuVisible.value = false;
  }
}

document.addEventListener('click', handleDocumentClick);
document.addEventListener('keydown', handleEscape);

onBeforeUnmount(() => {
  document.removeEventListener('click', handleDocumentClick);
  document.removeEventListener('keydown', handleEscape);
});
</script>

<template>
  <div ref="rootRef" class="medical-language-selector">
    <button
      class="medical-language-trigger"
      type="button"
      aria-haspopup="menu"
      :aria-expanded="menuVisible"
      @click.stop="toggleMenu"
    >
      <Languages :size="15" />
      <span class="medical-language-current">
        {{ t(currentLanguage.labelKey) }}
      </span>
      <ChevronDown
        :size="14"
        :class="[
          'medical-language-chevron',
          menuVisible ? 'medical-language-chevron-open' : '',
        ]"
      />
    </button>

    <div v-if="menuVisible" class="medical-language-menu" role="menu">
      <button
        v-for="item in languageOptions"
        :key="item.value"
        class="medical-language-option"
        type="button"
        role="menuitemradio"
        :aria-checked="medicalLanguage === item.value"
        @click="selectLanguage(item.value)"
      >
        <span class="medical-language-option-badge">{{ item.shortLabel }}</span>
        <span>{{ t(item.labelKey) }}</span>
        <Check
          v-if="medicalLanguage === item.value"
          :size="15"
          class="medical-language-check"
        />
      </button>
    </div>
  </div>
</template>
