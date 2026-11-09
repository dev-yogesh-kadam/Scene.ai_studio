// A light touch felt on a tap, a success or an error, where the browser can vibrate (Chrome on Android can; iPhones
// can't, and nothing happens). Named as expo-haptics names them, so screens read the same.

const vibrate = (pattern: number | number[]) => {
  try {
    if (typeof navigator !== 'undefined' && 'vibrate' in navigator) navigator.vibrate(pattern);
  } catch {
    // not allowed until the page has been touched: nothing to feel
  }
};

export enum ImpactFeedbackStyle {
  Light = 'light',
  Medium = 'medium',
  Heavy = 'heavy',
}

export enum NotificationFeedbackType {
  Success = 'success',
  Warning = 'warning',
  Error = 'error',
}

export async function impactAsync(style: ImpactFeedbackStyle = ImpactFeedbackStyle.Medium) {
  vibrate(style === ImpactFeedbackStyle.Light ? 8 : style === ImpactFeedbackStyle.Medium ? 14 : 22);
}

export async function selectionAsync() {
  vibrate(6);
}

export async function notificationAsync(type: NotificationFeedbackType = NotificationFeedbackType.Success) {
  vibrate(type === NotificationFeedbackType.Success ? [10, 60, 18] : type === NotificationFeedbackType.Error ? [24, 50, 24, 50, 24] : 30);
}
