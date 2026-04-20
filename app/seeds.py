from decimal import Decimal
import re

from .extensions import db
from .models import AppSetting, Category, Product, ProductColorVariant, User


def slugify(text: str) -> str:
    slug = re.sub(r'[^a-zA-Z0-9]+', '-', text.lower()).strip('-')
    return slug or 'categoria'


def ensure_settings() -> None:
    defaults = {
        'store_enabled': 'true',
        'schedule_enabled': 'false',
        'opening_time': '08:00',
        'closing_time': '18:00',
        'store_name': 'Loja Flex Final',
        'whatsapp_number': '5535999999999',
        'owner_whatsapp_number': '5535999999999',
        'owner_user_id': '1',
        'pix_key': 'pix@lojaflex.com',
        'merchant_name': 'LOJA FLEX',
        'merchant_city': 'POCOSCALDAS',
        'custom_css': '',
        'custom_css_version': '0',
        'theme_editor_json': '{}',
        'theme_advanced_css': '',
        'bulk_discount_enabled': 'true',
        'bulk_discount_min_qty': '3',
        'bulk_discount_percent': '10',
    }

    for key, value in defaults.items():
        if not AppSetting.query.filter_by(key=key).first():
            db.session.add(AppSetting(key=key, value=value))


def ensure_users() -> None:
    if not User.query.filter_by(email='owner@lojaflex.com').first():
        owner = User(
            name='Dono da Loja',
            email='owner@lojaflex.com',
            phone='5535999999999',
            role='owner',
        )
        owner.set_password('123456')
        db.session.add(owner)

    if not User.query.filter_by(email='admin@lojaflex.com').first():
        admin = User(
            name='Administrador',
            email='admin@lojaflex.com',
            phone='5535997777666',
            role='admin',
        )
        admin.set_password('123456')
        db.session.add(admin)

    if not User.query.filter_by(email='cliente@lojaflex.com').first():
        customer = User(
            name='Cliente Teste',
            email='cliente@lojaflex.com',
            phone='5535998888777',
            role='customer',
        )
        customer.set_password('123456')
        db.session.add(customer)

    db.session.flush()


def get_or_create_category(name: str) -> Category:
    slug = slugify(name)

    category = Category.query.filter_by(slug=slug).first()
    if category:
        if category.name != name:
            category.name = name
        return category

    category = Category.query.filter_by(name=name).first()
    if category:
        if category.slug != slug:
            category.slug = slug
        return category

    category = Category(name=name, slug=slug)
    db.session.add(category)
    db.session.flush()
    return category


def ensure_catalog() -> None:
    category_names = ['Padaria', 'Bebidas', 'Doces', 'Lanches', 'Roupas', 'Acessórios']
    categories: dict[str, Category] = {}

    for name in category_names:
        categories[name] = get_or_create_category(name)

    if not Product.query.filter_by(name='Pão Francês').first():
        db.session.add(
            Product(
                name='Pão Francês',
                description='Pão fresco, crocante por fora e macio por dentro.',
                price=Decimal('1.20'),
                stock=300,
                category_id=categories['Padaria'].id,
                image_url='https://images.unsplash.com/photo-1509440159596-0249088772ff',
                product_type='consumivel',
                weight_grams='50 g',
                recipe_ingredients='Farinha de trigo, água, fermento, sal e melhorador.',
            )
        )

    if not Product.query.filter_by(name='Bolo de Cenoura').first():
        db.session.add(
            Product(
                name='Bolo de Cenoura',
                description='Bolo fofinho com cobertura de chocolate.',
                price=Decimal('24.90'),
                stock=20,
                category_id=categories['Doces'].id,
                image_url='https://images.unsplash.com/photo-1578985545062-69928b1d9587',
                product_type='consumivel',
                weight_grams='700 g',
                recipe_ingredients='Cenoura, farinha, ovos, açúcar, óleo, fermento e chocolate.',
            )
        )

    camiseta = Product.query.filter_by(name='Camiseta Básica').first()
    if not camiseta:
        camiseta = Product(
            name='Camiseta Básica',
            description='Camiseta confortável para uso diário.',
            price=Decimal('49.90'),
            stock=35,
            category_id=categories['Roupas'].id,
            image_url='https://images.unsplash.com/photo-1521572163474-6864f9cf17ab',
            product_type='utensilio',
            size_info='P, M, G e GG',
            material='Malha de algodão penteado',
        )
        db.session.add(camiseta)
        db.session.flush()

    if camiseta and camiseta.id:
        has_preto = ProductColorVariant.query.filter_by(
            product_id=camiseta.id,
            color_name='Preto',
        ).first()

        if not has_preto:
            db.session.add(
                ProductColorVariant(
                    product_id=camiseta.id,
                    color_name='Preto',
                    color_hex='#111111',
                    image_url='https://images.unsplash.com/photo-1521572163474-6864f9cf17ab',
                )
            )

        has_branco = ProductColorVariant.query.filter_by(
            product_id=camiseta.id,
            color_name='Branco',
        ).first()

        if not has_branco:
            db.session.add(
                ProductColorVariant(
                    product_id=camiseta.id,
                    color_name='Branco',
                    color_hex='#F9FAFB',
                    image_url='https://images.unsplash.com/photo-1503341504253-dff4815485f1',
                )
            )


def sync_owner_defaults() -> None:
    owner = User.query.filter_by(role='owner').order_by(User.id.asc()).first()
    if owner:
        AppSetting.set_value('owner_user_id', str(owner.id))
        AppSetting.set_value('owner_whatsapp_number', owner.phone)


def seed_all() -> None:
    ensure_settings()
    ensure_users()
    ensure_catalog()
    sync_owner_defaults()
    db.session.commit()