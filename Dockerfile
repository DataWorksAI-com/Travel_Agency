FROM python:3.13-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    LANGSMITH_TRACING=false LANGCHAIN_TRACING_V2=false \
    ANONYMIZED_TELEMETRY=False DO_NOT_TRACK=1
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 app
WORKDIR /app
COPY requirements.txt /tmp/project-requirements.txt
COPY desktop/requirements.txt /tmp/local-requirements.txt
RUN pip install -r /tmp/project-requirements.txt -r /tmp/local-requirements.txt
COPY --chown=app:app app.py orchestrator.py orchestrator_agent.py orchestrator_config.py subagent_client.py flights_agent.py local_llm.py ./
COPY --chown=app:app ui/ ui/
COPY --chown=app:app sandbox/ sandbox/
COPY --chown=app:app destination_agent/ destination_agent/
COPY --chown=app:app destination_data/ destination_data/
COPY --chown=app:app airport_transport/ airport_transport/
COPY --chown=app:app money&customs_agent/ money&customs_agent/
COPY --chown=app:app desktop/bundled_data.py desktop/dining_policy.py desktop/
COPY --chown=app:app docker/start_web.py docker/start_web.py
RUN mkdir -p .chainlit && chown -R app:app /app
USER app
EXPOSE 8000
CMD ["python", "docker/start_web.py"]
