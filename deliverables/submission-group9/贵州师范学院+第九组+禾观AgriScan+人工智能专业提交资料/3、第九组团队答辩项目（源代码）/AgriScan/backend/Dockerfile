FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt requirements-inference.txt requirements-media.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-media.txt
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./alembic.ini
RUN groupadd --gid 10001 agriscan && useradd --uid 10001 --gid agriscan --no-create-home agriscan \
    && mkdir -p /app/uploads /app/data && chown -R agriscan:agriscan /app
USER agriscan
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
