'use client';

import { useSyncExternalStore } from 'react';

const key = 'disastervision.browserAlerts';
const event = 'disastervision:browser-alerts';

function subscribe(callback: () => void) {
  window.addEventListener(event, callback);
  window.addEventListener('storage', callback);
  return () => { window.removeEventListener(event, callback); window.removeEventListener('storage', callback); };
}

function snapshot() {
  return window.localStorage.getItem(key) === 'enabled' && 'Notification' in window && Notification.permission === 'granted';
}

function save(enabled: boolean) {
  window.localStorage.setItem(key, enabled ? 'enabled' : 'disabled');
  window.dispatchEvent(new Event(event));
}

export function useBrowserAlerts() {
  const enabled = useSyncExternalStore(subscribe, snapshot, () => false);
  const enable = async () => {
    if (!('Notification' in window)) throw new Error('This browser does not support desktop notifications.');
    const permission = await Notification.requestPermission();
    if (permission !== 'granted') throw new Error('Browser notification permission was not granted.');
    save(true);
  };
  return { enabled, enable, disable: () => save(false) };
}
