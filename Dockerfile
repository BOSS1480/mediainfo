FROM python:3.9-slim

RUN apt-get update && apt-get install -y mediainfo

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8080

CMD ["python", "flask_server.py"]
