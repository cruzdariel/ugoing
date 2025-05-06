FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1

WORKDIR /

COPY . .

RUN pip install --no-cache-dir -r requirements.txt

CMD ["python3", "app.py"]