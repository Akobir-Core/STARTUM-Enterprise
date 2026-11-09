/* STARTUM public-shell service worker.
 * Authenticated areas, APIs, private records and user-generated uploads are never cached.
 */
'use strict';
const CACHE_NAME = 'startum-public-v2';
const OFFLINE_URL = './offline.html';
const PRECACHE = [
  './',
  './index.html',
  './privacy.html',
  './style.css',
  './lightmode-aeline.css',
  './design-system.css',
  './premium-experience.css',
  './script.js',
  './startum.config.js',
  './site.webmanifest',
  './assets/favicon.svg',
  './assets/icon-192.png',
  './assets/icon-512.png',
  './assets/images/startum-day-hero.webp',
  './assets/images/startum-dark-hero.webp',
  './offline.html'
];
const PRIVATE_PATH = /\/(?:api|admin|auth|private|sessions?|uploads|media\/private)(?:\/|$)/i;
const FORBIDDEN_FILE = /\.(?:db|sqlite3?|env|log|pem|key)$/i;

self.addEventListener('install', (event) => {
  event.waitUntil((async () => {
    const cache = await caches.open(CACHE_NAME);
    await Promise.all(PRECACHE.map(async (path) => {
      try {
        const response = await fetch(path, { cache: 'reload', credentials: 'omit' });
        if (response.ok && response.type !== 'opaque') await cache.put(path, response);
      } catch (_) { /* the online page remains available even if one optional asset is offline */ }
    }));
    await self.skipWaiting();
  })());
});

self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    const keys = await caches.keys();
    await Promise.all(keys.filter((key) => key.startsWith('startum-public-') && key !== CACHE_NAME).map((key) => caches.delete(key)));
    await self.clients.claim();
  })());
});

self.addEventListener('fetch', (event) => {
  const request = event.request;
  if (request.method !== 'GET') return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin || url.search || PRIVATE_PATH.test(url.pathname) || FORBIDDEN_FILE.test(url.pathname)) return;

  // Only public homepage and privacy page receive safe offline navigation fallbacks.
  if (request.mode === 'navigate') {
    const isHome = url.pathname === '/' || url.pathname.endsWith('/index.html');
    const isPrivacy = url.pathname.endsWith('/privacy.html');
    if (!isHome && !isPrivacy) return;
    const publicDocument = isPrivacy ? './privacy.html' : './index.html';
    event.respondWith((async () => {
      try {
        const response = await fetch(request);
        if (response.ok) {
          const cache = await caches.open(CACHE_NAME);
          await cache.put(publicDocument, response.clone());
        }
        return response;
      } catch (_) {
        return (await caches.match(publicDocument)) || (isHome ? await caches.match(OFFLINE_URL) : Response.error());
      }
    })());
    return;
  }

  const path = url.pathname;
  // Cache only the known public frontend shell and supplied public images.
  // User uploads and arbitrary media paths are network-only by default.
  const isShellAsset = /\/(?:privacy\.html|style\.css|lightmode-aeline\.css|design-system\.css|premium-experience\.css|script\.js|startum\.config\.js|site\.webmanifest|offline\.html)$/i.test(path);
  const isPublicBrandAsset = /\/assets\/(?:favicon\.svg|icon-(?:192|512)\.png|images\/[a-z0-9._-]+\.(?:svg|png|webp|jpe?g))$/i.test(path);
  if (!isShellAsset && !isPublicBrandAsset) return;

  event.respondWith((async () => {
    const cache = await caches.open(CACHE_NAME);
    const cached = await cache.match(request);
    const network = fetch(request).then((response) => {
      if (response.ok && response.type !== 'opaque') cache.put(request, response.clone());
      return response;
    });
    return cached || network;
  })());
});
