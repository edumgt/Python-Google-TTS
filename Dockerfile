FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# git is required because the app clones public GitHub repositories at runtime.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/media /app/workspace_repos

EXPOSE 8000

CMD ["uvicorn", "repo_voice_analyzer.fastapi_app:app", "--host", "0.0.0.0", "--port", "8000"]
