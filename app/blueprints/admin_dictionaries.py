"""Админ-панель: справочники (навыки, вероисповедания).

Выделен из app/blueprints/admin.py (задача 4-5).
"""

from flask import Blueprint, current_app, jsonify, request

from app.decorators import login_required, admin_required, validate_uuid
from app.utils import postgrest_admin_request, postgrest_rpc, is_circuit_open
from app.utils.helpers import assert_postgrest_ok
from app.utils.errors import safe_error_message

admin_dictionaries_bp = Blueprint('admin_dictionaries', __name__, url_prefix='/admin')


# ═══════════════════════════════════════════════════════════════
# Навыки
# ═══════════════════════════════════════════════════════════════

@admin_dictionaries_bp.route('/skills', methods=['GET'])
@login_required
@admin_required
def get_skills():
    resp = postgrest_admin_request('GET', 'skills?select=*&order=sort_order.asc,name.asc')
    if not resp.ok:
        resp = postgrest_admin_request('GET', 'skills?select=*&order=name.asc')
    return jsonify({'success': True, 'skills': resp.json() if resp.ok else []})


@admin_dictionaries_bp.route('/skills', methods=['POST'])
@login_required
@admin_required
def add_skill():
    try:
        data = request.get_json(silent=True) or {}
        name = (request.form.get('name', '') or data.get('name', '') or '').strip()
        if not name:
            return jsonify({'success': False, 'error': 'Название навыка не может быть пустым'})
        max_order = 0
        existing = postgrest_admin_request('GET', 'skills?select=sort_order&order=sort_order.desc&limit=1')
        if not existing.ok:
            existing = postgrest_admin_request('GET', 'skills?select=id&order=name.desc&limit=1')
        if existing.ok and existing.json():
            item = existing.json()[0] if existing.json() else {}
            max_order = item.get('sort_order', 0)
        resp = postgrest_admin_request('POST', 'skills', json={'name': name, 'sort_order': max_order + 1})
        if resp.ok:
            return jsonify({'success': True})
        current_app.logger.error('add_skill: PostgREST error (status %s): %s', resp.status_code, resp.text)
        return jsonify({'success': False, 'error': safe_error_message(resp, 'Ошибка при добавлении навыка')})
    except Exception as e:
        current_app.logger.exception('add_skill: unexpected error')
        return jsonify({'success': False, 'error': str(e)})


@admin_dictionaries_bp.route('/skills/reorder', methods=['POST'])
@login_required
@admin_required
def reorder_skills():
    data = request.get_json() or {}
    items = data.get('items', [])
    if not items:
        return jsonify({'success': False, 'error': 'items required'}), 400
    for item in items:
        resp = postgrest_admin_request('PATCH', f'skills?id=eq.{item["id"]}', json={'sort_order': item['sort_order']})
        assert_postgrest_ok(resp, f'пересортировка навыка {item["id"]}')
    return jsonify({'success': True})


@admin_dictionaries_bp.route('/skills/<skill_id>', methods=['PUT'])
@login_required
@admin_required
@validate_uuid('skill_id')
def update_skill(skill_id):
    try:
        data = request.get_json(silent=True) or {}
        if not data.get('name'):
            data['name'] = request.form.get('name', request.form.get('skill_name', '')).strip()
        name = (data.get('name', '')).strip()
        if not name:
            return jsonify({'success': False, 'error': 'Name required'}), 400
        resp = postgrest_admin_request('PATCH', f'skills?id=eq.{skill_id}', json={'name': name})
        if not resp.ok:
            current_app.logger.error(
                'update_skill(id=%s): PostgREST error (status %s): %s',
                skill_id, resp.status_code, resp.text
            )
            return jsonify({'success': False, 'error': safe_error_message(resp, 'Ошибка обновления навыка')}), resp.status_code or 400
        return jsonify({'success': True})
    except Exception as e:
        current_app.logger.exception('update_skill(id=%s): unexpected error', skill_id)
        return jsonify({'success': False, 'error': str(e)}), 500


