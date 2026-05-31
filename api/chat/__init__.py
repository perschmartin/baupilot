"""BauPilot Chatbot-Modul.

Beantwortet projektinterne Fragen ueber strukturierte DB-Abfragen
(Tool-Use statt RAG). Lokal via LiteLLM-Gateway + Ollama qwen-32b.
SSE-Streaming-Antworten.

Konzept-Bezug:
  - §6 Schicht 4 KI-Assistenz (Konzept v0.4)
  - G1 Sachliche Neutralitaet, G2 Digitale Souveraenitaet
"""
from chat.router import router as chat_router

__all__ = ["chat_router"]
