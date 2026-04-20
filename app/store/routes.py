from __future__ import annotations

from decimal import Decimal
import secrets

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from ..decorators import store_enabled_required
from ..extensions import db
from ..models import AppSetting, CartItem, Category, Order, OrderItem, Product
from ..runtime_store import get_store_offline_message
from ..services.receipt_service import format_brl
from ..services.whatsapp_service import build_customer_status_message, build_owner_order_message, build_whatsapp_link

bp = Blueprint('store', __name__)

STATUS_BADGES = {
    'pending': 'badge badge-warning',
    'accepted': 'badge',
    'rejected': 'badge badge-danger-soft',
    'completed': 'badge badge-success-soft',
    'cancelled': 'badge badge-danger-soft',
}


def _public_base_url() -> str:
    configured = current_app.config.get('PUBLIC_BASE_URL', '').strip()
    if configured:
        return configured.rstrip('/')
    return request.url_root.rstrip('/')


def customer_whatsapp_link(order: Order) -> str:
    store_name = AppSetting.get_value('store_name', current_app.config['STORE_NAME'])
    return build_whatsapp_link(order.user.phone, build_customer_status_message(store_name, order))


def generate_order_code() -> str:
    return f'PED-{secrets.token_hex(3).upper()}'


def _normalize_selected_size(product: Product, raw_size: str | None) -> str | None:
    selected_size = (raw_size or '').strip()
    options = product.size_options
    if not options:
        return None
    if not selected_size:
        raise ValueError('Escolha um tamanho para continuar.')
    if selected_size not in options:
        raise ValueError('O tamanho selecionado não é válido para este produto.')
    return selected_size


def _normalize_selected_color(product: Product, raw_color_name: str | None) -> tuple[str | None, str | None, str | None]:
    selected_color_name = (raw_color_name or '').strip()
    variants = list(product.color_variants or [])
    if not variants:
        return None, None, None

    if not selected_color_name:
        raise ValueError('Escolha uma cor para continuar.')

    for variant in variants:
        if variant.color_name == selected_color_name:
            return variant.color_name, variant.safe_color_hex, variant.image_src

    raise ValueError('A cor selecionada não é válida para este produto.')


def _quantity_discount_message(product: Product, quantity: int) -> str:
    if product.has_bulk_discount_for(quantity):
        return f'Desconto automático aplicado: {product.bulk_discount_percent_display}% off por levar {quantity} unidades.'
    return ''


def _create_order_from_products(products_and_qty: list[tuple[Product, int, str | None, str | None, str | None, str | None]], clear_cart_for_user_id: int | None = None) -> Order:
    subtotal = sum(
        (Decimal(quantity) * Decimal(product.unit_price_for_quantity(quantity)) for product, quantity, _selected_size, _selected_color_name, _selected_color_hex, _selected_color_image in products_and_qty),
        start=Decimal('0.00'),
    )
    order = Order(
        user_id=current_user.id,
        subtotal=subtotal,
        payment_method='pix',
        status='pending',
        payment_status='pending',
        code=generate_order_code(),
    )
    db.session.add(order)
    db.session.flush()

    for product, quantity, selected_size, selected_color_name, selected_color_hex, selected_color_image in products_and_qty:
        if quantity > product.stock:
            db.session.rollback()
            raise ValueError(f'Estoque insuficiente para {product.name}.')
        unit_price = product.unit_price_for_quantity(quantity)
        db.session.add(
            OrderItem(
                order_id=order.id,
                product_id=product.id,
                product_name=product.name,
                quantity=quantity,
                selected_size=selected_size,
                selected_color_name=selected_color_name,
                selected_color_hex=selected_color_hex,
                selected_color_image=selected_color_image,
                unit_price=unit_price,
                total_price=Decimal(quantity) * unit_price,
            )
        )
        product.stock -= quantity

    if clear_cart_for_user_id is not None:
        CartItem.query.filter_by(user_id=clear_cart_for_user_id).delete()

    db.session.flush()
    store_name = AppSetting.get_value('store_name', current_app.config['STORE_NAME'])
    owner_phone = AppSetting.get_value('owner_whatsapp_number', '')
    admin_order_url = f"{_public_base_url()}{url_for('admin.order_detail', order_id=order.id)}"
    order.seller_whatsapp_link = build_whatsapp_link(owner_phone, build_owner_order_message(store_name, order, admin_order_url))

    db.session.commit()
    return order


