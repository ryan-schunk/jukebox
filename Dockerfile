FROM python:3.13-slim

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir .

COPY server.py .
COPY static/ static/

EXPOSE 8080

CMD ["python", "server.py"]
