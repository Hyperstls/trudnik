# Supabase Linter Warnings

- **Дата:** 2026-06-11
- **Источник:** Supabase Database Linter (Security Advisor)
- **Статус:** После миграций `015`–`019`
- **Ссылки на remediation:** колонка `remediation`

| name | title | level | categories | detail | status |
|------|-------|-------|------------|--------|--------|
| ~~`rls_disabled_in_public`~~ | ~~RLS Disabled~~ | ~~ERROR~~ | SECURITY | ~~`public.spatial_ref_sys`~~ | ✅ **FIXED** — `018_fix_spatial_ref_sys_rls.sql` |
| `extension_in_public` | Extension in Public | WARN | SECURITY | Расширение `postgis` в public-схеме | ❌ **IGNORE** — PostGIS обязателен в `public` для near by search |
| `extension_in_public` | Extension in Public | WARN | SECURITY | Расширение `cube` в public-схеме | ❌ **IGNORE** — зависимость earthdistance |
| `extension_in_public` | Extension in Public | WARN | SECURITY | Расширение `earthdistance` в public-схеме | ❌ **IGNORE** — используется функциями поиска по городу |
| `public_bucket_allows_listing` | Bucket Listing | WARN | SECURITY | Bucket `avatars` — широкая SELECT политика | ✅ **FIXED** — `019_fix_security_warnings.sql` |
| `public_bucket_allows_listing` | Bucket Listing | WARN | SECURITY | Bucket `jobs` — широкая SELECT политика | ✅ **FIXED** — `019_fix_security_warnings.sql` |
| `public_bucket_allows_listing` | Bucket Listing | WARN | SECURITY | Bucket `verification-docs` SELECT политика | ✅ **FIXED** — `016_fix_supabase_warnings.sql` |
| ~~`anon_security_definer_function_executable`~~ | Public Can Execute | WARN | SECURITY | ~~`execute_sql` — критичная уязвимость~~ | ✅ **FIXED** — функция удалена в `019` |
| ~~`anon_security_definer_function_executable`~~ | Public Can Execute | WARN | SECURITY | ~~`handle_new_user`~~ | ✅ **FIXED** — EXECUTE revoked в `019` |
| ~~`anon_security_definer_function_executable`~~ | Public Can Execute | WARN | SECURITY | ~~`st_estimatedextent` (PostGIS)~~ | ✅ **FIXED** — EXECUTE revoked в `019` |
| ~~`authenticated_security_definer_function_executable`~~ | Auth Can Execute | WARN | SECURITY | ~~`execute_sql` — критичная уязвимость~~ | ✅ **FIXED** — функция удалена в `019` |
| ~~`authenticated_security_definer_function_executable`~~ | Auth Can Execute | WARN | SECURITY | ~~`handle_new_user`~~ | ✅ **FIXED** — EXECUTE revoked в `019` |
| ~~`authenticated_security_definer_function_executable`~~ | Auth Can Execute | WARN | SECURITY | ~~`st_estimatedextent` (PostGIS)~~ | ✅ **FIXED** — EXECUTE revoked в `019` |
| `auth_leaked_password_protection` | Leaked Password Protection | WARN | SECURITY | Защита от скомпрометированных паролей выключена | 🔧 **Включить вручную** — Auth → Settings → Leaked Password Protection |

## Инструкция: включить Leaked Password Protection

1. Supabase Dashboard → **Authentication** → **Settings**
2. Найти **Leaked Password Protection**
3. Включить тумблер (использует HaveIBeenPwned.org)
