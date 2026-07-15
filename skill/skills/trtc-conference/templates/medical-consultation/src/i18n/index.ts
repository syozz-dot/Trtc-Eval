import { i18next } from '@tencentcloud/uikit-base-component-vue3';
import { resource as enResource } from './en-US';
import { resource as zhResource } from './zh-CN';

export { enResource, zhResource };

export const addI18n = (
  lng: string,
  resource: any,
  deep = true,
  overwrite = false
) => {
  i18next.addResourceBundle(
    lng,
    'translation',
    resource.translation,
    deep,
    overwrite
  );
};

export function initMedicalI18n() {
  addI18n('en-US', { translation: enResource });
  addI18n('zh-CN', { translation: zhResource });
}
