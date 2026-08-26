"""UI layer: the Chainlit front end and the real-vs-dummy agent seam.

Nothing in here is an agent. app.py calls plan_trip; agent_seam.py decides,
below the UI, which client each orchestrator slot gets.
"""
