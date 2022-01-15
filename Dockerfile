FROM python:3.10
ENV PYTHONUNBUFFERED 1

WORKDIR /app

RUN pip install pip==21.2.4 pip-tools==6.2.0
COPY requirements.txt /app/
RUN pip install -r requirements.txt

COPY api.py /app/
