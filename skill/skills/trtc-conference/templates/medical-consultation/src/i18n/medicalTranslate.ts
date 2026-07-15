import { i18next } from '@tencentcloud/uikit-base-component-vue3';
import { medicalLanguage } from './state';

const textKeyMap: Record<string, string> = {
  李医生: 'Medical.Mock.DoctorLi',
  王医生: 'Medical.Mock.DoctorWang',
  张医生: 'Medical.Mock.DoctorZhang',
  张晓明: 'Medical.Mock.PatientZhang',
  李美华: 'Medical.Mock.PatientLi',
  主任医师: 'Medical.Mock.ChiefPhysician',
  副主任医师: 'Medical.Mock.AssociateChiefPhysician',
  主治医师: 'Medical.Mock.AttendingPhysician',
  心内科: 'Medical.Mock.Cardiology',
  呼吸内科: 'Medical.Mock.Respiratory',
  消化内科: 'Medical.Mock.Gastroenterology',
  示例三甲医院: 'Medical.Mock.TertiaryHospital',
  示例互联网医院: 'Medical.Mock.InternetHospital',
  示例专科医院: 'Medical.Mock.SpecialtyHospital',
  '20年': 'Medical.Mock.Years20',
  '15年': 'Medical.Mock.Years15',
  '10年': 'Medical.Mock.Years10',
  高血压: 'Medical.Mock.Hypertension',
  冠心病: 'Medical.Mock.Coronary',
  心律失常: 'Medical.Mock.Arrhythmia',
  咳嗽: 'Medical.Mock.Cough',
  哮喘: 'Medical.Mock.Asthma',
  肺炎: 'Medical.Mock.Pneumonia',
  胃炎: 'Medical.Mock.Gastritis',
  胃溃疡: 'Medical.Mock.GastricUlcer',
  消化不良: 'Medical.Mock.Indigestion',
  复诊问诊与慢病管理: 'Medical.Mock.ChronicCare',
  呼吸系统在线复诊: 'Medical.Mock.RespiratoryFollowUp',
  胃肠健康随访: 'Medical.Mock.GastroFollowUp',
  男: 'Medical.Mock.Male',
  女: 'Medical.Mock.Female',
  无: 'Medical.Mock.None',
  未知: 'Medical.Mock.Unknown',
  '持续咳嗽、低热 3 天': 'Medical.Mock.CoughFever',
  '夜间咳嗽、轻微气喘': 'Medical.Mock.NightCough',
  '饭后胃胀、反酸': 'Medical.Mock.Reflux',
  '头晕、心悸': 'Medical.Mock.DizzyPalpitations',
  '反复咽痒、清晨咳嗽': 'Medical.Mock.ThroatCough',
  '腹部隐痛、食欲下降': 'Medical.Mock.AbdominalPain',
  青霉素过敏: 'Medical.Mock.PenicillinAllergy',
  花粉过敏: 'Medical.Mock.PollenAllergy',
  无重大疾病史: 'Medical.Mock.NoMajorHistory',
  过敏性鼻炎: 'Medical.Mock.AllergicRhinitis',
  慢性胃炎: 'Medical.Mock.ChronicGastritis',
  甲状腺结节: 'Medical.Mock.ThyroidNodule',
  轻度哮喘: 'Medical.Mock.MildAsthma',
  '示例主诉，请替换为客户预约系统返回的诊前信息': 'Medical.Mock.IntegrationChiefComplaint',
  请替换为客户业务数据: 'Medical.Mock.IntegrationBusinessData',
  '[图片消息]': 'Medical.Message.ImageMessage',
  '[视频消息]': 'Medical.Message.VideoMessage',
  '[文件消息]': 'Medical.Message.FileMessage',
  '[暂不支持的消息类型]': 'Medical.Message.UnsupportedMessage',
  'EMR / HIS / PACS 业务插槽': 'Medical.Business.EMRHISPACSSlot',
  会话初始化失败: 'Medical.Chat.SessionInitFailed',
  消息发送失败: 'Medical.Chat.MessageSendFailed',
  确认踢出成员: 'Medical.Member.ConfirmKickTitle',
  确认踢出: 'Medical.Member.ConfirmButton',
  取消: 'Medical.Member.CancelButton',
  中文: 'Medical.LanguageSwitch.ChineseLang',
};

export function medicalTranslate(text?: string) {
  medicalLanguage.value;
  if (!text) {
    return text || '';
  }
  if (text.startsWith('Medical.')) {
    return i18next.t(text);
  }
  const key = textKeyMap[text];
  return key ? i18next.t(key) : text;
}

export function medicalT(key: string, options?: Record<string, unknown>) {
  medicalLanguage.value;
  return i18next.t(key, options);
}

export function medicalTranslateList(values?: string[]) {
  return values?.map(item => medicalTranslate(item)) || [];
}
