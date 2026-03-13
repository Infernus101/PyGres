FROM python:3.12-slim

RUN addgroup --system app && adduser --system --ingroup app --no-create-home app

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

USER app

EXPOSE 8000

CMD ["uvicorn", "main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--no-server-header", \
     "--proxy-headers", \
     "--forwarded-allow-ips=*"]
