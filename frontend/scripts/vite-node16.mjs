import crypto, { webcrypto } from 'node:crypto';

if (!globalThis.crypto?.getRandomValues) {
  globalThis.crypto = webcrypto;
}

if (!crypto.getRandomValues) {
  crypto.getRandomValues = webcrypto.getRandomValues.bind(webcrypto);
}

await import('../node_modules/vite/bin/vite.js');
