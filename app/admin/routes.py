from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
import json
import re
import secrets

from flask import Blueprint, Response, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

from ..decorators import admin_required, owner_required
from ..extensions import db
from ..models import AppSetting, Category, Order, Product, ProductColorVariant, User
from ..runtime_store import get_store_schedule_settings, is_store_open_now
from ..services.payment_service import ensure_order_pix_data
from ..services.receipt_service import build_receipt, format_brl
from ..services.whatsapp_service import build_customer_status_message, build_whatsapp_link

bp = Blueprint('admin', __name__, url_prefix='/admin')
ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp', 'gif'}

VISUAL_THEME_BLOCKS = [
    {
        'id': 'body',
        'label': 'Página inteira',
        'selectors': 'body',
        'classes': ['body'],
        'description': 'Controla o fundo e a cor base do site inteiro.',
    },
    {
        'id': 'topbar',
        'label': 'Topo e navegação',
        'selectors': '.topbar, .nav-links a, .brand',
        'classes': ['topbar', 'nav-links', 'brand'],
        'description': 'Cabeçalho fixo da loja e links do menu principal.',
    },
    {
        'id': 'sidebar',
        'label': 'Menu lateral',
        'selectors': '.sidebar, .sidebar-link, .sidebar-link.active',
        'classes': ['sidebar', 'sidebar-link', 'sidebar-link active'],
        'description': 'Bloco de categorias e links do menu lateral.',
    },
    {
        'id': 'cards',
        'label': 'Cards e caixas',
        'selectors': '.product-card, .table-card, .profile-card, .payment-card, .checkout-box, .stat-card, .empty-state, .auth-card',
        'classes': ['product-card', 'table-card', 'profile-card', 'payment-card', 'checkout-box', 'stat-card'],
        'description': 'Cartões, tabelas e caixas principais do sistema.',
    },
    {
        'id': 'titles',
        'label': 'Títulos',
        'selectors': '.page-header h1, .detail-info h1, .product-card-body h3, .auth-card h1',
        'classes': ['page-header', 'detail-info', 'product-card-body', 'auth-card'],
        'description': 'Títulos principais das páginas e dos produtos.',
    },
    {
        'id': 'prices',
        'label': 'Preços',
        'selectors': '.price-large, .product-price',
        'classes': ['price-large', 'product-price'],
        'description': 'Textos usados para exibir preço e destaque monetário.',
    },
    {
        'id': 'btn_primary',
        'label': 'Botão principal',
        'selectors': '.btn.btn-primary',
        'classes': ['btn', 'btn-primary'],
        'description': 'Botões de ação principal como finalizar e salvar.',
    },
    {
        'id': 'btn_secondary',
        'label': 'Botão secundário',
        'selectors': '.btn:not(.btn-primary):not(.btn-danger):not(.btn-success)',
        'classes': ['btn'],
        'description': 'Botões neutros como voltar, inserir e abrir pedido.',
    },
    {
        'id': 'inputs',
        'label': 'Campos e selects',
        'selectors': 'input, select, textarea',
        'classes': ['input', 'select', 'textarea'],
        'description': 'Campos de formulário em todo o sistema.',
    },
    {
        'id': 'badges',
        'label': 'Badges e status',
        'selectors': '.badge, .badge-soft, .badge-warning, .badge-danger-soft, .badge-success-soft',
        'classes': ['badge', 'badge-soft', 'badge-warning'],
        'description': 'Selos de status, categoria e situação do pedido.',
    },
]


def slugify(text: str) -> str:
    slug = re.sub(r'[^a-zA-Z0-9]+', '-', text.lower()).strip('-')
    return slug or 'categoria'


def owner_candidates():
    return User.query.filter(User.role.in_(['owner', 'admin'])).order_by(User.name.asc()).all()


def resolve_owner_user():
    owner_user_id = AppSetting.get_value('owner_user_id', '')
    if owner_user_id.isdigit():
        user = db.session.get(User, int(owner_user_id))
        if user and user.role in {'owner', 'admin'}:
            return user
    return User.query.filter_by(role='owner').order_by(User.id.asc()).first()


def uploads_dir() -> Path:
    path = Path(current_app.root_path) / 'static' / 'uploads' / 'products'
    path.mkdir(parents=True, exist_ok=True)
    return path


