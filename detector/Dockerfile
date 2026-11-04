FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY sentinel ./sentinel
RUN useradd --create-home appuser
USER appuser
CMD ["python", "-m", "sentinel.main"]
