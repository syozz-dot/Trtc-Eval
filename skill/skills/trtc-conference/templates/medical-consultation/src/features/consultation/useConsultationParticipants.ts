import { computed, ref, type Ref } from 'vue';
import { useUIKit } from '@tencentcloud/uikit-base-component-vue3';
import type { RoomParticipant } from 'tuikit-atomicx-vue3';
import type { MedicalUser } from '@/services/adapters';
import type {
  ConsultationRole,
  ConsultationVideoMember,
} from '@/features/consultation/types';

export function useConsultationParticipants(options: {
  participantList: Ref<RoomParticipant[]>;
  participantListWithVideo: Ref<RoomParticipant[]>;
  localParticipant: Ref<RoomParticipant | null | undefined>;
  primaryDoctorId: Ref<string | undefined>;
  patientId: Ref<string | undefined>;
  preferredFocusUserId: Ref<string | undefined>;
  getDoctorById: (userId: string) => MedicalUser | null;
  getPatientById: (userId: string) => MedicalUser | null;
  selfDisplayName?: string;
}) {
  const { t } = useUIKit();
  const focusUserId = ref('');

  function getRoleLabel(role: ConsultationRole) {
    if (role === 'primaryDoctor') {
      return t('Medical.Common.AttendingDoctor');
    }
    if (role === 'consultingDoctor') {
      return t('Medical.Common.ConsultingDoctor');
    }
    return t('Medical.Common.Patient');
  }

  function getRoleFromUserId(
    userId: string,
    patientId: string | undefined,
    primaryDoctorId: string | undefined
  ): ConsultationRole {
    if (userId === patientId) {
      return 'patient';
    }
    if (userId === primaryDoctorId) {
      return 'primaryDoctor';
    }
    return 'consultingDoctor';
  }

  const videoReadyUserIdSet = computed(
    () =>
      new Set(
        options.participantListWithVideo.value.map(item => String(item.userId))
      )
  );

  const members = computed<ConsultationVideoMember[]>(() =>
    options.participantList.value.map(item => {
      const userId = String(item.userId);
      const isSelf = userId === options.localParticipant.value?.userId;
      const role: ConsultationRole = getRoleFromUserId(
        userId,
        options.patientId.value,
        options.primaryDoctorId.value
      );
      const doctorInfo = options.getDoctorById(userId);
      const patientInfo = options.getPatientById(userId);
      const rawDisplayName =
        item.nameCard ||
        doctorInfo?.userName ||
        patientInfo?.userName ||
        item.userName ||
        userId;
      const displayName = isSelf
        ? options.selfDisplayName ||
          `${rawDisplayName} (${t('Medical.Common.Me')})`
        : rawDisplayName;

      return {
        userId,
        displayName,
        avatarText: isSelf
          ? options.selfDisplayName || t('Medical.Common.Me')
          : String(rawDisplayName).charAt(0),
        role,
        roleLabel: getRoleLabel(role),
        participant: item,
        videoReady: videoReadyUserIdSet.value.has(userId),
        isSelf,
      };
    })
  );

  const mainMember = computed(() => {
    const list = members.value;
    return (
      list.find(item => item.userId === focusUserId.value) ||
      list.find(item => item.userId === options.preferredFocusUserId.value) ||
      list.find(
        item => item.userId === options.localParticipant.value?.userId
      ) ||
      list[0] ||
      null
    );
  });

  const thumbnailMembers = computed(() =>
    members.value.filter(item => item.userId !== mainMember.value?.userId)
  );

  function focusParticipant(userId: string) {
    focusUserId.value = userId;
  }

  return {
    focusUserId,
    videoReadyUserIdSet,
    members,
    mainMember,
    thumbnailMembers,
    focusParticipant,
  };
}