def allowed_image(filename: str) -> bool:
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_IMAGE_EXTENSIONS


def save_uploaded_image(file: FileStorage | None) -> str | None:
    if not file or not file.filename:
        return None
    if not allowed_image(file.filename):
        raise ValueError('Use uma imagem PNG, JPG, JPEG, WEBP ou GIF.')
    original_name = secure_filename(file.filename)
    extension = original_name.rsplit('.', 1)[1].lower()
    filename = f'{secrets.token_hex(12)}.{extension}'
    file.save(uploads_dir() / filename)
    return filename


def delete_uploaded_image(filename: str | None) -> None:
    if not filename:
        return
    file_path = uploads_dir() / filename
    if file_path.exists():
        file_path.unlink()


def parse_decimal(value: str, default: str = '0') -> Decimal:
    cleaned = (value or default).strip().replace('.', '').replace(',', '.')
    try:
        return Decimal(cleaned)
    except (InvalidOperation, AttributeError):
        return Decimal(default)


def parse_int(value: str, default: int = 0) -> int:
    try:
        return int(str(value).strip())
    except Exception:
        return default


def _template_root() -> Path:
    return Path(current_app.root_path) / 'templates'


def _base_css_path() -> Path:
    return Path(current_app.root_path) / 'static' / 'css' / 'style.css'


def _extract_used_classes() -> list[dict]:
    template_root = _template_root()
    usage: dict[str, set[str]] = {}
    for file_path in template_root.rglob('*.html'):
        source = file_path.read_text(encoding='utf-8')
        for raw_classes in re.findall(r'class\s*=\s*"([^"]+)"', source):
            if '{{' in raw_classes or '{%' in raw_classes:
                continue
            for token in raw_classes.split():
                if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]*', token):
                    continue
                usage.setdefault(token, set()).add(file_path.relative_to(template_root).as_posix())
    css_source = _base_css_path().read_text(encoding='utf-8')
    for class_name in re.findall(r'\.([A-Za-z][A-Za-z0-9_-]*)', css_source):
        usage.setdefault(class_name, set())
    return [
        {
            'name': class_name,
            'files': sorted(usage[class_name]),
            'snippet': f'.{class_name} {{\n    \n}}',
        }
        for class_name in sorted(usage)
    ]


def _custom_css() -> str:
    return AppSetting.get_value('custom_css', '')


def _theme_json_value() -> str:
    return AppSetting.get_value('theme_editor_json', '{}')


def _advanced_css_value() -> str:
    stored = AppSetting.get_value('theme_advanced_css', '')
    if stored:
        return stored
    if _theme_json_value() == '{}':
        return AppSetting.get_value('custom_css', '')
    return ''


def _load_visual_theme_settings() -> dict[str, dict[str, str]]:
    raw = _theme_json_value()
    try:
        data = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        data = {}
    return data if isinstance(data, dict) else {}


def _clean_color(value: str) -> str:
    text = (value or '').strip()
    if not text:
        return ''
    if re.fullmatch(r'#[0-9a-fA-F]{3,8}', text):
        return text
    if re.fullmatch(r'(rgb|rgba|hsl|hsla)\([0-9.,%\s-]+\)', text):
        return text
    if re.fullmatch(r'[A-Za-z][A-Za-z\s-]{1,30}', text):
        return text
    if re.fullmatch(r'var\(--[A-Za-z0-9_-]+\)', text):
        return text
    return ''


def _clean_length(value: str) -> str:
    text = (value or '').strip()
    if not text:
        return ''
    if re.fullmatch(r'[0-9]+(\.[0-9]+)?(px|rem|em|%)?', text):
        return text
    return ''


def _clean_shadow(value: str) -> str:
    text = (value or '').strip()
    if not text:
        return ''
    if re.fullmatch(r'[A-Za-z0-9#(),.%\s-]{1,80}', text):
        return text
    return ''


