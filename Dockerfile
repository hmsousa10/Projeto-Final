FROM python:3.14-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN python -m pip uninstall -y pip
RUN useradd --create-home --uid 10001 nexo && mkdir /app/data && chown nexo:nexo /app/data
COPY --chown=nexo:nexo app ./app
COPY --chown=nexo:nexo web ./web
COPY --chown=nexo:nexo evaluation ./evaluation
USER nexo
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--limit-concurrency", "32", "--backlog", "64", "--timeout-keep-alive", "5"]