@admin_dictionaries_bp.route('/skills/<skill_id>', methods=['DELETE'])
@login_required
@admin_required
@validate_uuid('skill_id')
def delete_skill(skill_id):
    rpc_result = postgrest_rpc('delete_skill_cascade', {'p_skill_id': skill_id}, use_admin=True)
    if not rpc_result.ok:
        current_app.logger.error(
            'delete_skill RPC: failed for %s: status=%s text=%s',
            skill_id, rpc_result.status_code, (rpc_result.text or '')[:200]
        )
        return jsonify({'success': False, 'error': f'RPC failed: {rpc_result.text}'}), 500
    return jsonify({'success': True})


@admin_dictionaries_bp.route('/bulk-delete-skills', methods=['POST'])
@login_required
@admin_required
def bulk_delete_skills():
    data = request.get_json(silent=True) or {}
    skill_ids = data.get('skill_ids', [])

    if not isinstance(skill_ids, list) or len(skill_ids) == 0:
        return jsonify({'deleted': 0, 'failed': 0, 'errors': ['No skill_ids provided']}), 400
    if len(skill_ids) > 50:
        return jsonify({'deleted': 0, 'failed': len(skill_ids), 'errors': ['Max 50 skills per request']}), 400

    ids_filter = f'id=in.({",".join(str(sid) for sid in skill_ids)})'
    skill_id_filter = f'skill_id=in.({",".join(str(sid) for sid in skill_ids)})'

    errors = []
    failed = 0

    resp_user = postgrest_admin_request('DELETE', f'user_skills?{skill_id_filter}')
    if not resp_user.ok:
        errors.append('user_skills cleanup failed')
        failed += 1

    resp_job = postgrest_admin_request('DELETE', f'job_skills?{skill_id_filter}')
    if not resp_job.ok:
        errors.append('job_skills cleanup failed')
        failed += 1

    resp = postgrest_admin_request('DELETE', f'skills?{ids_filter}')

    if not resp.ok:
        return jsonify({
            'deleted': 0,
            'failed': len(skill_ids),
            'errors': errors + [safe_error_message(resp, 'Ошибка удаления навыков')]
        }), 500

    deleted = len(resp.json()) if isinstance(resp.json(), list) else 0
    missing = len(skill_ids) - deleted
    if missing > 0:
        errors.append(f'{missing} skill(s) not found in database')

    return jsonify({'deleted': deleted, 'failed': failed, 'errors': errors})


# ═══════════════════════════════════════════════════════════════
# Вероисповедания
# ═══════════════════════════════════════════════════════════════

@admin_dictionaries_bp.route('/religions', methods=['GET'])
@login_required
@admin_required
def get_religions():
    resp = postgrest_admin_request('GET', 'religions?select=*&order=sort_order.asc,name.asc')
    if not resp.ok:
        resp = postgrest_admin_request('GET', 'religions?select=*&order=name.asc')
    return jsonify({'success': True, 'religions': resp.json() if resp.ok else []})


@admin_dictionaries_bp.route('/religions', methods=['POST'])
@login_required
@admin_required
def add_religion():
    try:
        data = request.get_json(silent=True) or {}
        name = (request.form.get('name', '') or data.get('name', '') or '').strip()
        if not name:
            return jsonify({'success': False, 'error': 'Название вероисповедания не может быть пустым'})
        max_order = 0
        existing = postgrest_admin_request('GET', 'religions?select=sort_order&order=sort_order.desc&limit=1')
        if not existing.ok:
            if is_circuit_open(existing):
                return jsonify({'success': False, 'error': 'Сервис временно недоступен. Попробуйте позже.'})
            current_app.logger.warning('add_religion: GET max_order failed (status %s), using default 0', existing.status_code)
        elif existing.json():
            item = existing.json()[0] if existing.json() else {}
            max_order = item.get('sort_order', 0)

        resp = postgrest_admin_request('POST', 'religions', json={'name': name, 'sort_order': max_order + 1})
        if resp.ok:
            return jsonify({'success': True})
        if is_circuit_open(resp):
            return jsonify({'success': False, 'error': 'Сервис временно недоступен. Попробуйте позже.'})
        current_app.logger.error('add_religion: PostgREST error (status %s): %s', resp.status_code, resp.text)
        return jsonify({'success': False, 'error': safe_error_message(resp, 'Ошибка при добавлении вероисповедания')})
    except Exception as e:
        current_app.logger.exception('add_religion: unexpected error')
        return jsonify({'success': False, 'error': str(e)})


