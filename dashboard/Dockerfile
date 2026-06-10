FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV DASHBOARD_PORT=8080
EXPOSE 8080
HEALTHCHECK --interval=20s --timeout=5s CMD curl -f http://localhost:8080/ || exit 1
CMD ["python", "app.py"]
