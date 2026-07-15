<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';
import { useUIKit } from '@tencentcloud/uikit-base-component-vue3';
import {
  Stethoscope,
  Bell,
  LogOut,
  Users,
  Clock,
  CheckCircle,
  TrendingUp,
  Video,
  FileText,
  X,
} from '@/shared/icons';
import {
  useLoginState,
  useRoomState,
  RoomEvent,
  RoomStatus,
} from 'tuikit-atomicx-vue3';
import { services, type MedicalAppointment } from '@/services/adapters';
import type { ConsultationCallEvent } from '@/features/consultation/types';
import { clearSession, getSessionUser } from '@/utils/session';
import { formatTimeRange } from '@/utils/format';
import LoadingSpinner from '@/components/LoadingSpinner.vue';
import MedicalButton from '@/components/MedicalButton.vue';
import LanguageSwitch from '@/components/LanguageSwitch.vue';

const router = useRouter();
const loginState = useLoginState();
const roomState = useRoomState();
const { t } = useUIKit();

const loading = ref(false);
const syncing = ref(false);
const startingAppointmentId = ref('');
const loggingOut = ref(false);
const consultationInvite = ref<{
  appointment: MedicalAppointment;
  fromDoctor: ReturnType<typeof services.user.getDoctorById>;
  patient: ReturnType<typeof services.user.getPatientById>;
  roomId: string;
} | null>(null);
const joiningInvite = ref(false);
const inviteDetailsVisible = ref(false);
const actionMessage = ref('');
type AppointmentFilter = 'all' | 'waiting' | 'running';

const activeFilter = ref<AppointmentFilter>('all');
const filters = computed<Array<{ value: AppointmentFilter; label: string }>>(() => [
  { value: 'all', label: t('Medical.DoctorDashboard.All') },
  { value: 'waiting', label: t('Medical.DoctorDashboard.Waiting') },
  { value: 'running', label: t('Medical.DoctorDashboard.Running') },
]);

const doctor = computed(() => getSessionUser());
const doctorAppointments = computed(() =>
  doctor.value
    ? services.appointment.getAppointmentsByDoctor(doctor.value.userId)
    : []
);

const appointmentCards = computed(() =>
  doctorAppointments.value.map(item => {
    const scheduled = roomState.scheduledRoomList.value.find(
      room => room.roomId === item.roomId
    );
    const patient = services.user.getPatientById(item.patientId);
    return {
      ...item,
      scheduled,
      patient,
    };
  })
);

const filteredAppointmentCards = computed(() => {
  if (activeFilter.value === 'all') {
    return appointmentCards.value;
  }
  if (activeFilter.value === 'waiting') {
    return appointmentCards.value.filter(
      item => item.scheduled?.roomStatus !== RoomStatus.Running
    );
  }
  return appointmentCards.value.filter(
    item => item.scheduled?.roomStatus === RoomStatus.Running
  );
});

const stats = computed(() => {
  const total = appointmentCards.value.length;
  const running = appointmentCards.value.filter(
    item => item.scheduled?.roomStatus === RoomStatus.Running
  ).length;
  const scheduled = appointmentCards.value.filter(
    item => item.scheduled?.roomStatus !== RoomStatus.Running
  ).length;
  const syncedRooms = roomState.scheduledRoomList.value.length;
  return [
    {
      title: t('Medical.DoctorDashboard.StatToday'),
      value: String(total),
      icon: Users,
      color: 'bg-gradient-to-br from-blue-500 to-blue-600',
    },
    {
      title: t('Medical.DoctorDashboard.StatWaiting'),
      value: String(scheduled),
      icon: Clock,
      color: 'bg-gradient-to-br from-yellow-500 to-yellow-600',
    },
    {
      title: t('Medical.DoctorDashboard.StatRunning'),
      value: String(running),
      icon: CheckCircle,
      color: 'bg-gradient-to-br from-green-500 to-green-600',
    },
    {
      title: t('Medical.DoctorDashboard.StatSynced'),
      value: String(syncedRooms),
      icon: TrendingUp,
      color: 'bg-gradient-to-br from-purple-500 to-purple-600',
    },
  ];
});

