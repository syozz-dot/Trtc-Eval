<template>
  <div class="h-full flex flex-col bg-white">
    <div class="p-6 border-b border-gray-100 shrink-0">
      <div class="flex items-center justify-between mb-4">
        <div>
          <h3 class="font-semibold text-gray-900 flex items-center gap-2">
            <FolderOpen :size="20" class="text-[#0D9488]" />
            {{ t('Medical.Data.Title') }}
          </h3>
          <p class="text-xs text-gray-500 mt-1">
            {{ t('Medical.Data.Description') }}
          </p>
        </div>
        <span
          class="px-3 py-1 rounded-full text-xs font-medium bg-gray-100 text-gray-700"
        >
          {{ t('Medical.Data.FileCount', { count: files.length }) }}
        </span>
      </div>

      <div class="bg-[#F1F5F9] rounded-xl p-3 text-sm">
        <div class="flex items-center justify-between">
          <span class="text-gray-600">
            {{ t('Medical.Record.PatientLabel') }}
            <span class="font-medium text-gray-900 ml-1">
              {{ patientInfo.name }} ·
              {{ t('Medical.DoctorDashboard.PatientAge', {
                gender: patientInfo.gender,
                age: patientInfo.age,
              }) }}
            </span>
          </span>
        </div>
      </div>
    </div>

    <div class="px-6 pt-5 pb-4 border-b border-gray-100 bg-gray-50 shrink-0">
      <button
        class="w-full border-2 border-dashed border-gray-300 rounded-xl p-4 hover:border-[#0D9488] hover:bg-[#0D9488]/5 transition-all flex flex-col items-center gap-2 text-gray-600 hover:text-[#0D9488]"
      >
        <Upload :size="24" />
        <div class="text-sm font-medium">{{ t('Medical.Data.Upload') }}</div>
        <div class="text-xs text-gray-500">
          {{ t('Medical.Data.UploadHint') }}
        </div>
      </button>
    </div>

    <div class="flex-1 overflow-y-auto px-6 py-5 space-y-3 custom-scrollbar">
      <div
        v-for="file in files"
        :key="file.id"
        class="border border-gray-200 rounded-2xl p-4 hover:shadow-md hover:border-[#0D9488]/30 transition-all duration-200 bg-white group"
      >
        <div class="flex items-start gap-4">
          <div
            :class="[
              'w-16 h-16 rounded-xl flex items-center justify-center shrink-0',
              file.type === 'image' ? 'bg-blue-50' : 'bg-orange-50',
            ]"
          >
            <component
              :is="file.type === 'image' ? ImageIcon : FileText"
              :size="28"
              :class="
                file.type === 'image' ? 'text-blue-600' : 'text-orange-600'
              "
            />
          </div>

          <div class="flex-1 min-w-0">
            <div class="flex items-start justify-between gap-2 mb-2">
              <h4 class="font-medium text-gray-900 text-sm truncate">
                {{ file.name }}
              </h4>
              <button
                class="p-1.5 hover:bg-gray-100 rounded-lg transition-colors opacity-0 group-hover:opacity-100 shrink-0"
              >
                <MoreVertical :size="16" class="text-gray-500" />
              </button>
            </div>

            <div class="flex items-center gap-4 text-xs text-gray-500 mb-3">
              <span>{{ file.size }}</span>
              <span>{{ file.date }}</span>
              <span
                :class="[
                  'px-2 py-0.5 rounded-full font-medium',
                  file.categoryKey === 'BloodRoutine'
                    ? 'bg-red-100 text-red-700'
                    : file.categoryKey === 'CTImage'
                      ? 'bg-blue-100 text-blue-700'
                      : file.categoryKey === 'XRay'
                        ? 'bg-purple-100 text-purple-700'
                        : 'bg-green-100 text-green-700',
                ]"
              >
                {{ file.category }}
              </span>
            </div>

            <div class="flex gap-2">
              <button
                class="px-3 py-1.5 bg-[#0D9488] hover:bg-[#0F766E] text-white rounded-lg text-xs font-medium transition-colors flex items-center gap-1"
              >
                <Eye :size="14" />
                {{ t('Medical.Common.View') }}
              </button>
              <button
                class="px-3 py-1.5 border border-gray-200 hover:bg-gray-50 rounded-lg text-xs font-medium transition-colors flex items-center gap-1"
              >
                <Download :size="14" />
                {{ t('Medical.Common.Download') }}
              </button>
            </div>
          </div>
        </div>
      </div>

      <div v-if="files.length === 0" class="text-center py-12">
        <div
          class="w-20 h-20 rounded-full bg-gray-100 mx-auto flex items-center justify-center mb-4"
        >
          <FolderOpen :size="32" class="text-gray-400" />
        </div>
        <p class="text-sm text-gray-500 mb-2">
          {{ t('Medical.Data.EmptyTitle') }}
        </p>
        <p class="text-xs text-gray-400">{{ t('Medical.Data.EmptyDesc') }}</p>
      </div>
    </div>

    <div class="p-6 border-t border-gray-100 shrink-0 bg-gray-50">
      <div class="flex items-start gap-2 text-xs text-gray-500">
        <AlertCircle :size="12" class="mt-0.5 shrink-0" />
        <p>{{ t('Medical.Data.SecurityTip') }}</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useUIKit } from '@tencentcloud/uikit-base-component-vue3';
import {
  AlertCircle,
  Download,
  Eye,
  FileText,
  FolderOpen,
  ImageIcon,
  MoreVertical,
  Upload,
} from '@/shared/icons';

interface PatientInfo {
  name: string;
  age: number;
  gender: string;
}

defineProps<{
  patientInfo: PatientInfo;
}>();
const { t } = useUIKit();

const files = computed(() => [
  {
    id: '1',
    name: t('Medical.Data.BloodRoutineReport'),
    type: 'pdf',
    size: '2.3 MB',
    date: '2026-04-15',
    category: t('Medical.Data.BloodRoutine'),
    categoryKey: 'BloodRoutine',
  },
  {
    id: '2',
    name: t('Medical.Data.ChestCTImage'),
    type: 'image',
    size: '5.1 MB',
    date: '2026-04-14',
    category: t('Medical.Data.CTImage'),
    categoryKey: 'CTImage',
  },
  {
    id: '3',
    name: t('Medical.Data.ECGReport'),
    type: 'pdf',
    size: '1.8 MB',
    date: '2026-04-13',
    category: t('Medical.Data.ECG'),
    categoryKey: 'ECG',
  },
]);
</script>
