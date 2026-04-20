from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Optional
import re

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db, login_manager


class TimestampMixin:
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class User(UserMixin, TimestampMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    phone = db.Column(db.String(30), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), default='customer', nullable=False)

    cart_items = db.relationship('CartItem', back_populates='user', cascade='all, delete-orphan')
    orders = db.relationship('Order', back_populates='user', cascade='all, delete-orphan')

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    @property
    def is_admin(self) -> bool:
        return self.role in {'admin', 'owner'}

    @property
    def is_owner(self) -> bool:
        return self.role == 'owner'

    @property
    def role_display(self) -> str:
        return {'owner': 'Dono', 'admin': 'Administrador', 'customer': 'Cliente'}.get(self.role, self.role)


@login_manager.user_loader
def load_user(user_id: str) -> Optional["User"]:
    return db.session.get(User, int(user_id))


class Category(TimestampMixin, db.Model):
    __tablename__ = 'categories'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)
    slug = db.Column(db.String(80), unique=True, nullable=False, index=True)
    products = db.relationship('Product', back_populates='category')


class Product(TimestampMixin, db.Model):
    __tablename__ = 'products'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, nullable=False)
    price = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    discount_price = db.Column(db.Numeric(10, 2), nullable=True)
    stock = db.Column(db.Integer, nullable=False, default=0)
    image_url = db.Column(db.String(255), nullable=True)
    image_filename = db.Column(db.String(255), nullable=True)
    active = db.Column(db.Boolean, default=True, nullable=False)
    product_type = db.Column(db.String(20), default='consumivel', nullable=False)
    weight_grams = db.Column(db.String(60), nullable=True)
    recipe_ingredients = db.Column(db.Text, nullable=True)
    size_info = db.Column(db.String(120), nullable=True)
    material = db.Column(db.String(200), nullable=True)

    category_id = db.Column(db.Integer, db.ForeignKey('categories.id'), nullable=False)
    category = db.relationship('Category', back_populates='products')

    order_items = db.relationship('OrderItem', back_populates='product')
    color_variants = db.relationship('ProductColorVariant', back_populates='product', cascade='all, delete-orphan', order_by='ProductColorVariant.id.asc()')

    @property
    def type_display(self) -> str:
        return 'Consumível' if self.product_type == 'consumivel' else 'Utensílio'

    @property
    def has_discount(self) -> bool:
        return self.discount_price is not None and Decimal(self.discount_price) > 0 and Decimal(self.discount_price) < Decimal(self.price)

    @property
    def effective_price(self) -> Decimal:
        return Decimal(self.discount_price) if self.has_discount else Decimal(self.price)

    @property
    def original_price(self) -> Decimal:
        return Decimal(self.price)

    @property
    def discount_percentage(self) -> int:
        if not self.has_discount or Decimal(self.price) <= 0:
            return 0
        percentage = ((Decimal(self.price) - Decimal(self.discount_price)) / Decimal(self.price) * Decimal('100'))
        return int(percentage.quantize(Decimal('1'), rounding=ROUND_HALF_UP))

    @property
    def bulk_discount_enabled(self) -> bool:
        return AppSetting.get_bool('bulk_discount_enabled', True)

    @property
    def bulk_discount_min_qty(self) -> int:
        return max(AppSetting.get_int('bulk_discount_min_qty', 3), 2)

    @property
    def bulk_discount_percent(self) -> Decimal:
        raw = AppSetting.get_decimal('bulk_discount_percent', Decimal('10'))
        if raw < 0:
            return Decimal('0')
        if raw > 99:
            return Decimal('99')
        return raw

    @property
    def bulk_discount_percent_display(self) -> str:
        value = self.bulk_discount_percent
        return str(int(value)) if value == value.to_integral() else str(value.normalize())

    @property
    def has_bulk_discount_offer(self) -> bool:
        return self.bulk_discount_enabled and self.bulk_discount_percent > 0 and self.bulk_discount_min_qty >= 2

    def has_bulk_discount_for(self, quantity: int) -> bool:
        return self.has_bulk_discount_offer and quantity >= self.bulk_discount_min_qty

    def unit_price_for_quantity(self, quantity: int) -> Decimal:
        base_price = Decimal(self.effective_price)
        if not self.has_bulk_discount_for(quantity):
            return base_price.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        multiplier = (Decimal('100') - self.bulk_discount_percent) / Decimal('100')
        return (base_price * multiplier).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    @property
    def main_image(self) -> str:
        if self.image_filename:
            return f'uploads/products/{self.image_filename}'
        if self.image_url:
            return self.image_url
        return 'https://via.placeholder.com/900x700?text=Produto'

    @property
    def ingredient_list(self) -> list[str]:
        if not self.recipe_ingredients:
            return []
        raw = self.recipe_ingredients.replace('\r', '\n')
        parts = [chunk.strip(' -•\t') for line in raw.split('\n') for chunk in line.split(',')]
        return [part for part in parts if part]

    @property
    def color_names(self) -> list[str]:
        return [variant.color_name for variant in self.color_variants if variant.color_name]

    @property
    def size_options(self) -> list[str]:
        if not self.size_info:
            return []
        normalized = self.size_info.replace('\r', '\n')
        normalized = re.sub(r'\s+e\s+', ',', normalized, flags=re.IGNORECASE)
        chunks = re.split(r'[\n,/;|]+', normalized)
        return [chunk.strip(' -•\t') for chunk in chunks if chunk.strip(' -•\t')]


