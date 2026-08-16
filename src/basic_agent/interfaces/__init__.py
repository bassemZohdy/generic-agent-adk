"""Interface adapters: REST, Live WebSocket, service API, MCP.

Modules are NOT imported eagerly — each adapter creates its FastAPI ``app``
at module level, and eager import would run ``create_app()`` during test
collection. Import the specific adapter module directly:

    from basic_agent.interfaces.rest import app
    from basic_agent.interfaces.live import app
"""
