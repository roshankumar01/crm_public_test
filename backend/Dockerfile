FROM python:3.13-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && useradd --create-home --uid 10001 crm

COPY --chown=crm:crm app ./app
COPY --chown=crm:crm seed_courses.py ./seed_courses.py
USER crm

EXPOSE 8000
CMD ["python", "-m", "app.docker_start"]
