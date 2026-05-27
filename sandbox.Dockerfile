FROM python:3.12-slim
RUN pip install hypothesis pytest --no-cache-dir
RUN adduser --disabled-password --uid 1001 sandbox
USER sandbox
WORKDIR /workspace
