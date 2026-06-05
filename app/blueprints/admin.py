from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from app.decorators import login_required, role_required
from app.utils import supabase_request

admin_bp = Blueprint('admin', __name__)


@admin_bp.route('/admin')
@login_required
@role_required('admin')
def admin_panel():
    # Fetch users with pending verification (original schema: verification_status)
    resp = supabase_request('GET',
        'profiles?verification_status=eq.pending&select=*')
    return render_template('admin.html', pending=resp.json() if resp.ok else [])


@admin_bp.route('/admin/approve/<user_id>', methods=['POST'])
@login_required
@role_required('admin')
def approve_employer(user_id):
    supabase_request('PATCH', f'profiles?id=eq.{user_id}',
        json={'verification_status': 'approved'})
    flash('Работодатель верифицирован', 'success')
    return redirect(url_for('admin.admin_panel'))


@admin_bp.route('/admin/reject/<user_id>', methods=['POST'])
@login_required
@role_required('admin')
def reject_employer(user_id):
    supabase_request('PATCH', f'profiles?id=eq.{user_id}',
        json={'verification_status': 'rejected'})
    flash('Верификация отклонена', 'warning')
    return redirect(url_for('admin.admin_panel'))
