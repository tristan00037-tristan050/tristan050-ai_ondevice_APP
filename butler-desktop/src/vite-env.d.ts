/// <reference types="vite/client" />

declare module '*.svg' {
  const src: string;
  export default src;
}

// vite.config.ts 의 define 으로 빌드 시점에 주입되는 전역 상수
declare const __BUILD_COMMIT__: string;
declare const __BUILD_BRANCH__: string;
declare const __BUILD_CHANNEL__: 'production' | 'development';
declare const __BUILD_CONTEXT_DIGEST__: string;
declare const __APP_VERSION__: string;
