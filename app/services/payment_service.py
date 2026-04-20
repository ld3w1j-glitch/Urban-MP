from __future__ import annotations

from decimal import Decimal
from pathlib import Path
import qrcode


def _field(field_id: str, value: str) -> str:
    return f"{field_id}{len(value):02d}{value}"


def _crc16(payload: str) -> str:
    polynomial = 0x1021
    result = 0xFFFF
    for byte in payload.encode('utf-8'):
        result ^= byte << 8
        for _ in range(8):
            if result & 0x8000:
                result = (result << 1) ^ polynomial
            else:
                result <<= 1
            result &= 0xFFFF
    return f'{result:04X}'


def build_pix_payload(pix_key: str, amount: Decimal, merchant_name: str, merchant_city: str, txid: str) -> str:
    merchant_name = merchant_name[:25].upper()
    merchant_city = merchant_city[:15].upper()
    gui = _field('00', 'br.gov.bcb.pix')
    key = _field('01', pix_key)
    merchant_account = _field('26', gui + key)
    payload = ''.join([
        _field('00', '01'), _field('01', '11'), merchant_account, _field('52', '0000'), _field('53', '986'),
        _field('54', f'{Decimal(amount):.2f}'), _field('58', 'BR'), _field('59', merchant_name), _field('60', merchant_city), _field('62', _field('05', txid[:25])), '6304'
    ])
    return payload + _crc16(payload)


def generate_qr_code(payload: str, output_path: Path) -> str:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    img = qrcode.make(payload)
    img.save(output_path)
    return str(output_path)


def ensure_order_pix_data(order_id: int, amount: Decimal, root_path: Path, pix_key: str, merchant_name: str, merchant_city: str) -> tuple[str, str]:
    payload = build_pix_payload(pix_key, amount, merchant_name, merchant_city, f'PEDIDO{order_id}')
    qr_path = root_path / 'static' / 'uploads' / 'qr' / f'order_{order_id}.png'
    generate_qr_code(payload, qr_path)
    return payload, f'uploads/qr/order_{order_id}.png'
