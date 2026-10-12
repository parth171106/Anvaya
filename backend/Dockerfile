ARG PYTHON_IMAGE=python:3-slim
FROM ${PYTHON_IMAGE}
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv
COPY backend/requirements.lock backend/pyproject.toml ./
RUN pip install --no-cache-dir -r requirements.lock
COPY backend/app ./app
COPY generator ./generator
COPY collectors ./collectors
EXPOSE 8000 5514/udp
CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
