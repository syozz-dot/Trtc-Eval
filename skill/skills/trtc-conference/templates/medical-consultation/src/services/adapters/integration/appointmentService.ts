import type {
  AppointmentService,
  MedicalAppointment,
} from '@/services/adapters/types';
import { medicalT } from '@/i18n/medicalTranslate';
import { getRequiredLaunchContext } from '@/services/adapters/integration/launchContext';

function getLaunchAppointmentId() {
  return getRequiredLaunchContext()?.appointmentId || '';
}

function getLaunchUserContext() {
  const context = getRequiredLaunchContext();
  const role = context?.role;
  const userId = context?.userId || '';
  const doctorId =
    context?.doctorId ||
    (role === 'doctor' ? userId : '') ||
    'doctor_placeholder';
  const patientId =
    context?.patientId ||
    (role === 'patient' ? userId : '') ||
    'patient_placeholder';

  return { doctorId, patientId };
}

function buildIntegrationAppointment(
  appointmentId: string
): MedicalAppointment {
  // Customer integration should replace this mapper with data returned by
  // its appointment API, preserving the MedicalAppointment view model shape.
  const now = Math.floor(Date.now() / 1000);
  const { doctorId, patientId } = getLaunchUserContext();
  return {
    id: appointmentId,
    roomId: `room-${appointmentId}`,
    doctorId,
    patientId,
    scheduleStartTime: now,
    scheduleEndTime: now + 30 * 60,
    chiefComplaint: medicalT('Medical.Mock.IntegrationChiefComplaint'),
    allergyHistory: medicalT('Medical.Mock.IntegrationBusinessData'),
    medicalHistory: medicalT('Medical.Mock.IntegrationBusinessData'),
    patientAge: 0,
    patientGender: medicalT('Medical.Mock.Unknown'),
    patientPhone: '',
  };
}

export const integrationAppointmentService: AppointmentService = {
  getAppointmentById(appointmentId) {
    return buildIntegrationAppointment(appointmentId);
  },
  getAppointmentByRoomId(roomId) {
    const appointmentId = roomId.startsWith('room-')
      ? roomId.slice('room-'.length)
      : getLaunchAppointmentId();
    return appointmentId ? buildIntegrationAppointment(appointmentId) : null;
  },
  getAppointmentsByDoctor(doctorId) {
    const appointmentId = getLaunchAppointmentId();
    if (!appointmentId) {
      return [];
    }
    const appointment = buildIntegrationAppointment(appointmentId);
    return appointment.doctorId === doctorId ? [appointment] : [];
  },
  getAppointmentsByPatient(patientId) {
    const appointmentId = getLaunchAppointmentId();
    if (!appointmentId) {
      return [];
    }
    const appointment = buildIntegrationAppointment(appointmentId);
    return appointment.patientId === patientId ? [appointment] : [];
  },
};
