FROM python:3.11-slim

# Instala tesseract y dependencias
RUN apt-get update && apt-get install -y tesseract-ocr libtesseract-dev poppler-utils && rm -rf /var/lib/apt/lists/*

# Instala Python dependencies
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 10000

CMD ["python", "main.py"]
