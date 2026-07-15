import { medicalT } from '@/i18n/medicalTranslate';
import LibGenerateTestUserSig from './lib-generate-test-usersig-es.min';

export const SDKAPPID = 0;
export const SDKSECRETKEY = '';
export const EXPIRETIME = 604800;

export function assertBasicInfoConfigured() {
  if (!Number(SDKAPPID) || !String(SDKSECRETKEY).trim()) {
    throw new Error(
      medicalT('Medical.Config.SDKConfigErrorWithUserSig')
    );
  }
}

export function getBasicInfo(userId: string) {
  assertBasicInfoConfigured();
  const generator = new LibGenerateTestUserSig(
    SDKAPPID,
    SDKSECRETKEY,
    EXPIRETIME
  );
  return {
    sdkAppId: SDKAPPID,
    userId,
    userSig: generator.genTestUserSig(userId),
    scene: 5001,
  };
}
