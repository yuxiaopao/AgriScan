import {Capacitor} from '@capacitor/core'
import {App} from '@capacitor/app'
import {Camera, CameraResultType, CameraSource} from '@capacitor/camera'

export function isNativeAndroid(): boolean {
  return Capacitor.isNativePlatform() && Capacitor.getPlatform() === 'android'
}

/** Ask Android before requesting the WebView camera stream; browsers use getUserMedia's own prompt. */
export async function ensureCameraPermission(): Promise<void> {
  if (!Capacitor.isNativePlatform()) return
  let permissions = await Camera.checkPermissions()
  if (permissions.camera !== 'granted') {
    permissions = await Camera.requestPermissions({permissions: ['camera']})
  }
  if (permissions.camera !== 'granted') {
    throw new Error('未获得相机权限。请在手机系统设置中允许“禾观”使用相机，再重试。')
  }
}

/** Open Android's camera activity; cancelling does not create an empty detection. */
export async function captureNativePhoto(): Promise<File | null> {
  if (!Capacitor.isNativePlatform()) return null
  await ensureCameraPermission()
  try {
    const photo = await Camera.getPhoto({
      source: CameraSource.Camera,
      resultType: CameraResultType.Uri,
      quality: 90,
      correctOrientation: true,
      saveToGallery: false,
      width: 2048,
      height: 2048,
    })
    if (!photo.webPath) throw new Error('未能读取拍摄的照片，请重试。')
    const response = await fetch(photo.webPath)
    if (!response.ok) throw new Error('未能读取拍摄的照片，请重试。')
    const blob = await response.blob()
    const extension = photo.format === 'png' ? 'png' : 'jpg'
    return new File([blob], `禾观拍摄-${Date.now()}.${extension}`, {type: blob.type || `image/${extension === 'jpg' ? 'jpeg' : extension}`})
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error)
    if (/cancelled|canceled|cancel|取消/i.test(message)) return null
    throw error
  }
}

export async function registerNativeBackButton(
  handler: (event: {canGoBack: boolean}) => void,
): Promise<() => void> {
  if (!isNativeAndroid()) return () => {}
  const listener = await App.addListener('backButton', handler)
  return () => {void listener.remove()}
}

export async function minimizeNativeApp(): Promise<void> {
  if (isNativeAndroid()) await App.minimizeApp()
}
