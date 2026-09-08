FROM python:3.12-slim

WORKDIR /app

COPY extractor/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY warehouse/ ./warehouse/
COPY extractor/ ./

CMD ["python", "main.py"]
