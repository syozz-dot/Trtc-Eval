import { ref } from 'vue';

export type MedicalLanguage = 'zh-CN' | 'en-US';

export const MEDICAL_LANGUAGE_STORAGE_KEY = 'tuiMedical-language';

export function normalizeMedicalLanguage(
  language?: string | null
): MedicalLanguage {
  if (!language) {
    return 'zh-CN';
  }
  const normalizedLanguage = language.toLowerCase();
  if (normalizedLanguage.startsWith('zh')) {
    return 'zh-CN';
  }
  if (normalizedLanguage.startsWith('en')) {
    return 'en-US';
  }
  return 'en-US';
}

function getBrowserLanguage() {
  const languages = navigator.languages?.length
    ? navigator.languages
    : [navigator.language];
  return (
    languages.find(language => /^zh/i.test(language)) ||
    languages.find(language => /^en/i.test(language)) ||
    navigator.userAgent.match(/\b(zh|en)(?:-|_)[a-z]{2}\b/i)?.[0] ||
    ''
  );
}

function getInitialLanguage(): MedicalLanguage {
  const queryLanguage = new URLSearchParams(window.location.search).get('lang');
  const storedLanguage = localStorage.getItem(MEDICAL_LANGUAGE_STORAGE_KEY);
  return normalizeMedicalLanguage(
    queryLanguage || storedLanguage || getBrowserLanguage()
  );
}

export const medicalLanguage = ref<MedicalLanguage>(getInitialLanguage());

export function setMedicalLanguage(language: MedicalLanguage) {
  medicalLanguage.value = language;
  localStorage.setItem(MEDICAL_LANGUAGE_STORAGE_KEY, language);
  document.documentElement.lang = language;
}
