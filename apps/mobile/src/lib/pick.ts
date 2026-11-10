// Choosing a file on the phone: a picture or a video from Photos, or anything (a sound) from Files.
import * as DocumentPicker from 'expo-document-picker';
import * as ImagePicker from 'expo-image-picker';

export type PhoneFile = { uri: string; name: string; type: string; kind: 'image' | 'video' | 'audio' | 'file' };

const kindOf = (type: string): PhoneFile['kind'] =>
  type.startsWith('image/') ? 'image' : type.startsWith('video/') ? 'video' : type.startsWith('audio/') ? 'audio' : 'file';

/** A picture or a video from Photos (`kind` narrows it), or null when the user backs out. */
export async function fromPhotos(kind?: 'image' | 'video'): Promise<PhoneFile | null> {
  const permission = await ImagePicker.requestMediaLibraryPermissionsAsync();
  if (!permission.granted) throw new Error('Scene.ai needs permission to read your photos.');
  const picked = await ImagePicker.launchImageLibraryAsync({
    mediaTypes: kind === 'image' ? ['images'] : kind === 'video' ? ['videos'] : ['images', 'videos'],
    quality: 0.92,
  });
  if (picked.canceled || !picked.assets[0]) return null;
  const asset = picked.assets[0];
  const type = asset.mimeType ?? (asset.type === 'video' ? 'video/mp4' : 'image/jpeg');
  const name = asset.fileName ?? `${asset.type === 'video' ? 'video' : 'photo'}-${Date.now()}.${type.split('/')[1] ?? 'jpg'}`;
  return { uri: asset.uri, name, type, kind: kindOf(type) };
}

/** A picture with the camera, or null. */
export async function fromCamera(): Promise<PhoneFile | null> {
  const permission = await ImagePicker.requestCameraPermissionsAsync();
  if (!permission.granted) throw new Error('Scene.ai needs permission to use the camera.');
  const taken = await ImagePicker.launchCameraAsync({ quality: 0.92 });
  if (taken.canceled || !taken.assets[0]) return null;
  const asset = taken.assets[0];
  const type = asset.mimeType ?? 'image/jpeg';
  return { uri: asset.uri, name: asset.fileName ?? `photo-${Date.now()}.jpg`, type, kind: kindOf(type) };
}

/** Any file from the phone's Files (a sound, a script), or null. `types` like ['audio/*']. */
export async function fromFiles(types: string[] = ['*/*']): Promise<PhoneFile | null> {
  const picked = await DocumentPicker.getDocumentAsync({ type: types, copyToCacheDirectory: true });
  if (picked.canceled || !picked.assets[0]) return null;
  const asset = picked.assets[0];
  const type = asset.mimeType ?? 'application/octet-stream';
  return { uri: asset.uri, name: asset.name, type, kind: kindOf(type) };
}
