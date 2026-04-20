from decimal import Decimal


def format_brl(value: Decimal) -> str:
    text = f'{Decimal(value):,.2f}'
    return 'R$ ' + text.replace(',', 'X').replace('.', ',').replace('X', '.')


def build_receipt(store_name: str, order) -> str:
    lines = [
        f'COMPROVANTE - {store_name}',
        f"Pedido {order.code or ('#' + str(order.id))}",
        f'Cliente: {order.user.name}',
        'Forma de pagamento: PIX',
        f'Status do pedido: {order.status_display}',
        'Itens:',
    ]
    for item in order.items:
        lines.append(f'- {item.product_name} | {item.quantity} x {format_brl(item.unit_price)} = {format_brl(item.total_price)}')
    lines.extend([f'Total: {format_brl(order.subtotal)}', f'Pagamento: {order.payment_status_display}', 'Obrigado pela compra!'])
    return '\n'.join(lines)