function getSchedulableWindow(appointment: {
  scheduleStartTime: number;
  scheduleEndTime: number;
}) {
  const nowSeconds = Math.floor(Date.now() / 1000);
  const minimumStartTime = nowSeconds + 5 * 60;
  const originalDuration = Math.max(
    30 * 60,
    appointment.scheduleEndTime - appointment.scheduleStartTime
  );

  if (appointment.scheduleEndTime > minimumStartTime) {
    return {
      scheduleStartTime: appointment.scheduleStartTime,
      scheduleEndTime: appointment.scheduleEndTime,
    };
  }

  return {
    scheduleStartTime: minimumStartTime,
    scheduleEndTime: minimumStartTime + originalDuration,
  };
}

async function loadScheduledRooms() {
  loading.value = true;
  try {
    await roomState.getScheduledRoomList({ cursor: '' });
  } finally {
    loading.value = false;
  }
}

async function syncAppointments() {
  if (!doctor.value) {
    return;
  }
  syncing.value = true;
  actionMessage.value = '';
  try {
    for (const appointment of doctorAppointments.value) {
      const existing = roomState.scheduledRoomList.value.find(
        room => room.roomId === appointment.roomId
      );
      if (existing) {
        continue;
      }
      const scheduleWindow = getSchedulableWindow(appointment);
      await roomState.scheduleRoom({
        roomId: appointment.roomId,
        options: {
          roomName: `${doctor.value.userName} · ${appointment.id}`,
          scheduleStartTime: scheduleWindow.scheduleStartTime,
          scheduleEndTime: scheduleWindow.scheduleEndTime,
          scheduleAttendees: [appointment.patientId],
          reminderSecondsBeforeStart: 300,
        },
      });
    }
    await loadScheduledRooms();
    actionMessage.value = t('Medical.DoctorDashboard.RefreshSuccess');
  } catch (error) {
    actionMessage.value =
      error instanceof Error ? error.message : t('Medical.DoctorDashboard.RefreshFailed');
  } finally {
    syncing.value = false;
  }
}

async function startConsultation(appointmentId: string, roomId: string) {
  if (startingAppointmentId.value) {
    return;
  }
  const appointment = services.appointment.getAppointmentById(appointmentId);
  if (!appointment) {
    return;
  }
  startingAppointmentId.value = appointmentId;
  try {
    try {
      await roomState.createAndJoinRoom({
        roomId,
        options: {
          roomName: `${doctor.value?.userName ?? t('Medical.Common.Doctor')} · ${appointment.id}`,
        },
      });
    } catch {
      await roomState.joinRoom({ roomId });
    }
    await router.push(`/doctor/consultation/${appointmentId}`);
  } catch (error) {
    actionMessage.value =
      error instanceof Error ? error.message : t('Medical.DoctorDashboard.EnterFailed');
  } finally {
    startingAppointmentId.value = '';
  }
}

function getInviteDoctorId(
  eventInfo: ConsultationCallEvent,
  appointment: MedicalAppointment
) {
  return (
    eventInfo?.call?.inviter?.userId ||
    eventInfo?.call?.caller?.userId ||
    eventInfo?.inviter?.userId ||
    eventInfo?.senderUserId ||
    appointment.doctorId
  );
}

function handleConsultationInviteReceived(eventInfo: ConsultationCallEvent) {
  const roomId = eventInfo?.roomInfo?.roomId || eventInfo?.call?.roomId || '';
  if (!roomId || !doctor.value) {
    return;
  }
  const appointment = services.appointment.getAppointmentByRoomId(roomId);
  if (!appointment || appointment.doctorId === doctor.value.userId) {
    return;
  }
  const fromDoctor = services.user.getDoctorById(
    getInviteDoctorId(eventInfo, appointment)
  );
  consultationInvite.value = {
    appointment,
    fromDoctor,
    patient: services.user.getPatientById(appointment.patientId),
    roomId,
  };
}