def _collect_visual_theme_form() -> dict[str, dict[str, str]]:
    data: dict[str, dict[str, str]] = {}
    for block in VISUAL_THEME_BLOCKS:
        block_id = block['id']
        block_data = {
            'background': _clean_color(request.form.get(f'theme__{block_id}__background', '')),
            'text': _clean_color(request.form.get(f'theme__{block_id}__text', '')),
            'border': _clean_color(request.form.get(f'theme__{block_id}__border', '')),
            'font_size': _clean_length(request.form.get(f'theme__{block_id}__font_size', '')),
            'radius': _clean_length(request.form.get(f'theme__{block_id}__radius', '')),
            'padding': _clean_length(request.form.get(f'theme__{block_id}__padding', '')),
            'shadow': _clean_shadow(request.form.get(f'theme__{block_id}__shadow', '')),
        }
        if any(block_data.values()):
            data[block_id] = block_data
    return data


def _build_visual_theme_css(theme_values: dict[str, dict[str, str]], advanced_css: str = '') -> str:
    chunks: list[str] = ['/* CSS gerado pelo editor visual do admin */']
    for block in VISUAL_THEME_BLOCKS:
        block_id = block['id']
        values = theme_values.get(block_id, {})
        declarations: list[str] = []
        if values.get('background'):
            declarations.append(f"background: {values['background']};")
        if values.get('text'):
            declarations.append(f"color: {values['text']};")
        if values.get('border'):
            declarations.append(f"border-color: {values['border']};")
            declarations.append('border-style: solid;')
            declarations.append('border-width: 1px;')
        if values.get('font_size'):
            declarations.append(f"font-size: {values['font_size']};")
        if values.get('radius'):
            declarations.append(f"border-radius: {values['radius']};")
        if values.get('padding'):
            declarations.append(f"padding: {values['padding']};")
        if values.get('shadow'):
            declarations.append(f"box-shadow: {values['shadow']};")
        if declarations:
            chunks.append(f"\n{block['selectors']} {{\n    " + "\n    ".join(declarations) + "\n}")
    advanced_css = (advanced_css or '').strip()
    if advanced_css:
        chunks.append('\n/* CSS avançado do admin */\n' + advanced_css)
    return '\n'.join(chunks).strip() + ('\n' if chunks else '')


def _theme_editor_blocks_with_values() -> list[dict]:
    values = _load_visual_theme_settings()
    blocks: list[dict] = []
    for block in VISUAL_THEME_BLOCKS:
        current = values.get(block['id'], {})
        blocks.append(
            {
                **block,
                'theme_values': {
                    'background': current.get('background', ''),
                    'text': current.get('text', ''),
                    'border': current.get('border', ''),
                    'font_size': current.get('font_size', ''),
                    'radius': current.get('radius', ''),
                    'padding': current.get('padding', ''),
                    'shadow': current.get('shadow', ''),
                },
            }
        )
    return blocks


def _ensure_order_payment_assets(order: Order) -> None:
    if order.pix_payload and order.pix_qr_path:
        return
    pix_key = AppSetting.get_value('pix_key', 'pix@lojaflex.com')
    merchant_name = AppSetting.get_value('merchant_name', 'LOJA FLEX')
    merchant_city = AppSetting.get_value('merchant_city', 'POCOSCALDAS')
    payload, qr_relative_path = ensure_order_pix_data(
        order_id=order.id,
        amount=Decimal(order.subtotal),
        root_path=Path(current_app.root_path),
        pix_key=pix_key,
        merchant_name=merchant_name,
        merchant_city=merchant_city,
    )
    order.pix_payload = payload
    order.pix_qr_path = qr_relative_path


def extract_color_variants_from_form() -> list[dict[str, str]]:
    names = request.form.getlist('color_name[]')
    hexes = request.form.getlist('color_hex[]')
    urls = request.form.getlist('color_image_url[]')
    existing_filenames = request.form.getlist('color_existing_filename[]')
    image_files = request.files.getlist('color_image[]')
    max_len = max(len(names), len(hexes), len(urls), len(existing_filenames), len(image_files)) if any([names, hexes, urls, existing_filenames, image_files]) else 0
    variants: list[dict[str, str]] = []
    for index in range(max_len):
        color_name = names[index].strip() if index < len(names) else ''
        color_hex = _clean_color(hexes[index]) if index < len(hexes) else ''
        color_image_url = urls[index].strip() if index < len(urls) else ''
        existing_filename = existing_filenames[index].strip() if index < len(existing_filenames) else ''
        image_file = image_files[index] if index < len(image_files) else None
        if not color_name and not color_hex and not color_image_url and not existing_filename and not (image_file and image_file.filename):
            continue
        image_filename = save_uploaded_image(image_file) if image_file and image_file.filename else existing_filename
        variants.append(
            {
                'color_name': color_name,
                'color_hex': color_hex or '#111827',
                'image_url': color_image_url,
                'image_filename': image_filename,
            }
        )
    return variants


