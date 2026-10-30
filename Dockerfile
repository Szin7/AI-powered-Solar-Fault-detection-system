FROM python:3.12.16-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
WORKDIR /app
COPY requirements.txt pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir -r requirements.txt && pip install --no-cache-dir --no-deps . \
    && useradd --create-home --uid 10001 solar
COPY scenarios ./scenarios
COPY data/README.md ./data/README.md
RUN mkdir -p var models reports data/generated && chown -R solar:solar /app
USER solar
EXPOSE 8000
CMD ["python", "-m", "solarsense", "serve", "--host", "0.0.0.0"]