function clearConsultationInviteByRoom(eventInfo: ConsultationCallEvent) {
  const roomId = eventInfo?.roomInfo?.roomId || eventInfo?.call?.roomId || '';
  if (roomId && consultationInvite.value?.roomId === roomId) {
    dismissConsultationInvite();
  }
}

function dismissConsultationInvite() {
  consultationInvite.value = null;
  inviteDetailsVisible.value = false;
}

async function joinConsultationInvite() {
  if (!consultationInvite.value || joiningInvite.value) {
    return;
  }
  joiningInvite.value = true;
  actionMessage.value = '';
  try {
    try {
      await roomState.acceptCall({ roomId: consultationInvite.value.roomId });
    } catch {
      await roomState.joinRoom({ roomId: consultationInvite.value.roomId });
    }
    await router.push(
      `/doctor/consultation/${consultationInvite.value.appointment.id}`
    );
    dismissConsultationInvite();
  } catch (error) {
    actionMessage.value =
      error instanceof Error ? error.message : t('Medical.DoctorDashboard.JoinInviteFailed');
  } finally {
    joiningInvite.value = false;
  }
}

async function logout() {
  if (loggingOut.value) {
    return;
  }
  loggingOut.value = true;
  try {
    await loginState.logout();
    clearSession();
    router.replace('/login');
  } finally {
    loggingOut.value = false;
  }
}

onMounted(async () => {
  if (!doctor.value || doctor.value.role !== 'doctor') {
    router.replace('/login');
    return;
  }
  await loadScheduledRooms();
  roomState.subscribeEvent(
    RoomEvent.onCallReceived,
    handleConsultationInviteReceived
  );
  roomState.subscribeEvent(
    RoomEvent.onCallCancelled,
    clearConsultationInviteByRoom
  );
  roomState.subscribeEvent(RoomEvent.onCallTimeout, clearConsultationInviteByRoom);
});

onBeforeUnmount(() => {
  roomState.unsubscribeEvent(
    RoomEvent.onCallReceived,
    handleConsultationInviteReceived
  );
  roomState.unsubscribeEvent(
    RoomEvent.onCallCancelled,
    clearConsultationInviteByRoom
  );
  roomState.unsubscribeEvent(
    RoomEvent.onCallTimeout,
    clearConsultationInviteByRoom
  );
});
</script>

