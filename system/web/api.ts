import { createClient, type SupabaseClient } from '@supabase/supabase-js';

export const demo = import.meta.env.VITE_DEMO === 'true';
const url = import.meta.env.VITE_SUPABASE_URL;
const key = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY;
export const configured = demo || Boolean(url && key);
const operatorId = '00000000-0000-4000-8000-000000000001';

export class ApiError extends Error {
  constructor(message: string, public network = false) { super(message); }
}

export class Api {
  client?: SupabaseClient;
  userId = '';
  constructor(public operator: boolean) {
    if (!demo && configured) this.client = createClient(url, key, {
      auth: { storageKey: operator ? 'nys-operator-auth' : 'nys-participant-auth' },
    });
  }
  async init() {
    if (demo) {
      if (this.operator) this.userId = sessionStorage.getItem('nys-demo-operator') ?? '';
      else {
        this.userId = localStorage.getItem('nys-demo-participant') ?? crypto.randomUUID();
        localStorage.setItem('nys-demo-participant', this.userId);
      }
      return;
    }
    if (!this.client) throw new ApiError('NOT_CONFIGURED');
    const { data, error } = await this.client.auth.getSession();
    if (error) throw new ApiError(error.message, true);
    this.userId = data.session?.user.id ?? '';
    if (!this.operator && !this.userId) {
      const result = await this.client.auth.signInAnonymously();
      if (result.error) throw new ApiError(result.error.message, result.error.status === 0 || !result.error.status);
      this.userId = result.data.user?.id ?? '';
    }
  }
  async login(email: string, password: string) {
    if (demo) {
      this.userId = operatorId;
      sessionStorage.setItem('nys-demo-operator', this.userId);
    } else {
      const { data, error } = await this.client!.auth.signInWithPassword({ email, password });
      if (error) throw new ApiError(error.message);
      this.userId = data.user.id;
    }
  }
  async logout() {
    if (this.client) await this.client.auth.signOut();
    sessionStorage.removeItem('nys-demo-operator');
    this.userId = '';
  }
  async call<T>(name: string, args: Record<string, unknown> = {}): Promise<T> {
    let timeout: ReturnType<typeof setTimeout>;
    const request = async () => {
      try {
        if (demo) {
          const res = await fetch('/demo/rpc', {
            method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Demo-User': this.userId },
            body: JSON.stringify({ name, args }), signal: AbortSignal.timeout(10000),
          });
          if (res.status >= 500) throw new ApiError('SERVER_UNAVAILABLE', true);
          const body = await res.json();
          if (!res.ok) throw new ApiError(body.error ?? 'REQUEST_FAILED');
          return body.data as T;
        }
        const { data, error, status } = await this.client!.rpc(name, args);
        if (error) throw new ApiError(error.message, !status || status >= 500);
        return data as T;
      } catch (error) {
        if (error instanceof ApiError) throw error;
        throw new ApiError(error instanceof Error ? error.message : 'NETWORK', true);
      }
    };
    try {
      return await Promise.race([request(), new Promise<T>((_, reject) => {
        timeout = setTimeout(() => reject(new ApiError('TIMEOUT', true)), 11000);
      })]);
    } finally { clearTimeout(timeout!); }
  }
  subscribe(id: string | undefined, refresh: () => void) {
    if (!this.client) return () => {};
    const channel = this.client.channel(`state-${id ?? 'operator'}-${crypto.randomUUID()}`)
      .on('postgres_changes', { event: '*', schema: 'public', table: 'participants',
        ...(id ? { filter: `id=eq.${id}` } : {}) }, refresh)
      .subscribe((status) => { if (status === 'SUBSCRIBED') refresh(); });
    return () => { void this.client!.removeChannel(channel); };
  }
}
