# Gmail OAuth — Platform Deployment Setup

**Audience:** Platform operators / DevOps. **Not** tenant users.

TruckERP uses a **platform-owned** Google OAuth app. The platform configures Google Cloud once; tenant users never see or configure credentials. Tenant flow is: Admin → Email → Connect with Google → Approve → Connected.

---

## App owner vs tenant user

| Who | Does what |
|-----|-----------|
| **Platform / app owner** | Creates Google Cloud project, OAuth app, client ID/secret. Adds redirect URIs. Sets env vars. Done once per deployment. |
| **Tenant user** | Opens Admin → Email, clicks Connect with Google, approves on Google consent screen, returns connected. No Google Cloud access required. |

Tenant users are **never** asked to create their own Google API credentials or go to Google Cloud Console.

---

## Developer / deployment setup

Perform these steps **once** when deploying TruckERP. Tenants do not perform these steps.

### 1. Google Cloud Console

- Create or select a Google Cloud project
- APIs & Services → Enabled APIs → Enable **Gmail API**

### 2. OAuth consent screen

- Configure OAuth consent screen (External for multi-tenant)
- Add scopes: `gmail.readonly`, `userinfo.email`

### 3. OAuth 2.0 Client ID

- APIs & Services → Credentials → Create Credentials → OAuth client ID
- Application type: Web application
- Authorized redirect URIs (one fixed platform URL; no wildcards):
  - `https://truckerp.me/api/v1/admin/email-config/gmail/callback`
  - For local dev: `http://localhost/api/v1/admin/email-config/gmail/callback` (or `https://truckerp.me/...` if testing on deployed host)

### 4. Environment variables

- `GOOGLE_CLIENT_ID` — OAuth client ID (from step 3)
- `GOOGLE_CLIENT_SECRET` — OAuth client secret (from step 3)

**SSM (production):** Add to `/truckerp/<env>/platform/`:

```bash
aws ssm put-parameter --name "/truckerp/prod/platform/GOOGLE_CLIENT_ID" \
  --value "YOUR_CLIENT_ID.apps.googleusercontent.com" --type SecureString --overwrite

aws ssm put-parameter --name "/truckerp/prod/platform/GOOGLE_CLIENT_SECRET" \
  --value "YOUR_CLIENT_SECRET" --type SecureString --overwrite
```

Restart the API after adding. See `docs/secrets.md` for details.

---

## Scopes

- `https://www.googleapis.com/auth/gmail.readonly` — read messages for inbox
- `https://www.googleapis.com/auth/userinfo.email` — display connected account

---

## Tenant user flow (no setup required)

1. Tenant admin opens Admin → Email Configuration
2. Clicks **Connect with Google**
3. Redirects to Google consent screen
4. Approves access
5. Returns to TruckERP with primary mailbox connected

No Google Cloud Console, no API credentials, no technical setup.
