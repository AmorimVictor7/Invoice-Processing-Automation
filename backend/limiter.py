"""
Instância global do rate limiter (slowapi).
Módulo separado para evitar import circular entre main.py e os routers.
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
