import { ref } from 'vue';
import { useUIKit } from '@tencentcloud/uikit-base-component-vue3';

export type DeviceOpenResult =
  | { status: 'fulfilled'; value: unknown }
  | { status: 'rejected'; reason: unknown };

export function useConsultationDevices() {
  const { t } = useUIKit();
  const devicePermissionHint = ref('');

  function getDeviceErrorHint(deviceLabel: string, error: unknown) {
    const message = error instanceof Error ? error.message : '';
    return t('Medical.Device.OpenFailed', {
      device: deviceLabel,
      message: message ? t('Medical.Device.ErrorInfo', { message }) : '',
    });
  }

  function updateDevicePermissionHint(results: DeviceOpenResult[]) {
    const failedLabels = results
      .map((result, index) => ({
        result,
        label: index === 0 ? t('Medical.Device.Microphone') : t('Medical.Device.Camera'),
      }))
      .filter(
        item =>
          item.result.status === 'rejected' ||
          (item.result.status === 'fulfilled' && item.result.value === false)
      )
      .map(item => item.label);

    if (!failedLabels.length) {
      devicePermissionHint.value = '';
      return;
    }

    devicePermissionHint.value = t('Medical.Device.PermissionHint', {
      devices: failedLabels.join('、'),
    });
  }

  return {
    devicePermissionHint,
    getDeviceErrorHint,
    updateDevicePermissionHint,
  };
}
