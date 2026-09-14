FROM python:3.12-alpine

WORKDIR /app

COPY . /app

RUN cp HW1-Nathan_Pak.html index.html

EXPOSE 8000

CMD ["python", "-m", "http.server", "8000", "--directory", "/app"]