<template>
  <div class="min-h-screen bg-[#F8FAFB]">
    <header class="bg-white border-b border-gray-200 px-6 py-4">
      <div class="max-w-7xl mx-auto flex items-center justify-between">
        <div class="flex items-center gap-4">
          <div
            class="bg-gradient-to-br from-[#0D9488] to-[#0F766E] p-2 rounded-xl"
          >
            <Stethoscope :size="24" class="text-white" />
          </div>
          <div>
            <h1 class="text-xl font-semibold text-gray-900">{{ t('Medical.DoctorDashboard.Title') }}</h1>
            <p class="text-sm text-gray-500">{{ t('Medical.DoctorDashboard.Subtitle') }}</p>
          </div>
        </div>

        <div class="flex items-center gap-4">
          <LanguageSwitch />
          <button
            class="p-2 hover:bg-gray-100 rounded-xl transition-colors relative"
          >
            <Bell :size="20" class="text-gray-600" />
            <span
              v-if="consultationInvite"
              class="absolute top-1 right-1 w-2 h-2 bg-red-500 rounded-full"
            ></span>
          </button>
          <div class="h-8 w-px bg-gray-200"></div>
          <div class="flex items-center gap-3">
            <div
              class="w-10 h-10 rounded-full bg-gradient-to-br from-[#0D9488] to-[#0F766E] flex items-center justify-center text-white font-medium"
            >
              {{ doctor?.userName?.slice(0, 1) }}
            </div>
            <div>
              <p class="text-sm font-medium text-gray-900">
                {{ doctor?.userName }}
              </p>
              <p class="text-xs text-gray-500">{{ doctor?.title }}</p>
            </div>
          </div>
          <button
            @click="logout"
            :disabled="loggingOut"
            class="p-2 hover:bg-gray-100 rounded-xl transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
          >
            <LoadingSpinner v-if="loggingOut" class="text-gray-600" />
            <LogOut v-else :size="20" class="text-gray-600" />
          </button>
        </div>
      </div>
    </header>

    <main class="max-w-7xl mx-auto p-6">
      <div class="flex items-end justify-between gap-4 mb-6">
        <div>
          <h2 class="text-3xl font-semibold text-gray-900 mb-2">
            {{ t('Medical.DoctorDashboard.TodayAppointments', { count: stats[0]?.value }) }}
          </h2>
          <p class="text-sm text-gray-500">
            {{ t('Medical.DoctorDashboard.CurrentDoctor', { hospital: doctor?.hospital, doctor: doctor?.userName }) }}
          </p>
        </div>
        <MedicalButton @click="syncAppointments" :loading="syncing">
          {{ syncing ? t('Medical.DoctorDashboard.Refreshing') : t('Medical.DoctorDashboard.RefreshToday') }}
        </MedicalButton>
      </div>

      <div class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-6 mb-6">
        <div
          v-for="stat in stats"
          :key="stat.title"
          class="bg-white rounded-2xl p-6 border border-gray-100 shadow-sm hover:shadow-md transition-shadow"
        >
          <div class="flex items-center justify-between mb-4">
            <div :class="['p-3 rounded-xl', stat.color]">
              <component :is="stat.icon" :size="24" class="text-white" />
            </div>
          </div>
          <h3 class="text-2xl font-semibold text-gray-900 mb-1">
            {{ stat.value }}
          </h3>
          <p class="text-sm text-gray-600">{{ stat.title }}</p>
        </div>
      </div>

      <p
        v-if="actionMessage"
        class="mb-4 text-sm text-[#0D9488] bg-[#0D9488]/10 px-4 py-3 rounded-xl"
      >
        {{ actionMessage }}
      </p>

      <div
        v-if="consultationInvite"
        class="mb-6 rounded-3xl border border-indigo-100 bg-white shadow-[0_10px_30px_rgba(79,70,229,0.12)]"
      >
        <div class="p-5 flex items-center justify-between gap-4">
          <div class="flex items-center gap-4 flex-1 min-w-0">
            <div class="relative shrink-0">
              <div
                class="w-12 h-12 rounded-full bg-gradient-to-br from-indigo-500 to-indigo-600 flex items-center justify-center shadow-lg shadow-indigo-500/30 animate-pulse"
              >
                <Stethoscope class="w-6 h-6 text-white" />
              </div>
              <div
                class="absolute -top-1 -right-1 w-5 h-5 bg-red-500 rounded-full flex items-center justify-center border-2 border-white"
              >
                <span class="text-white text-xs font-bold">!</span>
              </div>
            </div>
            <div class="flex-1 min-w-0">
              <div class="flex items-center gap-2 mb-1">
                <h4 class="font-semibold text-gray-900">{{ t('Medical.DoctorDashboard.ConsultationInvite') }}</h4>
                <span
                  class="bg-indigo-500 text-white rounded-full px-3 py-0.5 text-xs font-medium"
                >
                  {{ t('Medical.DoctorDashboard.Pending') }}
                </span>
              </div>
              <p class="text-sm text-gray-700 leading-6">
                {{
                  t('Medical.DoctorDashboard.InviteSummary', {
                    doctor: consultationInvite.fromDoctor?.userName || t('Medical.Common.Doctor'),
                    department: consultationInvite.fromDoctor?.department || t('Medical.Common.UnknownDepartment'),
                    patient: consultationInvite.patient?.userName || t('Medical.Common.Patient'),
                  })
                }}
              </p>
            </div>
          </div>
          <div class="flex items-center gap-3 shrink-0">
            <button
              type="button"
              @click="inviteDetailsVisible = true"
              class="rounded-xl gap-2 h-11 px-4 border border-indigo-200 text-indigo-600 hover:bg-indigo-50 inline-flex items-center justify-center font-medium transition-colors"
            >
              <FileText class="w-4 h-4" />
              {{ t('Medical.DoctorDashboard.ViewDetails') }}
            </button>
            <button
              type="button"
              @click="joinConsultationInvite"
              :disabled="joiningInvite"
              class="bg-gradient-to-r from-indigo-500 to-indigo-600 hover:from-indigo-600 hover:to-indigo-700 text-white rounded-xl gap-2 h-11 px-4 shadow-lg shadow-indigo-500/30 inline-flex items-center justify-center font-medium transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
            >
              <LoadingSpinner v-if="joiningInvite" />
              <Video v-else class="w-4 h-4" />
              {{ joiningInvite ? t('Medical.DoctorDashboard.Joining') : t('Medical.DoctorDashboard.JoinNow') }}
            </button>
            <button
              type="button"
              @click="dismissConsultationInvite"
              class="w-9 h-9 rounded-lg hover:bg-gray-100 shrink-0 inline-flex items-center justify-center transition-colors"
            >
              <X class="w-4 h-4 text-gray-500" />
            </button>
          </div>
        </div>
      </div>

      <div class="bg-white rounded-2xl border border-gray-100 shadow-sm">
        <div class="p-6 border-b border-gray-100">
          <div class="flex items-center justify-between gap-4">
            <div>
              <h2 class="text-lg font-semibold text-gray-900">{{ t('Medical.DoctorDashboard.WaitingPatients') }}</h2>
              <p class="text-sm text-gray-500 mt-1">
                {{ loading ? t('Medical.DoctorDashboard.LoadingAppointments') : t('Medical.DoctorDashboard.SortByTime') }}
              </p>
            </div>
            <div class="flex items-center gap-2">
              <button
                v-for="filter in filters"
                :key="filter.value"
                @click="activeFilter = filter.value"
                :class="[
                  'px-4 py-2 rounded-xl text-sm font-medium transition-all',
                  activeFilter === filter.value
                    ? 'bg-[#0D9488] text-white'
                    : 'text-gray-600 hover:bg-gray-100',
                ]"
              >
                {{ filter.label }}
              </button>
            </div>
          </div>
        </div>

        <div class="divide-y divide-gray-100">
          <div
            v-for="item in filteredAppointmentCards"
            :key="item.id"
            class="p-6 hover:bg-gray-50 transition-colors"
          >
            <div class="flex items-center justify-between gap-4">
              <div class="flex items-center gap-4 flex-1 min-w-0">
                <div
                  class="w-12 h-12 rounded-full bg-gradient-to-br from-blue-500 to-blue-600 flex items-center justify-center text-white font-medium"
                >
                  {{ item.patient?.userName?.charAt(0) }}
                </div>
                <div class="flex-1 min-w-0">
                  <div class="flex items-center gap-3 mb-1 flex-wrap">
                    <h3 class="font-semibold text-gray-900">
                      {{ item.patient?.userName }}
                    </h3>
                    <span class="text-sm text-gray-500">
                      {{ t('Medical.DoctorDashboard.PatientAge', { gender: item.patientGender, age: item.patientAge }) }}
                    </span>
                    <span
                      :class="[
                        'px-2 py-0.5 rounded-full text-xs font-medium',
                        item.scheduled?.roomStatus === RoomStatus.Running
                          ? 'bg-green-100 text-green-700'
                          : 'bg-yellow-100 text-yellow-700',
                      ]"
                    >
                      {{
                        item.scheduled?.roomStatus === RoomStatus.Running
                          ? t('Medical.DoctorDashboard.ConsultationRunning')
                          : t('Medical.DoctorDashboard.Waiting')
                      }}
                    </span>
                  </div>
                  <div
                    class="flex items-center gap-6 text-sm text-gray-600 flex-wrap"
                  >
                    <span class="flex items-center gap-1">
                      <Clock :size="14" />
                      {{
                        formatTimeRange(
                          item.scheduleStartTime,
                          item.scheduleEndTime
                        )
                      }}
                    </span>
                    <span class="flex items-center gap-1">
                      <FileText :size="14" />
                      {{ item.chiefComplaint }}
                    </span>
                  </div>
                </div>
              </div>

              <MedicalButton
                @click="startConsultation(item.id, item.roomId)"
                :disabled="!!startingAppointmentId"
                :loading="startingAppointmentId === item.id"
                class="shrink-0"
              >
                <Video v-if="startingAppointmentId !== item.id" :size="16" />
                {{
                  startingAppointmentId === item.id ? t('Medical.Common.Entering') : t('Medical.DoctorDashboard.StartConsultation')
                }}
              </MedicalButton>
            </div>
          </div>
        </div>
      </div>
    </main>

    <div
      v-if="inviteDetailsVisible && consultationInvite"
      class="fixed inset-0 z-[120] flex items-center justify-center bg-black/45 p-4"
      @click.self="inviteDetailsVisible = false"
    >
      <div class="w-full max-w-[460px] rounded-3xl bg-white p-6 shadow-2xl">
        <div class="flex items-start justify-between gap-4">
          <div>
            <h3 class="text-lg font-semibold text-gray-900">{{ t('Medical.DoctorDashboard.InviteDetails') }}</h3>
            <p class="mt-1 text-sm text-gray-500">
              {{ t('Medical.DoctorDashboard.AppointmentId', { id: consultationInvite.appointment.id }) }}
            </p>
          </div>
          <button
            type="button"
            @click="inviteDetailsVisible = false"
            class="w-8 h-8 rounded-lg hover:bg-gray-100 inline-flex items-center justify-center"
          >
            <X class="w-4 h-4 text-gray-500" />
          </button>
        </div>

        <div class="mt-5 space-y-4 text-sm">
          <div class="rounded-2xl bg-indigo-50 px-4 py-3">
            <p class="text-gray-500">{{ t('Medical.DoctorDashboard.InvitingDoctor') }}</p>
            <p class="mt-1 font-medium text-gray-900">
              {{ consultationInvite.fromDoctor?.userName || t('Medical.Common.Doctor') }}
              · {{ consultationInvite.fromDoctor?.department || t('Medical.Common.UnknownDepartment') }}
            </p>
          </div>
          <div class="rounded-2xl bg-gray-50 px-4 py-3">
            <p class="text-gray-500">{{ t('Medical.DoctorDashboard.PatientInfo') }}</p>
            <p class="mt-1 font-medium text-gray-900">
              {{ consultationInvite.patient?.userName || t('Medical.Common.Patient') }}
              · {{ t('Medical.DoctorDashboard.PatientAge', { gender: consultationInvite.appointment.patientGender, age: consultationInvite.appointment.patientAge }) }}
            </p>
          </div>
          <div class="rounded-2xl bg-gray-50 px-4 py-3">
            <p class="text-gray-500">{{ t('Medical.DoctorDashboard.ChiefComplaint') }}</p>
            <p class="mt-1 font-medium text-gray-900">
              {{ consultationInvite.appointment.chiefComplaint }}
            </p>
          </div>
          <div class="rounded-2xl bg-red-50 px-4 py-3">
            <p class="text-red-500">{{ t('Medical.DoctorDashboard.AllergyHistory') }}</p>
            <p class="mt-1 font-medium text-red-700">
              {{ consultationInvite.appointment.allergyHistory }}
            </p>
          </div>
        </div>

        <div class="mt-6 flex justify-end gap-3">
          <button
            type="button"
            @click="inviteDetailsVisible = false"
            class="h-11 px-4 rounded-xl border border-gray-200 text-gray-700 font-medium hover:bg-gray-50"
          >
            {{ t('Medical.DoctorDashboard.HandleLater') }}
          </button>
          <button
            type="button"
            @click="joinConsultationInvite"
            :disabled="joiningInvite"
            class="h-11 px-4 rounded-xl bg-indigo-600 text-white font-medium hover:bg-indigo-700 disabled:opacity-60 disabled:cursor-not-allowed inline-flex items-center gap-2"
          >
            <LoadingSpinner v-if="joiningInvite" />
            <Video v-else class="w-4 h-4" />
            {{ joiningInvite ? t('Medical.DoctorDashboard.Joining') : t('Medical.DoctorDashboard.JoinNow') }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
