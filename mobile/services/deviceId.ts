// Persistent anonymous device identifier for guest (unauthenticated) API requests
import * as SecureStore from 'expo-secure-store';
import AsyncStorage from '@react-native-async-storage/async-storage';
import * as Crypto from 'expo-crypto';

export class DeviceIdService {
  private static readonly STORAGE_KEY = 'device_id';
  private static cached: string | null = null;

  /**
   * Get the persisted device id, generating and storing one on first call.
   * Prefers SecureStore; falls back to AsyncStorage if SecureStore throws or
   * is unavailable on the current platform.
   */
  static async getDeviceId(): Promise<string> {
    if (this.cached) return this.cached;

    try {
      let id = await SecureStore.getItemAsync(this.STORAGE_KEY);
      if (!id) {
        id = Crypto.randomUUID();
        await SecureStore.setItemAsync(this.STORAGE_KEY, id);
      }
      this.cached = id;
      return id;
    } catch (error) {
      console.warn('⚠️ SecureStore unavailable for device id, falling back to AsyncStorage:', error);
    }

    let id = await AsyncStorage.getItem(this.STORAGE_KEY);
    if (!id) {
      id = Crypto.randomUUID();
      await AsyncStorage.setItem(this.STORAGE_KEY, id);
    }
    this.cached = id;
    return id;
  }
}

export async function getDeviceId(): Promise<string> {
  return DeviceIdService.getDeviceId();
}

export default DeviceIdService;
