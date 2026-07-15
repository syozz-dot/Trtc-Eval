<script setup lang="ts">
import { watch } from 'vue';
import { UIKitProvider } from '@tencentcloud/uikit-base-component-vue3';
import { medicalLanguage } from '@/i18n/state';
import { initMedicalI18n } from '@/i18n';

initMedicalI18n();

watch(
  medicalLanguage,
  () => {
    document.documentElement.lang = medicalLanguage.value;
  },
  { immediate: true }
);
</script>

<template>
  <UIKitProvider
    :theme="{ themeStyle: 'light', primaryColor: 'theme' }"
    :language="medicalLanguage"
  >
    <router-view />
  </UIKitProvider>
</template>
