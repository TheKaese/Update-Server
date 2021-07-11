FROM alpine:latest
RUN apk add --update --no-cache python3 py-pip

COPY . /www/UpdateServer
WORKDIR /www/UpdateServer
RUN pip install --ignore-installed -r requirements.txt

RUN chmod +x /www/UpdateServer/server.py
RUN hostname
ENTRYPOINT ["python3", "/www/UpdateServer/server.py"]
