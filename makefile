SHELL=/bin/bash
VENV=venv

.PHONY: run stop freeze build install uninstall

run:
	@docker-compose up --remove-orphans

stop:
	@docker-compose down --remove-orphans

freeze:
	@pip freeze > requirements.txt

build:
	@docker-compose build

install:
	@virtualenv -p python3.10 $(VENV)
	@source $(VENV)/bin/activate && pip install -r requirements.txt

uninstall:
	@rm -rf $(VENV)

