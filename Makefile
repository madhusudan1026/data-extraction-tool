.PHONY: help install start stop models

help:
	@echo "Available commands:"
	@echo "  make install - Install dependencies"
	@echo "  make start   - Start Docker services"
	@echo "  make stop    - Stop services"
	@echo "  make models  - Download LLM models"

install:
	npm install
	cd backend && npm install

start:
	docker-compose up -d
	@echo "Services started!"
	@echo "Backend will run on: http://localhost:3000"
	@echo "Mongo Express: http://localhost:8081"

stop:
	docker-compose down

models:
	docker exec -it extraction-ollama ollama pull llama3.2
