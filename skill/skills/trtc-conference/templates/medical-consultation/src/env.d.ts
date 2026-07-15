/// <reference types="vite/client" />

declare module '*.vue' {
  import type { DefineComponent } from 'vue';
  const component: DefineComponent<
    Record<string, never>,
    Record<string, never>,
    any
  >;
  export default component;
}

// Vue 3.3+ Composition API global types
declare global {
  function defineProps<T extends Record<string, any>>(
    props: T
  ): T;
  function defineEmits<T extends Record<string, any>>(
    emits: T
  ): T;
  function defineModel<T = any>(
    name?: string,
    options?: any
  ): [any, (value: T) => void];
  function defineExpose<T extends Record<string, any>>(
    expose: T
  ): void;
  function withDefaults<T extends Record<string, any>>(
    props: T,
    defaults: Record<string, any>
  ): T;
}
