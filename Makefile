SHELL := /bin/bash
.PHONY: help sample-data fetch-data qlib-sample up down logs dev-backend dev-frontend clean clean-all

help:
	@echo "QuantLab OSS — 常用命令"
	@echo "  make sample-data    生成样例行情库 data/market.db（首次必跑）"
	@echo "  make fetch-data     拉取真实行情（近 1 年 × 300 只）覆盖 data/market.db"
	@echo "  make qlib-sample    由 data/market.db 构建 Qlib 数据集（可选）"
	@echo "  make up             Docker 一键启动（前端 :8080 / 后端 :5001）"
	@echo "  make down           停止并移除容器"
	@echo "  make logs           查看容器日志"
	@echo "  make dev-backend    本地开发：后端（热重载）"
	@echo "  make dev-frontend   本地开发：前端（vite）"
	@echo "  make clean          清理生成数据"

sample-data:
	python3 examples/make_sample_data.py

# 真实行情（纯标准库直连公开接口，无需 token）。
# 自定义：make fetch-data ARGS="--top 50"  /  ARGS="--symbols 600519,000001"
fetch-data:
	python3 scripts/fetch_real_data.py $(ARGS)

qlib-sample:
	python3 scripts/build_qlib_sample.py

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f

dev-backend:
	cd backend && uvicorn main:app --reload --host 0.0.0.0 --port 5001

dev-frontend:
	cd frontend && npm install && npm run dev

clean:
	rm -rf data/market.db qlib_data

# 保留备份的清理（fetch-data 会把旧库备份成 market.db.bak）
clean-all: clean
	rm -f data/market.db.bak