def validate_product_form(categories: list[Category], product_type: str, color_variants: list[dict[str, str]]) -> str | None:
    name = request.form.get('name', '').strip()
    description = request.form.get('description', '').strip()
    category_id = request.form.get('category_id', '').strip()
    if not name or not description or not category_id:
        return 'Preencha nome, categoria e descrição.'
    if not any(str(category.id) == category_id for category in categories):
        return 'Categoria inválida.'
    if product_type not in {'consumivel', 'utensilio'}:
        return 'Selecione um tipo de produto válido.'
    if product_type == 'consumivel':
        if not request.form.get('weight_grams', '').strip():
            return 'Informe a gramagem do consumível.'
        if not request.form.get('recipe_ingredients', '').strip():
            return 'Informe os ingredientes usados na receita.'
    price_value = parse_decimal(request.form.get('price', '0'))
    discount_value = parse_decimal(request.form.get('discount_price', '0'))
    if price_value <= 0:
        return 'Informe um valor cheio maior que zero.'
    if discount_value and discount_value > 0 and discount_value >= price_value:
        return 'O valor com desconto deve ser menor que o valor cheio.'

    if product_type == 'utensilio':
        if not request.form.get('size_info', '').strip():
            return 'Informe o tamanho do utensílio.'
        if not request.form.get('material', '').strip():
            return 'Informe o tecido ou material do item.'
        valid_colors = [
            item for item in color_variants if item['color_name'] and item['color_hex'] and (item['image_filename'] or item['image_url'])
        ]
        if not valid_colors:
            return 'Cadastre pelo menos uma cor com imagem para o utensílio.'
    return None


def upsert_product_from_form(product: Product | None = None) -> Product:
    creating = product is None
    product = product or Product()
    old_main_filename = product.image_filename
    old_color_filenames = {variant.image_filename for variant in product.color_variants if variant.image_filename}
    categories = Category.query.order_by(Category.name.asc()).all()
    product_type = request.form.get('product_type', 'consumivel').strip()
    color_variants = extract_color_variants_from_form()
    validation_error = validate_product_form(categories, product_type, color_variants)
    if validation_error:
        raise ValueError(validation_error)
    product.name = request.form.get('name', '').strip()
    product.description = request.form.get('description', '').strip()
    product.price = parse_decimal(request.form.get('price', '0'))
    discount_value = parse_decimal(request.form.get('discount_price', '0'))
    product.discount_price = discount_value if discount_value > 0 else None
    product.stock = parse_int(request.form.get('stock', '0'), 0)
    product.category_id = parse_int(request.form.get('category_id', '0'), 0)
    product.active = request.form.get('active') == 'on'
    product.product_type = product_type

    uploaded_main = request.files.get('image_file')
    new_main_filename = save_uploaded_image(uploaded_main) if uploaded_main and uploaded_main.filename else None
    manual_image_url = request.form.get('image_url', '').strip()
    if new_main_filename:
        product.image_filename = new_main_filename
        product.image_url = ''
        if old_main_filename and old_main_filename != new_main_filename:
            delete_uploaded_image(old_main_filename)
    else:
        if manual_image_url:
            product.image_url = manual_image_url
        elif not product.image_filename:
            product.image_url = ''

    if product_type == 'consumivel':
        product.weight_grams = request.form.get('weight_grams', '').strip()
        product.recipe_ingredients = request.form.get('recipe_ingredients', '').strip()
        product.size_info = ''
        product.material = ''
    else:
        product.weight_grams = ''
        product.recipe_ingredients = ''
        product.size_info = request.form.get('size_info', '').strip()
        product.material = request.form.get('material', '').strip()

    if creating:
        db.session.add(product)
        db.session.flush()

    for variant in list(product.color_variants):
        db.session.delete(variant)
    db.session.flush()

    current_filenames: set[str] = set()
    if product.product_type == 'utensilio':
        for item in color_variants:
            if not item['color_name']:
                continue
            variant = ProductColorVariant(
                product_id=product.id,
                color_name=item['color_name'],
                color_hex=item['color_hex'],
                image_url=item['image_url'],
                image_filename=item['image_filename'],
            )
            if variant.image_filename:
                current_filenames.add(variant.image_filename)
            db.session.add(variant)

    for old_filename in old_color_filenames - current_filenames:
        delete_uploaded_image(old_filename)
    return product


