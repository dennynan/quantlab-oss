# Contributing to QuantLab OSS

感谢有兴趣参与！欢迎 Issue 与 PR。

## 开发环境

```bash
# 1) 样例数据（首次必跑）
make sample-data

# 2) 后端
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 5001

# 3) 前端
cd frontend
npm install
npm run dev
```

或直接 `make up` 用 Docker 一键起。

## 提交规范

- 分支：`feat/xxx`、`fix/xxx`、`docs/xxx`
- 提交信息：`<type>: <subject>`（type ∈ feat/fix/docs/refactor/test/chore）
- 保持改动聚焦，一个 PR 做一件事
- 新增依赖请更新 `backend/requirements.txt`（锁版本）

## PR 检查清单

- [ ] 本地能起（`make up` 或 dev 模式）
- [ ] 未引入密钥 / 个人路径 / 生产数据
- [ ] 相关文档同步更新
- [ ] commit message 规范

## 代码风格

- Python：PEP8，函数职责单一，关键逻辑加注释
- 前端：Vue 3 `<script setup>` + Composition API
