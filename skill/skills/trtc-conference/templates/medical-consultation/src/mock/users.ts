import type { MedicalUser } from '@/services/adapters/types';

export const mockDoctorUsers: MedicalUser[] = [
  {
    userId: 'doctor_li',
    userName: 'Medical.Mock.DoctorLi',
    avatarUrl: '',
    role: 'doctor',
    title: 'Medical.Mock.ChiefPhysician',
    department: 'Medical.Mock.Cardiology',
    hospital: 'Medical.Mock.TertiaryHospital',
    experience: 'Medical.Mock.Years20',
    rating: '98.5',
    consultations: '3248',
    price: '50',
    tags: [
      'Medical.Mock.Hypertension',
      'Medical.Mock.Coronary',
      'Medical.Mock.Arrhythmia',
    ],
    specialty: 'Medical.Mock.ChronicCare',
    status: 'online',
  },
  {
    userId: 'doctor_wang',
    userName: 'Medical.Mock.DoctorWang',
    avatarUrl: '',
    role: 'doctor',
    title: 'Medical.Mock.AssociateChiefPhysician',
    department: 'Medical.Mock.Respiratory',
    hospital: 'Medical.Mock.InternetHospital',
    experience: 'Medical.Mock.Years15',
    rating: '97.2',
    consultations: '2156',
    price: '40',
    tags: [
      'Medical.Mock.Cough',
      'Medical.Mock.Asthma',
      'Medical.Mock.Pneumonia',
    ],
    specialty: 'Medical.Mock.RespiratoryFollowUp',
    status: 'online',
  },
  {
    userId: 'doctor_zhang',
    userName: 'Medical.Mock.DoctorZhang',
    avatarUrl: '',
    role: 'doctor',
    title: 'Medical.Mock.AttendingPhysician',
    department: 'Medical.Mock.Gastroenterology',
    hospital: 'Medical.Mock.SpecialtyHospital',
    experience: 'Medical.Mock.Years10',
    rating: '96.8',
    consultations: '1892',
    price: '30',
    tags: [
      'Medical.Mock.Gastritis',
      'Medical.Mock.GastricUlcer',
      'Medical.Mock.Indigestion',
    ],
    specialty: 'Medical.Mock.GastroFollowUp',
    status: 'busy',
  },
];

export const mockPatientUsers: MedicalUser[] = [
  {
    userId: 'patient_zhang',
    userName: 'Medical.Mock.PatientZhang',
    avatarUrl: '',
    role: 'patient',
  },
  {
    userId: 'patient_li',
    userName: 'Medical.Mock.PatientLi',
    avatarUrl: '',
    role: 'patient',
  },
];
