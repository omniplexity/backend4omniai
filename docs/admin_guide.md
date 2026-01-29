# Admin Guide

## Admin Bootstrapping

1. Create `admin` role user via `/auth/register` (requires invite) or SQL seed.
2. Log in and confirm `/auth/me` shows `role: admin`.
3. The sidebar shows an **Admin** toggle for authorized users.

## Users & Quotas

- `/admin/users` returns paginated users with quota metadata.
- Use inline toggles to enable/disable accounts (self-disable is blocked).
- Set `messages_per_day` / `tokens_per_day` to enforce quotas; leave `null` for unlimited.
- Quota updates log `user_quota_update` events and refresh resume hints for interrupted streams.

## Usage Monitoring

- `/admin/usage` provides daily totals (message/token counts). Filter by date range or query parameters.
- Usage data drives the frontend progress bars (percentage = used/limit).
- Export usage via CSV (see Phase D) for compliance reports.

## Audit Log

- `/admin/audit` shows chronological events. Filter by `action`, `target_type`, and date ranges.
- Actions include `login`, `logout`, `invite_create`, `user_disable`, `user_quota_update`, etc.
- Export to CSV for retention or investigations (see Phase D).

## Invites & Sessions

- Issue invites through `/admin/invites` and monitor uses.
- Disabling a user deletes their sessions automatically.
- Use `/auth/logout` to revoke current session; CSRF header required.

## Best Practices

- Rotate `SECRET_KEY` and provider API keys regularly; keep them in `.env` outside source control.
- Monitor `quota_blocks_total` to ensure limits match usage patterns.
- Review audit logs weekly for suspicious admin/user activity.
