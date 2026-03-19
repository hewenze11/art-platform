FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN mkdir -p /data/uploads
ENV DATA_DIR=/data
ENV PORT=8899
EXPOSE 8899
CMD ["python", "app.py"]
