import { mockDoctorUsers, mockPatientUsers } from '@/mock/users';
import { medicalTranslate, medicalTranslateList } from '@/i18n/medicalTranslate';
import type { MedicalUser, UserService } from '@/services/adapters/types';

function localizeUser(user: MedicalUser): MedicalUser {
  return {
    ...user,
    userName: medicalTranslate(user.userName),
    title: user.title ? medicalTranslate(user.title) : user.title,
    department: user.department ? medicalTranslate(user.department) : user.department,
    hospital: user.hospital ? medicalTranslate(user.hospital) : user.hospital,
    experience: user.experience ? medicalTranslate(user.experience) : user.experience,
    tags: medicalTranslateList(user.tags),
    specialty: user.specialty ? medicalTranslate(user.specialty) : user.specialty,
  };
}

function findUserById(userId: string): MedicalUser | null {
  const user =
    mockDoctorUsers.find(item => item.userId === userId) ||
    mockPatientUsers.find(item => item.userId === userId);
  return user ? localizeUser(user) : null;
}

export const mockUserService: UserService = {
  listDoctors() {
    return mockDoctorUsers.map(localizeUser);
  },
  listPatients() {
    return mockPatientUsers.map(localizeUser);
  },
  getUserById(userId) {
    return findUserById(userId);
  },
  getDoctorById(userId) {
    const user = mockDoctorUsers.find(item => item.userId === userId);
    return user ? localizeUser(user) : null;
  },
  getPatientById(userId) {
    const user = mockPatientUsers.find(item => item.userId === userId);
    return user ? localizeUser(user) : null;
  },
};
