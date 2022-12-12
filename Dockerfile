FROM python:3.10-slim-buster

WORKDIR /python-docker

COPY requirements.txt requirements.txt
RUN pip3 install -r requirements.txt

COPY . .

CMD ["gunicorn", "--conf", "wsgi.py", "--bind", "0.0.0.0:80", "-k", "eventlet", "-w", "1", "app:app"]