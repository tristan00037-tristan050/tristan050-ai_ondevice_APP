/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_COLLECTOR_URL: string;
  readonly VITE_API_KEY: string;
  readonly VITE_TENANT: string;
  readonly VITE_PERMISSION?: 'read-only' | 'download';
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

