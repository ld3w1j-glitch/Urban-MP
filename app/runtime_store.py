from __future__ import annotations

from datetime import datetime

from .models import AppSetting


def _parse_time(value: str, fallback: str):
    text = (value or fallback).strip() or fallback
    try:
        return datetime.strptime(text, '%H:%M').time()
    except ValueError:
        return datetime.strptime(fallback, '%H:%M').time()


def get_store_schedule_settings() -> dict:
    return {
        'manual_enabled': AppSetting.get_value('store_enabled', 'true') == 'true',
        'schedule_enabled': AppSetting.get_value('schedule_enabled', 'false') == 'true',
        'opening_time': AppSetting.get_value('opening_time', '08:00'),
        'closing_time': AppSetting.get_value('closing_time', '18:00'),
    }


def is_store_open_now() -> bool:
    settings = get_store_schedule_settings()
    if not settings['manual_enabled']:
        return False
    if not settings['schedule_enabled']:
        return True
    now = datetime.now().time()
    opening = _parse_time(settings['opening_time'], '08:00')
    closing = _parse_time(settings['closing_time'], '18:00')
    if opening == closing:
        return True
    if opening < closing:
        return opening <= now <= closing
    return now >= opening or now <= closing


def get_store_offline_message() -> str:
    settings = get_store_schedule_settings()
    if not settings['manual_enabled']:
        return 'A loja está offline no momento. Tente novamente mais tarde.'
    if settings['schedule_enabled']:
        return 'A loja está fora do horário de funcionamento. Atendimento local entre ' + settings['opening_time'] + ' e ' + settings['closing_time'] + '.'
    return 'A loja está indisponível no momento.'
