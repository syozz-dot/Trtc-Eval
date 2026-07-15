import { mockAppointments } from '@/mock/appointments';
import { medicalTranslate } from '@/i18n/medicalTranslate';
import type {
  AppointmentService,
  MedicalAppointment,
} from '@/services/adapters/types';

function cloneAppointment(
  appointment: MedicalAppointment | undefined
): MedicalAppointment | null {
  return appointment
    ? {
        ...appointment,
        chiefComplaint: medicalTranslate(appointment.chiefComplaint),
        allergyHistory: medicalTranslate(appointment.allergyHistory),
        medicalHistory: medicalTranslate(appointment.medicalHistory),
        patientGender: medicalTranslate(appointment.patientGender),
      }
    : null;
}

export const mockAppointmentService: AppointmentService = {
  getAppointmentById(appointmentId) {
    return cloneAppointment(
      mockAppointments.find(item => item.id === appointmentId)
    );
  },
  getAppointmentByRoomId(roomId) {
    return cloneAppointment(mockAppointments.find(item => item.roomId === roomId));
  },
  getAppointmentsByDoctor(doctorId) {
    return mockAppointments
      .filter(item => item.doctorId === doctorId)
      .map(item => cloneAppointment(item))
      .filter((item): item is MedicalAppointment => !!item);
  },
  getAppointmentsByPatient(patientId) {
    return mockAppointments
      .filter(item => item.patientId === patientId)
      .map(item => cloneAppointment(item))
      .filter((item): item is MedicalAppointment => !!item);
  },
};