def _redirect_after_cart_add(product_id: int, redirect_to_cart: bool) -> str:
    if redirect_to_cart:
        return url_for('store.cart')
    return url_for('store.product_detail', product_id=product_id)


@bp.route('/offline')
def offline():
    return render_template('store/offline.html', offline_message=get_store_offline_message())


@bp.route('/store')
@login_required
@store_enabled_required
def index():
    category_slug = request.args.get('category', '').strip()
    categories = Category.query.order_by(Category.name.asc()).all()
    query = Product.query.filter_by(active=True)
    selected_category = None
    if category_slug:
        selected_category = Category.query.filter_by(slug=category_slug).first()
        if selected_category:
            query = query.filter_by(category_id=selected_category.id)
    products = query.order_by(Product.created_at.desc()).all()
    return render_template('store/index.html', products=products, categories=categories, selected_category=selected_category, format_brl=format_brl)


@bp.route('/store/product/<int:product_id>')
@login_required
@store_enabled_required
def product_detail(product_id: int):
    product = Product.query.get_or_404(product_id)
    return render_template('store/detail.html', product=product, format_brl=format_brl)


@bp.route('/store/product/<int:product_id>/buy-now', methods=['POST'])
@login_required
@store_enabled_required
def buy_now(product_id: int):
    product = Product.query.get_or_404(product_id)
    quantity = max(int(request.form.get('quantity', 1) or 1), 1)
    if quantity > product.stock:
        flash('Quantidade maior do que o estoque disponível.', 'danger')
        return redirect(url_for('store.product_detail', product_id=product.id))

    try:
        selected_size = _normalize_selected_size(product, request.form.get('selected_size'))
        selected_color_name, selected_color_hex, selected_color_image = _normalize_selected_color(product, request.form.get('selected_color_name'))
    except ValueError as exc:
        flash(str(exc), 'danger')
        return redirect(url_for('store.product_detail', product_id=product.id))

    item = CartItem.query.filter_by(
        user_id=current_user.id,
        product_id=product.id,
        selected_size=selected_size,
        selected_color_name=selected_color_name,
    ).first()

    final_quantity = quantity
    if item:
        final_quantity = item.quantity + quantity
        if final_quantity > product.stock:
            flash('Você ultrapassou o estoque disponível.', 'danger')
            return redirect(url_for('store.product_detail', product_id=product.id))
        item.quantity = final_quantity
        item.selected_color_hex = selected_color_hex
        item.selected_color_image = selected_color_image
    else:
        db.session.add(
            CartItem(
                user_id=current_user.id,
                product_id=product.id,
                quantity=quantity,
                selected_size=selected_size,
                selected_color_name=selected_color_name,
                selected_color_hex=selected_color_hex,
                selected_color_image=selected_color_image,
            )
        )
    db.session.commit()

    message = _quantity_discount_message(product, final_quantity)
    if message:
        flash(message, 'success')
    flash('Produto enviado para o carrinho. Agora você pode revisar antes de concluir o pedido.', 'success')
    return redirect(url_for('store.cart'))


@bp.route('/store/cart/add/<int:product_id>', methods=['POST'])
@login_required
@store_enabled_required
def add_to_cart(product_id: int):
    product = Product.query.get_or_404(product_id)
    quantity = max(int(request.form.get('quantity', 1) or 1), 1)
    if quantity > product.stock:
        flash('Quantidade maior do que o estoque disponível.', 'danger')
        return redirect(url_for('store.product_detail', product_id=product.id))

    try:
        selected_size = _normalize_selected_size(product, request.form.get('selected_size'))
        selected_color_name, selected_color_hex, selected_color_image = _normalize_selected_color(product, request.form.get('selected_color_name'))
    except ValueError as exc:
        flash(str(exc), 'danger')
        return redirect(url_for('store.product_detail', product_id=product.id))

    item = CartItem.query.filter_by(
        user_id=current_user.id,
        product_id=product.id,
        selected_size=selected_size,
        selected_color_name=selected_color_name,
    ).first()

    final_quantity = quantity
    if item:
        final_quantity = item.quantity + quantity
        if final_quantity > product.stock:
            flash('Você ultrapassou o estoque disponível.', 'danger')
            return redirect(url_for('store.product_detail', product_id=product.id))
        item.quantity = final_quantity
        item.selected_color_hex = selected_color_hex
        item.selected_color_image = selected_color_image
    else:
        db.session.add(
            CartItem(
                user_id=current_user.id,
                product_id=product.id,
                quantity=quantity,
                selected_size=selected_size,
                selected_color_name=selected_color_name,
                selected_color_hex=selected_color_hex,
                selected_color_image=selected_color_image,
            )
        )
    db.session.commit()

    message = _quantity_discount_message(product, final_quantity)
    if message:
        flash(message, 'success')

    redirect_to_cart = request.form.get('redirect_to_cart', '').lower() == 'true'
    flash('Produto adicionado ao carrinho.', 'success')
    return redirect(_redirect_after_cart_add(product.id, redirect_to_cart))


