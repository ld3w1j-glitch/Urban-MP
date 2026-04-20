from pathlib import Path

from flask import Flask, redirect, render_template, url_for
from sqlalchemy import inspect, text
from flask_login import current_user

from .admin.routes import bp as admin_bp
from .auth.routes import bp as auth_bp
from .config import Config
from .extensions import db, login_manager
from .runtime_store import get_store_offline_message, is_store_open_now
from .services.whatsapp_service import build_whatsapp_link
from .seeds import seed_all
from .store.routes import bp as store_bp


def run_runtime_migrations() -> None:
    inspector = inspect(db.engine)

    if 'products' in inspector.get_table_names():
        product_columns = {column['name'] for column in inspector.get_columns('products')}
        if 'discount_price' not in product_columns:
            with db.engine.begin() as connection:
                connection.execute(text('ALTER TABLE products ADD COLUMN discount_price NUMERIC(10, 2)'))

    if 'cart_items' in inspector.get_table_names():
        cart_columns = {column['name'] for column in inspector.get_columns('cart_items')}
        with db.engine.begin() as connection:
            if 'selected_size' not in cart_columns:
                connection.execute(text('ALTER TABLE cart_items ADD COLUMN selected_size VARCHAR(60)'))
            if 'selected_color_name' not in cart_columns:
                connection.execute(text('ALTER TABLE cart_items ADD COLUMN selected_color_name VARCHAR(80)'))
            if 'selected_color_hex' not in cart_columns:
                connection.execute(text('ALTER TABLE cart_items ADD COLUMN selected_color_hex VARCHAR(16)'))
            if 'selected_color_image' not in cart_columns:
                connection.execute(text('ALTER TABLE cart_items ADD COLUMN selected_color_image VARCHAR(255)'))

    if 'order_items' in inspector.get_table_names():
        order_item_columns = {column['name'] for column in inspector.get_columns('order_items')}
        with db.engine.begin() as connection:
            if 'selected_size' not in order_item_columns:
                connection.execute(text('ALTER TABLE order_items ADD COLUMN selected_size VARCHAR(60)'))
            if 'selected_color_name' not in order_item_columns:
                connection.execute(text('ALTER TABLE order_items ADD COLUMN selected_color_name VARCHAR(80)'))
            if 'selected_color_hex' not in order_item_columns:
                connection.execute(text('ALTER TABLE order_items ADD COLUMN selected_color_hex VARCHAR(16)'))
            if 'selected_color_image' not in order_item_columns:
                connection.execute(text('ALTER TABLE order_items ADD COLUMN selected_color_image VARCHAR(255)'))


def create_app() -> Flask:
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(Config)

    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    uploads_root = Path(app.root_path) / 'static' / 'uploads'
    (uploads_root / 'qr').mkdir(parents=True, exist_ok=True)
    (uploads_root / 'products').mkdir(parents=True, exist_ok=True)

    db.init_app(app)
    login_manager.init_app(app)

    @app.context_processor
    def inject_globals():
        from .models import AppSetting, CartItem
        cart_count = 0
        if current_user.is_authenticated:
            cart_count = sum(item.quantity for item in CartItem.query.filter_by(user_id=current_user.id).all())
        store_name = AppSetting.get_value('store_name', app.config['STORE_NAME'])
        support_number = AppSetting.get_value('whatsapp_number', '')
        support_message = f'Olá, preciso de suporte na {store_name}.'
        return {
            'store_name': store_name,
            'is_store_enabled': is_store_open_now(),
            'store_offline_message': get_store_offline_message(),
            'cart_count': cart_count,
            'custom_css_version': AppSetting.get_value('custom_css_version', '0'),
            'support_whatsapp_link': build_whatsapp_link(support_number, support_message),
        }

    @app.route('/')
    def home():
        if current_user.is_authenticated:
            return redirect(url_for('store.index'))
        return render_template('intro.html')

    app.register_blueprint(auth_bp)
    app.register_blueprint(store_bp)
    app.register_blueprint(admin_bp)

    with app.app_context():
        db.create_all()
        run_runtime_migrations()
        seed_all()

    return app