@bp.route('/')
@login_required
@admin_required
def dashboard():
    products = Product.query.order_by(Product.created_at.desc()).all()
    categories = Category.query.order_by(Category.name.asc()).all()
    orders = Order.query.order_by(Order.created_at.desc()).limit(20).all()
    orders_count = Order.query.count()
    users_count = User.query.count()
    total_sales = sum((Decimal(order.subtotal) for order in Order.query.filter_by(payment_status='paid').all()), start=Decimal('0.00'))
    linked_owner = resolve_owner_user()
    schedule = get_store_schedule_settings()
    settings = {
        'store_name': AppSetting.get_value('store_name', current_app.config['STORE_NAME']),
        'whatsapp_number': AppSetting.get_value('whatsapp_number', ''),
        'owner_user_id': str(linked_owner.id) if linked_owner else '',
        'owner_whatsapp_number': AppSetting.get_value('owner_whatsapp_number', linked_owner.phone if linked_owner else ''),
        'pix_key': AppSetting.get_value('pix_key', ''),
        'merchant_name': AppSetting.get_value('merchant_name', 'LOJA FLEX'),
        'merchant_city': AppSetting.get_value('merchant_city', 'POCOSCALDAS'),
        'store_enabled': AppSetting.get_value('store_enabled', 'true') == 'true',
        'schedule_enabled': schedule['schedule_enabled'],
        'opening_time': schedule['opening_time'],
        'closing_time': schedule['closing_time'],
        'store_open_now': is_store_open_now(),
        'bulk_discount_enabled': AppSetting.get_value('bulk_discount_enabled', 'true') == 'true',
        'bulk_discount_min_qty': AppSetting.get_value('bulk_discount_min_qty', '3'),
        'bulk_discount_percent': AppSetting.get_value('bulk_discount_percent', '10'),
    }
    return render_template(
        'admin/dashboard.html',
        products=products,
        categories=categories,
        orders=orders,
        orders_count=orders_count,
        users_count=users_count,
        total_sales=total_sales,
        settings=settings,
        owner_candidates=owner_candidates(),
        linked_owner=linked_owner,
        format_brl=format_brl,
    )


@bp.route('/orders/<int:order_id>')
@login_required
@admin_required
def order_detail(order_id: int):
    order = Order.query.get_or_404(order_id)
    store_name = AppSetting.get_value('store_name', current_app.config['STORE_NAME'])
    customer_whatsapp_link = build_whatsapp_link(order.user.phone, build_customer_status_message(store_name, order))
    return render_template('admin/order_detail.html', order=order, customer_whatsapp_link=customer_whatsapp_link, format_brl=format_brl)


@bp.route('/orders/<int:order_id>/approve', methods=['POST'])
@login_required
@admin_required
def approve_order(order_id: int):
    order = Order.query.get_or_404(order_id)
    if order.status == 'cancelled':
        flash('Pedido cancelado pelo cliente não pode ser aprovado.', 'warning')
        return redirect(url_for('admin.order_detail', order_id=order.id))
    if order.status == 'rejected' and order.payment_status == 'paid':
        flash('Pedido pago não pode ser reaberto sem revisão manual.', 'warning')
        return redirect(url_for('admin.order_detail', order_id=order.id))
    _ensure_order_payment_assets(order)
    order.status = 'completed' if order.payment_status == 'paid' else 'accepted'
    db.session.commit()
    flash('Pedido aprovado com sucesso. O PIX foi liberado para o cliente.', 'success')
    return redirect(url_for('admin.order_detail', order_id=order.id))


@bp.route('/orders/<int:order_id>/reject', methods=['POST'])
@login_required
@admin_required
def reject_order(order_id: int):
    order = Order.query.get_or_404(order_id)
    if order.status == 'cancelled':
        flash('Pedido cancelado pelo cliente não pode ser recusado novamente.', 'warning')
        return redirect(url_for('admin.order_detail', order_id=order.id))
    if order.payment_status == 'paid':
        flash('Não é possível recusar um pedido já marcado como pago.', 'danger')
        return redirect(url_for('admin.order_detail', order_id=order.id))
    for item in order.items:
        if item.product:
            item.product.stock += item.quantity
    order.status = 'rejected'
    db.session.commit()
    flash('Pedido recusado com sucesso.', 'warning')
    return redirect(url_for('admin.order_detail', order_id=order.id))