@bp.route('/store/cart')
@login_required
@store_enabled_required
def cart():
    cart_items = CartItem.query.filter_by(user_id=current_user.id).order_by(CartItem.created_at.desc()).all()
    total = sum((item.subtotal for item in cart_items), start=Decimal('0.00'))
    total_bulk_savings = sum((item.bulk_discount_savings for item in cart_items), start=Decimal('0.00'))
    return render_template('store/cart.html', cart_items=cart_items, total=total, total_bulk_savings=total_bulk_savings, format_brl=format_brl)


@bp.route('/store/cart/update', methods=['POST'])
@login_required
@store_enabled_required
def update_cart():
    cart_item_ids = request.form.getlist('cart_item_id')
    quantities = request.form.getlist('quantity')
    activated_discount = False
    for item_id, quantity in zip(cart_item_ids, quantities):
        item = CartItem.query.filter_by(id=int(item_id), user_id=current_user.id).first()
        if not item:
            continue
        qty = max(int(quantity or 1), 1)
        if qty > item.product.stock:
            qty = item.product.stock
        item.quantity = qty
        if item.has_bulk_discount:
            activated_discount = True
    db.session.commit()
    if activated_discount:
        flash('Desconto por quantidade aplicado no carrinho.', 'success')
    flash('Carrinho atualizado.', 'success')
    return redirect(url_for('store.cart'))


@bp.route('/store/cart/remove/<int:item_id>', methods=['POST'])
@login_required
@store_enabled_required
def remove_cart_item(item_id: int):
    item = CartItem.query.filter_by(id=item_id, user_id=current_user.id).first_or_404()
    db.session.delete(item)
    db.session.commit()
    flash('Item removido do carrinho.', 'info')
    return redirect(url_for('store.cart'))


@bp.route('/store/checkout', methods=['POST'])
@login_required
@store_enabled_required
def checkout():
    cart_items = CartItem.query.filter_by(user_id=current_user.id).all()
    if not cart_items:
        flash('Seu carrinho está vazio.', 'warning')
        return redirect(url_for('store.cart'))
    try:
        order = _create_order_from_products(
            [
                (
                    item.product,
                    item.quantity,
                    item.selected_size,
                    item.selected_color_name,
                    item.selected_color_hex,
                    item.selected_color_image,
                )
                for item in cart_items
            ],
            clear_cart_for_user_id=current_user.id,
        )
    except ValueError as exc:
        flash(str(exc), 'danger')
        return redirect(url_for('store.cart'))
    flash('Pedido criado com sucesso. Agora ele está aguardando aprovação.', 'success')
    return redirect(url_for('store.order_detail', order_id=order.id))


@bp.route('/store/profile')
@login_required
def profile():
    orders = Order.query.filter_by(user_id=current_user.id).order_by(Order.created_at.desc()).all()
    return render_template('store/profile.html', orders=orders, format_brl=format_brl, status_badges=STATUS_BADGES)


@bp.route('/store/orders/<int:order_id>')
@login_required
def order_detail(order_id: int):
    order = Order.query.filter_by(id=order_id, user_id=current_user.id).first_or_404()
    extra_customer_link = customer_whatsapp_link(order) if current_user.is_admin else ''
    return render_template('store/order_detail.html', order=order, format_brl=format_brl, status_badges=STATUS_BADGES, customer_whatsapp_link=extra_customer_link)


@bp.route('/store/orders/<int:order_id>/cancel', methods=['POST'])
@login_required
def cancel_order(order_id: int):
    order = Order.query.filter_by(id=order_id, user_id=current_user.id).first_or_404()
    if order.status != 'pending':
        flash('Só é possível cancelar pedidos que ainda aguardam aprovação.', 'warning')
        return redirect(url_for('store.order_detail', order_id=order.id))
    for item in order.items:
        if item.product:
            item.product.stock += item.quantity
    order.status = 'cancelled'
    order.payment_status = 'pending'
    db.session.commit()
    flash('Pedido cancelado com sucesso.', 'info')
    return redirect(url_for('store.profile'))
