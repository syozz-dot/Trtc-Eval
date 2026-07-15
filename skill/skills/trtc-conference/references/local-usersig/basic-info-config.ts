/**
 * Local development credentials — Conference Web integration.
 *
 * ⚠️ SDKSECRETKEY is for local debugging ONLY. Do NOT ship to production.
 * Production UserSig MUST be issued by your backend.
 *
 * Source bundle (copy all 3 files into the target project's src/config/):
 *   skills/trtc-conference/references/local-usersig/
 * Same signing lib as the medical-consultation template config.
 */
import LibGenerateTestUserSig from './lib-generate-test-usersig-es.min';

export const SDKAPPID = 0;
export const SDKSECRETKEY = '';
export const EXPIRETIME = 604800;

export function assertBasicInfoConfigured() {
  if (!Number(SDKAPPID) || !String(SDKSECRETKEY).trim()) {
    throw new Error(
      '请先在 src/config/basic-info-config.ts 中配置 SDKAPPID 和 SDKSECRETKEY'
    );
  }
}

/** Generate login params for the given userId. userSig always matches userId. */
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
    scene: 5001 as const,
  };
}
