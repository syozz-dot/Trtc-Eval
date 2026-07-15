<template>
  <div class="h-full flex flex-col bg-white">
    <div class="p-6 border-b border-gray-100 shrink-0">
      <div class="flex items-center justify-between mb-4">
        <div>
          <h3 class="font-semibold text-gray-900 flex items-center gap-2">
            <FileText :size="20" class="text-[#0D9488]" />
            {{ t('Medical.Business.RecordTab') }}
          </h3>
          <p class="text-xs text-gray-500 mt-1">
            {{ t('Medical.Record.ReplaceDesc') }}
          </p>
        </div>
        <span
          class="px-3 py-1 rounded-full text-xs font-medium bg-green-100 text-green-700"
        >
          {{ t('Medical.Record.SlotExample') }}
        </span>
      </div>

      <div class="bg-[#F1F5F9] rounded-xl p-3 text-sm">
        <div class="flex items-center justify-between">
          <span class="text-gray-600">
            {{ t('Medical.Record.PatientLabel') }}
            <span class="font-medium text-gray-900 ml-1">
              {{ patientInfo.name }} ·
              {{ t('Medical.Consultation.PatientAge', { gender: patientInfo.gender, age: patientInfo.age }) }}
            </span>
          </span>
        </div>
      </div>
    </div>

    <div class="flex-1 overflow-y-auto px-6 py-6 space-y-6 custom-scrollbar">
      <div>
        <label class="block text-sm font-medium text-gray-700 mb-2">
          {{ t('Medical.Consultation.ChiefComplaint') }} <span class="text-red-500">*</span>
        </label>
        <textarea
          v-model="formData.chiefComplaint"
          :placeholder="t('Medical.Record.ChiefComplaintPlaceholder')"
          rows="3"
          class="w-full px-4 py-3 rounded-xl border border-gray-200 focus:border-[#0D9488] focus:outline-none focus:ring-2 focus:ring-[#0D9488]/20 resize-none"
        ></textarea>
      </div>

      <div>
        <label class="block text-sm font-medium text-gray-700 mb-2">
          {{ t('Medical.Record.PresentIllness') }} <span class="text-red-500">*</span>
        </label>
        <textarea
          v-model="formData.presentIllness"
          :placeholder="t('Medical.Record.PresentIllnessPlaceholder')"
          rows="4"
          class="w-full px-4 py-3 rounded-xl border border-gray-200 focus:border-[#0D9488] focus:outline-none focus:ring-2 focus:ring-[#0D9488]/20 resize-none"
        ></textarea>
      </div>

      <div>
        <label class="block text-sm font-medium text-gray-700 mb-2">{{ t('Medical.Record.PastHistory') }}</label>
        <textarea
          v-model="formData.pastHistory"
          :placeholder="t('Medical.Record.PastHistoryPlaceholder')"
          rows="2"
          class="w-full px-4 py-3 rounded-xl border border-gray-200 focus:border-[#0D9488] focus:outline-none focus:ring-2 focus:ring-[#0D9488]/20 resize-none"
        ></textarea>
      </div>

      <div>
        <label class="block text-sm font-medium text-gray-700 mb-2">
          {{ t('Medical.Consultation.AllergyHistory') }} <span class="text-red-500">*</span>
        </label>
        <input
          v-model="formData.allergyHistory"
          type="text"
          :placeholder="t('Medical.Record.AllergyPlaceholder')"
          class="w-full h-11 px-4 rounded-xl border border-gray-200 focus:border-[#0D9488] focus:outline-none focus:ring-2 focus:ring-[#0D9488]/20"
        />
      </div>

      <div>
        <label class="block text-sm font-medium text-gray-700 mb-2">{{ t('Medical.Record.PhysicalExam') }}</label>
        <div class="grid grid-cols-2 gap-3">
          <div>
            <label class="text-xs text-gray-600 mb-1 block">{{ t('Medical.Record.Temperature') }}</label>
            <input
              v-model="formData.temperature"
              type="text"
              placeholder="36.5"
              class="w-full h-9 px-3 rounded-xl border border-gray-200 focus:border-[#0D9488] focus:outline-none text-sm"
            />
          </div>
          <div>
            <label class="text-xs text-gray-600 mb-1 block">{{ t('Medical.Record.Pulse') }}</label>
            <input
              v-model="formData.pulse"
              type="text"
              placeholder="75"
              class="w-full h-9 px-3 rounded-xl border border-gray-200 focus:border-[#0D9488] focus:outline-none text-sm"
            />
          </div>
          <div>
            <label class="text-xs text-gray-600 mb-1 block">{{ t('Medical.Record.BloodPressure') }}</label>
            <input
              v-model="formData.bloodPressure"
              type="text"
              placeholder="120/80"
              class="w-full h-9 px-3 rounded-xl border border-gray-200 focus:border-[#0D9488] focus:outline-none text-sm"
            />
          </div>
          <div>
            <label class="text-xs text-gray-600 mb-1 block">{{ t('Medical.Record.Respiration') }}</label>
            <input
              v-model="formData.respiration"
              type="text"
              placeholder="18"
              class="w-full h-9 px-3 rounded-xl border border-gray-200 focus:border-[#0D9488] focus:outline-none text-sm"
            />
          </div>
        </div>
      </div>

      <div>
        <label class="block text-sm font-medium text-gray-700 mb-2">{{ t('Medical.Record.AuxiliaryExam') }}</label>
        <textarea
          v-model="formData.auxiliaryExam"
          :placeholder="t('Medical.Record.AuxiliaryExamPlaceholder')"
          rows="3"
          class="w-full px-4 py-3 rounded-xl border border-gray-200 focus:border-[#0D9488] focus:outline-none focus:ring-2 focus:ring-[#0D9488]/20 resize-none"
        ></textarea>
      </div>

      <div>
        <label class="block text-sm font-medium text-gray-700 mb-2">
          {{ t('Medical.Record.InitialDiagnosis') }} <span class="text-red-500">*</span>
        </label>
        <div class="space-y-2">
          <input
            v-model="formData.diagnosis"
            type="text"
            :placeholder="t('Medical.Record.DiagnosisPlaceholder')"
            class="w-full h-11 px-4 rounded-xl border border-gray-200 focus:border-[#0D9488] focus:outline-none focus:ring-2 focus:ring-[#0D9488]/20"
          />
          <button
            class="text-sm text-[#0D9488] hover:text-[#0F766E] flex items-center gap-1"
          >
            <Search :size="14" />
            {{ t('Medical.Record.ICD10') }}
          </button>
        </div>
      </div>

      <div>
        <label class="block text-sm font-medium text-gray-700 mb-2">
          {{ t('Medical.Record.Treatment') }} <span class="text-red-500">*</span>
        </label>
        <textarea
          v-model="formData.treatment"
          :placeholder="t('Medical.Record.TreatmentPlaceholder')"
          rows="3"
          class="w-full px-4 py-3 rounded-xl border border-gray-200 focus:border-[#0D9488] focus:outline-none focus:ring-2 focus:ring-[#0D9488]/20 resize-none"
        ></textarea>
      </div>

      <div>
        <label class="block text-sm font-medium text-gray-700 mb-2">{{ t('Medical.Record.FollowUp') }}</label>
        <div class="grid grid-cols-2 gap-3">
          <button
            v-for="option in followUpOptions"
            :key="option"
            @click="formData.followUp = option"
            :class="[
              'px-4 py-2.5 rounded-xl border text-sm font-medium transition-all',
              formData.followUp === option
                ? 'border-[#0D9488] bg-[#0D9488]/5 text-[#0D9488]'
                : 'border-gray-200 text-gray-700 hover:border-gray-300',
            ]"
          >
            {{ option }}
          </button>
        </div>
      </div>
    </div>

    <div class="p-6 border-t border-gray-100 shrink-0 bg-gray-50">
      <div class="flex gap-3 mb-3">
        <button
          @click="handleSave"
          class="flex-1 bg-[#0D9488] hover:bg-[#0F766E] text-white rounded-xl h-11 font-medium flex items-center justify-center gap-2 transition-colors"
        >
          <Save :size="16" />
          {{ t('Medical.Record.SubmitDemo') }}
        </button>
        <button
          class="px-4 py-2.5 border border-gray-200 rounded-xl hover:bg-gray-50 transition-colors"
        >
          {{ t('Medical.Record.Preview') }}
        </button>
      </div>
      <div class="flex items-start gap-2 text-xs text-gray-500">
        <CheckCircle2 :size="12" class="mt-0.5 shrink-0" />
        <p>{{ t('Medical.Record.FooterTip') }}</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import { useUIKit } from '@tencentcloud/uikit-base-component-vue3';
