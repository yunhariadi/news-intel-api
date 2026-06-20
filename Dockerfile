# Single image for both api and worker (compose overrides the command).
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app

WORKDIR /app

# `pip install .` builds THIS project, so setuptools needs the apps/ package
# tree present to generate metadata — copy the source before installing.
# (packages/ is vendored via PYTHONPATH=/app rather than pip-installed; see
# pyproject [tool.setuptools].)
COPY pyproject.toml ./
COPY apps ./apps
COPY packages ./packages
RUN pip install --upgrade pip && pip install .

EXPOSE 8000

# Default command; docker-compose overrides per service (api vs worker).
CMD ["uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
