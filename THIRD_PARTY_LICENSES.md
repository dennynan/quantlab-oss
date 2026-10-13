# 第三方依赖许可证（THIRD_PARTY_LICENSES）

本项目（**QuantLab OSS · 策略实验室开源版**）以 **MIT** 许可证发布。

以下清单由 [`pip-licenses`](https://github.com/raimon49/pip-licenses) 依据 `backend/requirements.txt` 锁定的运行环境自动生成，仅列**直接依赖**；各依赖自身的传递依赖（transitive dependencies）可能另有其许可证，以对应包的官方仓库为准。

## 直接依赖

| 名称 | 版本 | 许可证 | 主页 |
|------|------|--------|------|
| json5 | 0.14.0 | Apache-2.0 | https://github.com/dpranke/pyjson5 |
| requests | 2.34.2 | Apache-2.0 | https://github.com/psf/requests |
| python-multipart | 0.0.32 | Apache-2.0 | https://github.com/Kludex/python-multipart |
| Jinja2 | 3.1.6 | BSD-3-Clause | https://github.com/pallets/jinja/ |
| pandas | 2.3.3 | BSD-3-Clause | https://pandas.pydata.org |
| scipy | 1.17.1 | BSD-3-Clause | https://scipy.org/ |
| scikit-learn | 1.9.0 | BSD-3-Clause | https://scikit-learn.org |
| uvicorn | 0.49.0 | BSD-3-Clause | https://uvicorn.dev/ |
| numpy | 2.4.6 | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 | https://numpy.org |
| SQLAlchemy | 2.0.50 | MIT | https://www.sqlalchemy.org |
| fastapi | 0.136.3 | MIT | https://github.com/fastapi/fastapi |
| pydantic | 2.13.4 | MIT | https://github.com/pydantic/pydantic |
| lightgbm | 4.6.0 | MIT | https://github.com/microsoft/LightGBM |
| pyqlib | 0.9.7 | MIT | https://github.com/microsoft/qlib |

> 版本号与 `backend/requirements.txt` 的锁定版本一致。以上均为宽松许可证（MIT / BSD / Apache-2.0），可与本项目 MIT 许可证兼容地分发。

## 复现命令

```bash
pip install pip-licenses
pip-licenses --format=markdown --with-urls --order=license \
  --packages fastapi uvicorn pydantic SQLAlchemy python-multipart Jinja2 \
             requests json5 pandas numpy scipy scikit-learn lightgbm pyqlib
```

## 说明与免责

- 本清单由包元数据自动生成，个别包元数据可能不完整（如 `pyqlib` 未声明主页），请以官方仓库为准。
- 若你二次分发本项目，请一并遵守上述各依赖的许可证条款。
