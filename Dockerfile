# One service: the React site and the FastAPI API on the same origin (secure session cookies).
# Stage 1 builds the frontend; stage 2 runs the API and serves frontend/dist. (Pattern from the author's tracker.)

FROM node:22-slim AS site
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend/ backend/
# Only the fictional demo dataset: real users' data lives in the database (DATABASE_URL).
COPY data/demo/ data/demo/
COPY --from=site /app/frontend/dist frontend/dist
RUN useradd --create-home app && chown -R app /app
USER app
# --proxy-headers: Render terminates HTTPS, so trust its X-Forwarded-Proto for secure cookies.
CMD uvicorn main:app --app-dir backend --host 0.0.0.0 --port ${PORT:-10000} --proxy-headers --forwarded-allow-ips="*"
