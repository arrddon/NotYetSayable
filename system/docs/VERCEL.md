# Vercel deployment

Import GitHub repository `arrddon/NotYetSayable`, branch `main`.
Set Root Directory to `system`, Framework to Vite, Build Command to
`npm run build`, and Output Directory to `dist`.

Set these public build environment variables using `system/.env.example`:

- `VITE_SUPABASE_URL`
- `VITE_SUPABASE_PUBLISHABLE_KEY`
- `VITE_DEMO=false`

Do not copy `.env.local` or add service-role/OpenAI credentials to Vercel.
Only the static `dist` output is served. TD, Python and captures stay on the laptop.
The SPA rewrite supports direct links and refreshes on `/operator` and join routes.

After deployment, open `https://YOUR-DOMAIN/operator` on the operator phone,
sign in and create a session. Use that session's full UUID in TD with
`demo=False, mock=True`. Participants use the QR links created on this deployed
origin. Phones do not need to share the laptop's Wi-Fi; all devices need internet.
Check that deployment protection allows participants to open the production URL.

Deployment and physical phone/TD capture verification remain pending.