@bp.route('/orders/<int:order_id>/mark-paid', methods=['POST'])
@login_required
@admin_required
def mark_paid(order_id: int):
    order = Order.query.get_or_404(order_id)
    if order.status in {'rejected', 'cancelled'}:
        flash('Esse pedido não pode ser marcado como pago.', 'warning')
        return redirect(url_for('admin.order_detail', order_id=order.id))
    _ensure_order_payment_assets(order)
    order.payment_status = 'paid'
    order.status = 'completed'
    store_name = AppSetting.get_value('store_name', current_app.config['STORE_NAME'])
    order.receipt_text = build_receipt(store_name, order)
    order.whatsapp_receipt_link = build_whatsapp_link(order.user.phone, order.receipt_text)
    db.session.commit()
    flash('Pagamento confirmado e comprovante gerado com sucesso.', 'success')
    return redirect(url_for('admin.order_detail', order_id=order.id))


@bp.route('/orders/clear-history', methods=['POST'])
@login_required
@admin_required
def clear_order_history():
    orders = Order.query.all()
    removed = len(orders)
    for order in orders:
        if order.pix_qr_path:
            qr_file = Path(current_app.root_path) / 'static' / order.pix_qr_path
            if qr_file.exists():
                qr_file.unlink()
        db.session.delete(order)
    db.session.commit()
    flash(f'Histórico limpo com sucesso. {removed} pedido(s) removido(s).', 'info')
    return redirect(url_for('admin.dashboard'))


@bp.route('/theme-editor', methods=['GET', 'POST'])
@login_required
@admin_required
def theme_editor():
    if request.method == 'POST':
        action = request.form.get('action', 'apply')
        version = str(int(datetime.utcnow().timestamp()))
        if action == 'reset':
            AppSetting.set_value('theme_editor_json', '{}')
            AppSetting.set_value('theme_advanced_css', '')
            AppSetting.set_value('custom_css', '')
            AppSetting.set_value('custom_css_version', version)
            db.session.commit()
            flash('Tema personalizado removido. O site voltou para o estilo base.', 'info')
        else:
            visual_settings = _collect_visual_theme_form()
            advanced_css = request.form.get('advanced_css', '').strip()
            final_css = _build_visual_theme_css(visual_settings, advanced_css)
            AppSetting.set_value('theme_editor_json', json.dumps(visual_settings, ensure_ascii=False))
            AppSetting.set_value('theme_advanced_css', advanced_css)
            AppSetting.set_value('custom_css', final_css)
            AppSetting.set_value('custom_css_version', version)
            db.session.commit()
            flash('Tema aplicado com sucesso em todo o site.', 'success')
        return redirect(url_for('admin.theme_editor'))
    return render_template(
        'admin/theme_editor.html',
        visual_blocks=_theme_editor_blocks_with_values(),
        used_classes=_extract_used_classes(),
        advanced_css=_advanced_css_value(),
    )


@bp.route('/custom.css')
def custom_css_file():
    return Response(_custom_css(), mimetype='text/css')


@bp.route('/product/new', methods=['GET', 'POST'])
@login_required
@admin_required
def product_new():
    categories = Category.query.order_by(Category.name.asc()).all()
    if request.method == 'POST':
        try:
            upsert_product_from_form(None)
            db.session.commit()
            flash('Produto criado com sucesso.', 'success')
            return redirect(url_for('admin.dashboard'))
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), 'danger')
    return render_template('admin/product_form.html', product=None, categories=categories)


@bp.route('/product/<int:product_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def product_edit(product_id: int):
    product = Product.query.get_or_404(product_id)
    categories = Category.query.order_by(Category.name.asc()).all()
    if request.method == 'POST':
        try:
            upsert_product_from_form(product)
            db.session.commit()
            flash('Produto atualizado com sucesso.', 'success')
            return redirect(url_for('admin.dashboard'))
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), 'danger')
    return render_template('admin/product_form.html', product=product, categories=categories)


