FROM python:3.9-slim-buster
RUN apt-get update
RUN apt-get install xz-utils
RUN apt-get -y install curl
RUN curl -fsSL https://deb.nodesource.com/setup_19.x | bash - &&\
   apt-get install -y nodejs
RUN apt-get install -y build-essential
COPY main.py /src/main.py
COPY requirements.txt requirements.txt
RUN pip3 install -r requirements.txt

COPY . /app

# CMD ["gunicorn", "--conf", "wsgi.py", "--bind", "0.0.0.0:80", "app:wsgi"]
CMD ["python", "app/app.py", "-p","80","--host","0.0.0.0"]