# Cleanup all temporary files
import os

files = [
    'app_backup_20260603.py', 'check_service_key_pyanywhere.py', 'fix_role_via_service_key.py',
    'get_service_key_from_pa.py', 'analyze_project.py', 'auto_fix_agent.py', 'comprehensive_tester.py',
    'debug_create_job.py', 'fix_test_issues.py', 'full_auto_agent.py', 'full_flask_tester.py',
    'manual_upload_v2.py', 'my_browser_agent.py', 'prepare_update.py', 'run_all_tests.py',
    'solution_rls.py', 'super_agent.py', 'ultimate_auto_agent.py', 'upload_final.py',
    'create_job_api.png', 'create_job_debug.png', 'create_job_fixed.png', 'create_job_js.png',
    'workers_diagnosis_2.png', 'workers_page.png', 'test_results.json', 'test_results_comprehensive.json',
    'test_results_final.json', 'APP_PY_CODE.txt', 'AUTO_AGENTS.md', 'AUTO_SOLUTION.md',
    'AUTO_TEST_GUIDE.md', 'auto_upload_pa.py', 'bash_commands.txt', 'check_after_login.py',
    'check_all_forms.py', 'check_all_links.py', 'check_all_requests.py', 'check_create_job.py',
    'check_created_jobs.py', 'check_encoding.py', 'check_env.py', 'check_form_action.py',
    'check_form_detailed.py', 'check_form_submit.py', 'check_jobs_api.py', 'check_js_fill.py',
    'check_links.py', 'check_login_detailed.py', 'check_login_error.py', 'check_login_form.py',
    'check_login_response.py', 'check_main_then_login.py', 'check_my_jobs.py', 'check_my_jobs_form.py',
    'check_new_employer_login.py', 'check_old_employer.py', 'check_old_employer_detailed.py',
    'check_pa_service_key.py', 'check_page.py', 'check_post_request.py', 'check_press_enter.py',
    'check_profile.py', 'check_profile_api.py', 'check_profile_api_direct.py', 'check_pythonanywhere.py',
    'check_redirect.py', 'check_register_form.py', 'check_role.py', 'check_role_detailed.py',
    'check_selector.py', 'check_server.py', 'check_server_session.py', 'check_server_simple.py',
    'check_service_key.py', 'check_session.py', 'check_test_admin.py', 'check_test_admin_role.py',
    'check_workers_page.py', 'commit_message.txt', 'commit_message2.txt', 'create_admin.py',
    'create_gist.py', 'create_job_direct.py', 'create_rls_policy.py', 'deploy_to_pa.py',
    'disable_rls.py', 'disable_rls_agent.py', 'disable_rls_and_update.py', 'disable_rls_direct.py',
    'FINAL_INSTRUCTION.md', 'FINAL_INSTRUCTION.txt', 'FINAL_INSTRUCTION_PA.md', 'FINAL_SUMMARY.md',
    'FINAL_TEST_REPORT.md', 'FINAL_WORK_REPORT.md', 'FIX_RECOMMENDATIONS.md', 'full_auto_agent.py',
    'GIT_UPDATE_INSTRUCTION.md', 'install_on_pa.py', 'INSTRUCTION.md', 'INSTRUCTION_PA_UPDATE.txt',
    'INSTRUCTION_UPDATE_PA.md', 'INSTRUCTION_UPLOAD.txt', 'INSTRUCTIONS_RLS.md', 'manual_upload.py',
    'manual_upload_v2.py', 'PA_BASH_COMMANDS.txt', 'PA_BASH_FINAL.txt', 'PA_BASH_FIND_PROJECT.txt',
    'PA_COMMANDS.txt', 'PA_FIND_PROJECT.txt', 'PA_GIT_COMMANDS.txt', 'PA_GIT_PULL.txt',
    'PA_SETUP_TOKEN.txt', 'PA_SETUP_TOKEN_DETAILED.txt', 'PA_STEP_BY_STEP.txt', 'PA_UPDATE_COMMANDS.txt',
    'PA_UPDATE_FINAL_INSTRUCTION.txt', 'PA_UPDATE_READY.txt', 'PA_UPDATE_SIMPLE.txt', 'PA_update_script.py',
    'PA_update_with_token.py', 'PA_UPLOAD_COMMANDS.txt', 'PLAN_TESTS.md', 'PROJECT_CONTEXT.md',
    'PROJECT_STATE.md', 'PYTHONANYWHERE_COMMANDS.txt', 'QUICK_UPDATE_INSTRUCTION.md',
    'README_TESTS.md', 'README_UPDATE.md', 'REFACTORING_REPORT_20260603.md', 'remote_update_role.py',
    'RUNNING_TESTS.md', 'send_to_pa.py', 'SIMPLE_UPLOAD.txt', 'SOLUTION_COMPLETE.md',
    'test_after_update.py', 'test_auth.py', 'test_create_job_js.py', 'test_pa.py',
    'test_profile_api.py', 'TEST_PROTOCOL.md', 'test_register_employer.py', 'TEST_REPORT.md',
    'test_rls_bypass.py', 'TEST_SCRIPTS.md', 'try_pa_api.py', 'try_pa_api_urllib.py',
    'update_pa.py', 'update_profile_role.py', 'update_profile_with_service_key.py',
    'update_role.py', 'update_role_direct.py', 'update_role_quick.py', 'update_role_via_flask.py',
    'upload_final.py', 'upload_final_v2.py', 'upload_pa_final.py', 'upload_via_api.py',
    'upload_via_console.py', 'upload_via_pa_api.py', 'cleanup_temp.py'
]

root = r'C:/Users/s.prokopenko/PycharmProjects/trudnik'
count = 0

for f in files:
    path = os.path.join(root, f)
    if os.path.exists(path):
        try:
            os.remove(path)
            count += 1
            print(f"Removed: {f}")
        except Exception as e:
            print(f"Error: {f} - {e}")

print(f"\nTotal removed: {count} files")
