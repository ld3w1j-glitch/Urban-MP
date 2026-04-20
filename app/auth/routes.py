from urllib.parse import urlsplit

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from ..extensions import db
from ..models import User

bp = Blueprint('auth', __name__)


def is_safe_next_url(target: str) -> bool:
    if not target:
        return False
    parts = urlsplit(target)
    return parts.scheme == '' and parts.netloc == ''


@bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('store.index'))
    next_url = request.args.get('next', '')
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        next_url = request.form.get('next', '')
        user = User.query.filter_by(email=email).first()
        if not user or not user.check_password(password):
            flash('E-mail ou senha inválidos.', 'danger')
            return render_template('auth/login.html', next_url=next_url)
        login_user(user)
        flash('Login realizado com sucesso.', 'success')
        if is_safe_next_url(next_url):
            return redirect(next_url)
        return redirect(url_for('store.index'))
    return render_template('auth/login.html', next_url=next_url)


@bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('store.index'))
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip().lower()
        phone = request.form.get('phone', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        if not all([name, email, phone, password, confirm_password]):
            flash('Preencha todos os campos.', 'danger')
            return render_template('auth/register.html')
        if password != confirm_password:
            flash('As senhas não conferem.', 'danger')
            return render_template('auth/register.html')
        if User.query.filter_by(email=email).first():
            flash('Já existe uma conta com este e-mail.', 'warning')
            return render_template('auth/register.html')
        user = User(name=name, email=email, phone=phone, role='customer')
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        flash('Cadastro realizado com sucesso. Agora faça login.', 'success')
        return redirect(url_for('auth.login'))
    return render_template('auth/register.html')


@bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Você saiu da conta.', 'info')
    return redirect(url_for('home'))
