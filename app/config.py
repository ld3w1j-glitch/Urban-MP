from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
INSTANCE_DIR = PROJECT_ROOT / 'instance'


class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'troque-esta-chave-em-producao')
    SQLALCHEMY_DATABASE_URI = f"sqlite:///{INSTANCE_DIR / 'loja_flex_final.db'}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    STORE_NAME = os.getenv('STORE_NAME', 'Loja Flex Final')
    PUBLIC_BASE_URL = os.getenv('PUBLIC_BASE_URL', '').strip()
