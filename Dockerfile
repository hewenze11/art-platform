FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN mkdir -p /data/uploads
ENV CONFIG_PATH=/app/project.yaml
ENV DATA_DIR=/data
EXPOSE 8899
CMD ["python", "app.py"]
