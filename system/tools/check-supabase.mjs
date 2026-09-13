// Read-only connection check. Does not create users or modify the database.
process.loadEnvFile('.env.local');
const url = process.env.VITE_SUPABASE_URL;
const headers = { apikey: process.env.VITE_SUPABASE_PUBLISHABLE_KEY };
for (const path of ['/auth/v1/settings', '/rest/v1/participants?select=id&limit=0']) {
  const response = await fetch(url + path, { headers, signal: AbortSignal.timeout(10000) });
  const data = await response.json();
  console.log(JSON.stringify({
    endpoint: path.split('?')[0], status: response.status,
    ...(path.includes('/auth/') ? { anonymous_sign_in: data.external?.anonymous_users ?? data.anonymous_users_enabled ?? 'not_reported' }
      : { code: data.code ?? null, message: data.message ?? null }),
  }));
}
