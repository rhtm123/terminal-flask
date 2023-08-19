FROM nikolaik/python3.10-nodejs16-slim
RUN apt-get install -y npm
COPY main.py /src/main.py
COPY requirements.txt requirements.txt
RUN pip3 install -r requirements.txt

COPY . /app

# CMD ["gunicorn", "--conf", "wsgi.py", "--bind", "0.0.0.0:80", "app:wsgi"]
CMD ["python", "app/app.py", "-p","80","--host","0.0.0.0"]