FROM python:3.12-slim
WORKDIR /model-service
COPY semantic/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY semantic/model.json semantic/download_model.py ./
RUN python -u download_model.py
RUN python -m pip uninstall -y pip
RUN useradd --uid 10001 --create-home semantic
COPY semantic/server.py ./
COPY app/request_limits.py ./
USER semantic
ENV TOKENIZERS_PARALLELISM=false
CMD ["uvicorn","server:app","--host","0.0.0.0","--port","8080","--no-access-log"]
