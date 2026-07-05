"""Build combined migration 076-096."""
import os

MIGRATIONS_DIR = 'migrations'
OUTPUT_FILE = os.path.join(MIGRATIONS_DIR, '076-096_combined.sql')

files = [
    '076_lock_down_rpc.sql',
    '077_update_rls_app_role.sql',
    '077b_grant_service_role.sql',
    '078_drop_exec_sql.sql',
    '079_add_email_verification.sql',
    '080_register_user_sets_email_verified.sql',
    '081_normalize_emails.sql',
    '082_login_user_rehash.sql',
    '083_add_outbox_attempts.sql',
    '084_fix_withdraw_atomic.sql',
    '085_fix_restore_job_atomic.sql',
    '086_fix_delete_job_cascade.sql',
    '088_apply_job_check_expires.sql',
    '089_migrate_skills.sql',
    '090_admin_dashboard_rpc.sql',
    '091_unify_rpc_jsonb.sql',
    '092_fix_delete_user_cascade.sql',
    '093_add_updated_at_triggers.sql',
    '094_drop_shift_id.sql',
    '095_drop_religion_text.sql',
    '096_add_consented_at.sql',
]

with open(OUTPUT_FILE, 'w', encoding='utf-8') as out:
    out.write('-- =' * 40 + '\n')
    out.write('-- COMBINED MIGRATION: 076-096\n')
    out.write('-- Generated: 2026-07-05 for Amvera production\n')
    out.write('-- ALL 21 migrations + conflict resolution patch\n')
    out.write('-- USAGE: copy-paste into pgAdmin and execute\n')
    out.write('-- =' * 40 + '\n\n')
    out.write('BEGIN;\n\n')

    count = 0
    for fname in files:
        fpath = os.path.join(MIGRATIONS_DIR, fname)
        if not os.path.exists(fpath):
            print(f'SKIP: {fpath} not found')
            continue
        count += 1
        with open(fpath, 'r', encoding='utf-8') as f:
            content = f.read()
        out.write(f'\n-- ====== [{count}] {fname} ======\n')
        out.write(content)
        if not content.endswith('\n'):
            out.write('\n')

    # Append the conflict fix patch
    patch = os.path.join(MIGRATIONS_DIR, '099_fix_conflicts.sql')
    if os.path.exists(patch):
        count += 1
        with open(patch, 'r', encoding='utf-8') as f:
            content = f.read()
        out.write(f'\n-- ====== [{count}] 099_fix_conflicts.sql (PATCH) ======\n')
        out.write(content)
        if not content.endswith('\n'):
            out.write('\n')

    out.write('\nCOMMIT;\n')

size_kb = os.path.getsize(OUTPUT_FILE) / 1024
print(f'Done: {OUTPUT_FILE} ({size_kb:.1f} KB, {count} files merged)')
print(f'Ready for pgAdmin on Amvera Console.')
