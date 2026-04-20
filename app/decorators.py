from functools import wraps

from flask import flash, redirect, url_for
from flask_login import current_user

from .runtime_store import get_store_offline_message, is_store_open_now


def admin_required(view_func):
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash('Acesso restrito ao administrador.', 'danger')
            return redirect(url_for('store.index'))
        return view_func(*args, **kwargs)
    return wrapper


def owner_required(view_func):
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_owner:
            flash('Somente o dono da loja pode usar esta função.', 'danger')
            return redirect(url_for('admin.dashboard'))
        return view_func(*args, **kwargs)
    return wrapper


def store_enabled_required(view_func):
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        if current_user.is_authenticated and current_user.is_admin:
            return view_func(*args, **kwargs)
        if is_store_open_now():
            return view_func(*args, **kwargs)
        flash(get_store_offline_message(), 'warning')
        return redirect(url_for('store.offline'))
    return wrapper
