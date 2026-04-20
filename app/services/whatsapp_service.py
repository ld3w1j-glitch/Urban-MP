from urllib.parse import quote


def only_digits(value: str) -> str:
    return ''.join(ch for ch in (value or '') if ch.isdigit())


def build_whatsapp_link(phone: str, message: str) -> str:
    phone_digits = only_digits(phone)
    if not phone_digits:
        return ''
    return f'https://wa.me/{phone_digits}?text={quote(message)}'


def build_owner_order_message(store_name: str, order, admin_order_url: str) -> str:
    lines = [
        f'Novo pedido recebido na {store_name}.', '', f"Pedido: {order.code or ('#' + str(order.id))}",
        f'Cliente: {order.user.name}', f'Telefone do cliente: {order.user.phone}',
        f"Total: R$ {float(order.subtotal):.2f}".replace('.', ','), '', 'Itens:'
    ]
    for item in order.items:
        lines.append(f'- {item.product_name} | Qtd: {item.quantity}')
    lines.extend(['', 'Abra este link para aprovar ou recusar no painel:', admin_order_url])
    return '\n'.join(lines)


def build_customer_status_message(store_name: str, order) -> str:
    if order.status == 'accepted':
        status_text = 'Seu pedido foi APROVADO e aguarda pagamento.'
    elif order.status == 'rejected':
        status_text = 'Seu pedido foi RECUSADO.'
    elif order.status == 'completed':
        status_text = 'Seu pedido foi finalizado.'
    elif order.status == 'cancelled':
        status_text = 'Seu pedido foi cancelado por você.'
    else:
        status_text = 'Seu pedido está aguardando aprovação.'
    return f'Olá, aqui é da {store_name}.\nPedido: {order.code or ("#" + str(order.id))}\nStatus: {status_text}\nPagamento: {order.payment_status_display}'
