"""
Route modules for Bifröst gateway
"""

from . import admin, chat, debug, embeddings, health, trace

__all__ = ["chat", "embeddings", "health", "debug", "trace", "admin"]