import { FileText, Search, Save, CheckCircle2 } from '@/shared/icons';

interface PatientInfo {
  name: string;
  age: number;
  gender: string;
  allergy_history?: string;
}

interface MedicalRecordPayload {
  chiefComplaint: string;
  presentIllness: string;
  pastHistory: string;
  allergyHistory: string;
  temperature: string;
  pulse: string;
  bloodPressure: string;
  respiration: string;
  auxiliaryExam: string;
  diagnosis: string;
  treatment: string;
  followUp: string;
}

defineProps<{
  patientInfo: PatientInfo;
}>();
const { t } = useUIKit();

const emit = defineEmits<{
  save: [payload: MedicalRecordPayload];
}>();

const formData = ref<MedicalRecordPayload>({
  chiefComplaint: '',
  presentIllness: '',
  pastHistory: '',
  allergyHistory: '',
  temperature: '',
  pulse: '',
  bloodPressure: '',
  respiration: '',
  auxiliaryExam: '',
  diagnosis: '',
  treatment: '',
  followUp: '',
});

const followUpOptions = [
  t('Medical.Record.Option3Days'),
  t('Medical.Record.Option1Week'),
  t('Medical.Record.Option2Weeks'),
  t('Medical.Record.Option1Month'),
];

const handleSave = () => {
  emit('save', { ...formData.value });
  window.alert(t('Medical.Record.SaveAlert'));
};
</script>