@bp.route('/product/<int:product_id>/delete', methods=['POST'])
@login_required
@admin_required
def product_delete(product_id: int):
    product = Product.query.get_or_404(product_id)
    delete_uploaded_image(product.image_filename)
    for variant in product.color_variants:
        delete_uploaded_image(variant.image_filename)
    db.session.delete(product)
    db.session.commit()
    flash('Produto removido com sucesso.', 'info')
    return redirect(url_for('admin.dashboard'))


@bp.route('/category/new', methods=['POST'])
@login_required
@admin_required
def category_new():
    name = request.form.get('name', '').strip()
    if not name:
        flash('Informe o nome da categoria.', 'danger')
        return redirect(url_for('admin.dashboard'))
    if Category.query.filter_by(slug=slugify(name)).first():
        flash('Já existe uma categoria com esse nome.', 'warning')
        return redirect(url_for('admin.dashboard'))
    db.session.add(Category(name=name, slug=slugify(name)))
    db.session.commit()
    flash('Categoria criada com sucesso.', 'success')
    return redirect(url_for('admin.dashboard'))


@bp.route('/category/<int:category_id>/delete', methods=['POST'])
@login_required
@admin_required
def category_delete(category_id: int):
    category = Category.query.get_or_404(category_id)
    if category.products:
        flash('Não é possível remover uma categoria que possui produtos.', 'warning')
        return redirect(url_for('admin.dashboard'))
    db.session.delete(category)
    db.session.commit()
    flash('Categoria removida com sucesso.', 'info')
    return redirect(url_for('admin.dashboard'))


@bp.route('/settings/update', methods=['POST'])
@login_required
@admin_required
def update_settings():
    AppSetting.set_value('store_name', request.form.get('store_name', 'Loja Flex Final').strip())
    AppSetting.set_value('whatsapp_number', request.form.get('whatsapp_number', '').strip())
    AppSetting.set_value('pix_key', request.form.get('pix_key', '').strip())
    AppSetting.set_value('merchant_name', request.form.get('merchant_name', 'LOJA FLEX').strip().upper())
    AppSetting.set_value('merchant_city', request.form.get('merchant_city', 'POCOSCALDAS').strip().upper())
    AppSetting.set_value('schedule_enabled', 'true' if request.form.get('schedule_enabled') == 'on' else 'false')
    AppSetting.set_value('bulk_discount_enabled', 'true' if request.form.get('bulk_discount_enabled') == 'on' else 'false')
    AppSetting.set_value('bulk_discount_min_qty', str(max(parse_int(request.form.get('bulk_discount_min_qty', '3'), 3), 2)))
    AppSetting.set_value('bulk_discount_percent', str(max(parse_decimal(request.form.get('bulk_discount_percent', '10'), '10'), Decimal('0'))))
    AppSetting.set_value('opening_time', request.form.get('opening_time', '08:00').strip() or '08:00')
    AppSetting.set_value('closing_time', request.form.get('closing_time', '18:00').strip() or '18:00')
    selected_owner_id = request.form.get('owner_user_id', '').strip()
    owner_phone = request.form.get('owner_whatsapp_number', '').strip()
    linked_owner = None
    if selected_owner_id.isdigit():
        linked_owner = db.session.get(User, int(selected_owner_id))
        if linked_owner and linked_owner.role in {'owner', 'admin'}:
            linked_owner.phone = owner_phone or linked_owner.phone
            AppSetting.set_value('owner_user_id', str(linked_owner.id))
        else:
            linked_owner = None
    if linked_owner and linked_owner.phone:
        AppSetting.set_value('owner_whatsapp_number', linked_owner.phone)
    else:
        AppSetting.set_value('owner_whatsapp_number', owner_phone)
    db.session.commit()
    flash('Configurações salvas. O telefone do dono foi vinculado pela conta administrativa.', 'success')
    return redirect(url_for('admin.dashboard'))


@bp.route('/settings/toggle-store', methods=['POST'])
@login_required
@owner_required
def toggle_store():
    current_value = AppSetting.get_value('store_enabled', 'true') == 'true'
    AppSetting.set_value('store_enabled', 'false' if current_value else 'true')
    db.session.commit()
    flash('Status manual da loja alterado com sucesso.', 'success')
    return redirect(url_for('admin.dashboard'))