class ProductColorVariant(TimestampMixin, db.Model):
    __tablename__ = 'product_color_variants'
    id = db.Column(db.Integer, primary_key=True)
    color_name = db.Column(db.String(80), nullable=False)
    color_hex = db.Column(db.String(7), nullable=True)
    image_url = db.Column(db.String(255), nullable=True)
    image_filename = db.Column(db.String(255), nullable=True)

    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    product = db.relationship('Product', back_populates='color_variants')

    @property
    def image_src(self) -> str:
        if self.image_filename:
            return f'uploads/products/{self.image_filename}'
        if self.image_url:
            return self.image_url
        return 'https://via.placeholder.com/600x450?text=Cor'

    @property
    def safe_color_hex(self) -> str:
        return self.color_hex if self.color_hex and self.color_hex.startswith('#') else '#111827'


class CartItem(TimestampMixin, db.Model):
    __tablename__ = 'cart_items'
    id = db.Column(db.Integer, primary_key=True)
    quantity = db.Column(db.Integer, default=1, nullable=False)
    selected_size = db.Column(db.String(60), nullable=True)
    selected_color_name = db.Column(db.String(80), nullable=True)
    selected_color_hex = db.Column(db.String(16), nullable=True)
    selected_color_image = db.Column(db.String(255), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    user = db.relationship('User', back_populates='cart_items')
    product = db.relationship('Product')

    @property
    def unit_price(self) -> Decimal:
        return self.product.unit_price_for_quantity(self.quantity)

    @property
    def subtotal(self) -> Decimal:
        return (Decimal(self.quantity) * self.unit_price).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    @property
    def base_subtotal(self) -> Decimal:
        return (Decimal(self.quantity) * Decimal(self.product.effective_price)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    @property
    def has_bulk_discount(self) -> bool:
        return self.product.has_bulk_discount_for(self.quantity)

    @property
    def bulk_discount_savings(self) -> Decimal:
        return (self.base_subtotal - self.subtotal).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


class Order(TimestampMixin, db.Model):
    __tablename__ = 'orders'
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), unique=True, nullable=True, index=True)
    subtotal = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    status = db.Column(db.String(20), default='pending', nullable=False)
    payment_method = db.Column(db.String(20), default='pix', nullable=False)
    payment_status = db.Column(db.String(20), default='pending', nullable=False)
    pix_payload = db.Column(db.Text, nullable=True)
    pix_qr_path = db.Column(db.String(255), nullable=True)
    receipt_text = db.Column(db.Text, nullable=True)
    whatsapp_receipt_link = db.Column(db.Text, nullable=True)
    seller_whatsapp_link = db.Column(db.Text, nullable=True)
    decision_note = db.Column(db.Text, nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    user = db.relationship('User', back_populates='orders')
    items = db.relationship('OrderItem', back_populates='order', cascade='all, delete-orphan')

    @property
    def status_display(self) -> str:
        return {
            'pending': 'Aguardando aprovação',
            'accepted': 'Aprovado',
            'rejected': 'Recusado',
            'completed': 'Finalizado',
            'cancelled': 'Cancelado pelo cliente',
        }.get(self.status, self.status)

    @property
    def payment_status_display(self) -> str:
        return {'pending': 'Pendente', 'paid': 'Pago'}.get(self.payment_status, self.payment_status)


class OrderItem(TimestampMixin, db.Model):
    __tablename__ = 'order_items'
    id = db.Column(db.Integer, primary_key=True)
    product_name = db.Column(db.String(150), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    selected_size = db.Column(db.String(60), nullable=True)
    selected_color_name = db.Column(db.String(80), nullable=True)
    selected_color_hex = db.Column(db.String(16), nullable=True)
    selected_color_image = db.Column(db.String(255), nullable=True)
    unit_price = db.Column(db.Numeric(10, 2), nullable=False)
    total_price = db.Column(db.Numeric(10, 2), nullable=False)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=True)
    order = db.relationship('Order', back_populates='items')
    product = db.relationship('Product', back_populates='order_items')


class AppSetting(TimestampMixin, db.Model):
    __tablename__ = 'app_settings'
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(80), unique=True, nullable=False)
    value = db.Column(db.Text, nullable=False)

    @classmethod
    def get_value(cls, key: str, default: str = '') -> str:
        item = cls.query.filter_by(key=key).first()
        return item.value if item else default

    @classmethod
    def set_value(cls, key: str, value: str) -> None:
        item = cls.query.filter_by(key=key).first()
        if item:
            item.value = value
        else:
            db.session.add(cls(key=key, value=value))

    @classmethod
    def get_bool(cls, key: str, default: bool = False) -> bool:
        raw = str(cls.get_value(key, 'true' if default else 'false')).strip().lower()
        return raw in {'1', 'true', 'sim', 'yes', 'on'}

    @classmethod
    def get_int(cls, key: str, default: int = 0) -> int:
        raw = str(cls.get_value(key, str(default))).strip()
        try:
            return int(raw)
        except Exception:
            return default

    @classmethod
    def get_decimal(cls, key: str, default: Decimal | str = '0') -> Decimal:
        fallback = Decimal(str(default))
        raw = str(cls.get_value(key, str(default))).strip().replace('.', '').replace(',', '.')
        try:
            return Decimal(raw)
        except (InvalidOperation, ValueError):
            return fallback