@admin_dictionaries_bp.route('/religions/reorder', methods=['POST'])
@login_required
@admin_required
def reorder_religions():
    data = request.get_json() or {}
    items = data.get('items', [])
    if not items:
        return jsonify({'success': False, 'error': 'items required'}), 400
    for item in items:
        resp = postgrest_admin_request('PATCH', f'religions?id=eq.{item["id"]}', json={'sort_order': item['sort_order']})
        assert_postgrest_ok(resp, f'пересортировка вероисповедания {item["id"]}')
    return jsonify({'success': True})


@admin_dictionaries_bp.route('/religions/<religion_id>', methods=['PUT'])
@login_required
@admin_required
@validate_uuid('religion_id')
def update_religion(religion_id):
    try:
        data = request.get_json(silent=True) or {}
        if not data.get('name'):
            data['name'] = request.form.get('name', request.form.get('religion_name', '')).strip()
        name = (data.get('name', '')).strip()
        if not name:
            return jsonify({'success': False, 'error': 'Name required'}), 400
        resp = postgrest_admin_request('PATCH', f'religions?id=eq.{religion_id}', json={'name': name})
        if not resp.ok:
            current_app.logger.error(
                'update_religion(id=%s): PostgREST error (status %s): %s',
                religion_id, resp.status_code, resp.text
            )
            return jsonify({'success': False, 'error': safe_error_message(resp, 'Ошибка обновления вероисповедания')}), resp.status_code or 400
        return jsonify({'success': True})
    except Exception as e:
        current_app.logger.exception('update_religion(id=%s): unexpected error', religion_id)
        return jsonify({'success': False, 'error': str(e)}), 500


@admin_dictionaries_bp.route('/religions/<religion_id>', methods=['DELETE'])
@login_required
@admin_required
@validate_uuid('religion_id')
def delete_religion(religion_id):
    nullify_resp = postgrest_admin_request('PATCH', f'profiles?religion_id=eq.{religion_id}', json={'religion_id': None})
    if not nullify_resp.ok:
        current_app.logger.warning(
            'delete_religion: failed to nullify religion_id in profiles for religion %s: status=%s',
            religion_id, nullify_resp.status_code
        )
    resp = postgrest_admin_request('DELETE', f'religions?id=eq.{religion_id}')
    return jsonify({'success': resp.ok})


@admin_dictionaries_bp.route('/bulk-delete-religions', methods=['POST'])
@login_required
@admin_required
def bulk_delete_religions():
    data = request.get_json(silent=True) or {}
    religion_ids = data.get('religion_ids', [])

    if not isinstance(religion_ids, list) or len(religion_ids) == 0:
        return jsonify({'deleted': 0, 'failed': 0, 'errors': ['No religion_ids provided']}), 400
    if len(religion_ids) > 50:
        return jsonify({'deleted': 0, 'failed': len(religion_ids), 'errors': ['Max 50 religions per request']}), 400

    ids_filter = f'id=in.({",".join(str(rid) for rid in religion_ids)})'
    religion_id_filter = f'religion_id=in.({",".join(str(rid) for rid in religion_ids)})'

    errors = []
    failed = 0

    nullify_resp = postgrest_admin_request('PATCH', f'profiles?{religion_id_filter}', json={'religion_id': None})
    if not nullify_resp.ok:
        errors.append('profiles nullify failed')
        failed += 1

    resp = postgrest_admin_request('DELETE', f'religions?{ids_filter}')

    if not resp.ok:
        return jsonify({
            'deleted': 0,
            'failed': len(religion_ids),
            'errors': errors + [safe_error_message(resp, 'Ошибка удаления вероисповеданий')]
        }), 500

    deleted = len(resp.json()) if isinstance(resp.json(), list) else 0
    missing = len(religion_ids) - deleted
    if missing > 0:
        errors.append(f'{missing} religion(s) not found in database')

    return jsonify({'deleted': deleted, 'failed': failed, 'errors': errors})