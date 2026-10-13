"""
RD-Agent 自动因子挖掘服务
==========================
- 通过 subprocess 拉起独立 conda 环境里的 rdagent CLI（fin_factor 纯因子场景）
- 异步后台运行，实时解析 stdout 日志识别 5 阶段进度（main 分支新增 record 阶段）
- 运行结束后 diff workspace 目录，解析因子代码 + 回测指标 + SOTA 对比 + 复盘结论
- 结果只读展示（人工筛选），不自动落因子库

依赖：RD-Agent 已在本机跑通（安装见 README「RD-Agent（可选）」），
本服务只负责「发起任务 + 读结果」，绝不 import rdagent 包（环境隔离）。
"""
import ast
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

from config import rel_path

# ────────────────────────────────────────────────────────────────
#  路径常量（RD-Agent 独立 conda 环境，与 QuantLab venv 完全隔离）
# ────────────────────────────────────────────────────────────────
_HOME = Path.home()
# 开源版默认把 RD-Agent 的工作目录放在**仓库内** data/rdagent_demo，
# 与机器上其他 RD-Agent 部署（例如 ~/rdagent_demo）彻底隔离。
# 可用环境变量覆盖：RDAGENT_HOME（RD-Agent 工作目录）、CONDA_ROOT（conda 根目录）、
# RDAGENT_CONDA_ENV（conda 环境名，默认取 <RDAGENT_HOME>/.env 的 CONDA_ENV_NAME）。
_REPO_ROOT = Path(__file__).resolve().parents[2]
RDAGENT_DIR = Path(os.environ.get("RDAGENT_HOME", str(_REPO_ROOT / "data" / "rdagent_demo")))
CONDA_ROOT = Path(os.environ.get("CONDA_ROOT", str(_HOME / "miniforge3")))


def _env_file_value(name: str, default=None):
    """从 <RDAGENT_HOME>/.env 读单个键（启动时静态读取）"""
    try:
        p = RDAGENT_DIR / ".env"
        if p.exists():
            for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
                s = line.strip()
                if not s or s.startswith("#") or "=" not in s:
                    continue
                k, _, v = s.partition("=")
                if k.strip() == name:
                    return v.strip().strip('"').strip("'") or default
    except Exception:
        pass
    return default


# conda 环境名：环境变量 > <RDAGENT_HOME>/.env 的 CONDA_ENV_NAME > rdagent
# （后者让「端口隔离」只靠改 RDAGENT_HOME + 其 .env 就能完成，不必另设后端环境变量）
RDAGENT_CONDA_ENV = (os.environ.get("RDAGENT_CONDA_ENV")
                     or _env_file_value("CONDA_ENV_NAME")
                     or "rdagent")
RDAGENT_ENV_BIN = CONDA_ROOT / "envs" / RDAGENT_CONDA_ENV / "bin"
RDAGENT_PYTHON = RDAGENT_ENV_BIN / "python"
RDAGENT_CLI = RDAGENT_ENV_BIN / "rdagent"
RDAGENT_WORKSPACE = RDAGENT_DIR / "git_ignore_folder" / "RD-Agent_workspace"
# 每任务会话检查点根目录（用 LOG_TRACE_PATH 环境变量强制落盘到此，方便续跑定位）
RDAGENT_SESSION_DIR = RDAGENT_DIR / "log" / "jobs"

# QuantLab 侧持久化目录（轻量 JSON，不引入新表）
DATA_DIR = Path(__file__).resolve().parents[2] / "data"
RDAGENT_DATA_DIR = DATA_DIR / "rdagent"
RDAGENT_DATA_DIR.mkdir(parents=True, exist_ok=True)
JOBS_PATH = RDAGENT_DATA_DIR / "jobs.json"

# ────────────────────────────────────────────────────────────────
#  过线门禁（提示性质：只标记不拦截，不影响导出/回测）
#  口径用「统计显著性 + 经济意义」双条件；调整阈值改这里即可
#  来源：Kronos P0-2c 教训 —— 只看 IC 容易被事后选择偏差骗，必须要求真金白银为正
# ────────────────────────────────────────────────────────────────
GATE_RANK_IC = 0.03
GATE_RANK_ICIR = 0.3
GATE_ANN_RET_COST = 0.0     # 年化收益（含成本）必须为正
GATE_IR_COST = 0.5          # 信息比率（含成本）


def _build_gate(backtest: dict) -> dict:
    """根据回测指标判定是否「过线」（提示用，不拦截任何操作）"""
    bt = backtest or {}
    rank_ic = bt.get("Rank IC")
    rank_icir = bt.get("Rank ICIR")
    ann_cost = bt.get("annualized_return_with_cost")
    ir_cost = bt.get("information_ratio_with_cost")

    def _chk(v, threshold):
        if v is None:
            return None
        return bool(v > threshold)

    checks = {
        f"Rank IC > {GATE_RANK_IC}": _chk(rank_ic, GATE_RANK_IC),
        f"Rank ICIR > {GATE_RANK_ICIR}": _chk(rank_icir, GATE_RANK_ICIR),
        "年化收益(含成本) > 0": _chk(ann_cost, GATE_ANN_RET_COST),
        f"信息比率(含成本) > {GATE_IR_COST}": _chk(ir_cost, GATE_IR_COST),
    }
    missing = [k for k, v in checks.items() if v is None]
    failed = [k for k, v in checks.items() if v is False]
    passed = bool(checks) and not missing and not failed
    if missing:
        reason = "指标缺失，无法判定：" + "、".join(missing)
    elif passed:
        reason = "四项全部通过"
    else:
        reason = "未通过：" + "、".join(failed)
    return {"pass": passed, "checks": checks, "reason": reason}

# ────────────────────────────────────────────────────────────────
#  阶段映射（对应日志 "Start Loop N, Step S: xxx"）
# ────────────────────────────────────────────────────────────────
STEPS = {
    "direct_exp_gen": {"label": "提假设", "idx": 0},
    "coding": {"label": "写代码", "idx": 1},
    "running": {"label": "回测验证", "idx": 2},
    "feedback": {"label": "复盘", "idx": 3},
    "record": {"label": "记录", "idx": 4},
}

# 全局运行状态（同一时间只允许 1 个任务）
RDAGENT_STATUS = {
    "running": False,
    "job_id": None,
    "loop": 0,
    "step": "",
    "step_label": "",
    "progress_pct": 0,
    "message": "",
    "started": None,
    "finished": None,
    "error": None,
}

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
_STEP_RE = re.compile(r"Start Loop (\d+), Step (\d+): ([a-z_]+)")


# ────────────────────────────────────────────────────────────────
#  任务历史持久化
# ────────────────────────────────────────────────────────────────
def _load_jobs() -> list:
    if JOBS_PATH.exists():
        try:
            data = json.loads(JOBS_PATH.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return data
        except Exception:
            pass
    return []


def _save_jobs(jobs: list):
    try:
        JOBS_PATH.write_text(json.dumps(jobs, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        # 不再静默吞掉：写失败会丢历史记录（2026-09-20 那次「秒失败且无记录」无法回溯）
        print(f"[rdagent][warn] _save_jobs 失败: {e}")


def _job_log_path(job_id: str) -> Path:
    return RDAGENT_DATA_DIR / f"{job_id}.log"


def _job_record(job_id: str) -> dict | None:
    """从 jobs.json 取单条任务记录（取不到返回 None）。"""
    for j in _load_jobs():
        if j.get("job_id") == job_id:
            return j
    return None


def _job_elapsed_seconds(job_id: str) -> float:
    """本轮已运行秒数（优先 jobs.json 的 started，兜底内存状态）。"""
    rec = _job_record(job_id) or {}
    started = rec.get("started") or RDAGENT_STATUS.get("started")
    if not started:
        return 0.0
    try:
        return max(0.0, (datetime.now() - datetime.fromisoformat(str(started))).total_seconds())
    except Exception:
        return 0.0


# ────────────────────────────────────────────────────────────────
#  命令构建
# ────────────────────────────────────────────────────────────────
def _session_path(job_id: str) -> Path:
    """本任务会话检查点目录（__session__）"""
    return RDAGENT_SESSION_DIR / job_id / "__session__"


def _build_command(loop_n: int, job_id: str, resume_path: str = None) -> str:
    """沿用已验证的启动方式：导出 PATH + source .env + conda 环境 + python 调 rdagent 入口

    注意：必须先 export PATH 让 rdagent 父进程的 os.environ['PATH'] 包含 conda 环境，
    否则因子执行子进程（env.py L524 构造 PATH）会回落到系统 Python，qlib 回测失败。

    续跑：传 resume_path 时追加 --path 指向上次会话的 __session__ 检查点目录，
    RD-Agent 会 pickle 恢复完整会话（trace/假设/SOTA 基线/已挖因子）后继续。
    LOG_TRACE_PATH 强制会话落盘到可定位目录（新任务单独一个；续跑任务的实际
    检查点因 checkout=False 仍锚定在原会话目录，由 jobs.json 的 session_path 追踪）。
    """
    resume_flag = f' --path "{resume_path}"' if resume_path else ""
    rdagent_dir = str(RDAGENT_DIR)
    env_bin = str(RDAGENT_ENV_BIN)
    conda_bin = str(CONDA_ROOT / "bin")
    rdagent_py = str(RDAGENT_PYTHON)
    rdagent_cli = str(RDAGENT_CLI)
    return (
        f"cd {rdagent_dir} && "
        f"export PATH=\"{env_bin}:{conda_bin}:$PATH\" && "
        "bash -c 'set -a; source .env; set +a; "
        f"export CONDA_DEFAULT_ENV={RDAGENT_CONDA_ENV} PYTHONUNBUFFERED=1; "
        f"export LOG_TRACE_PATH={rdagent_dir}/log/jobs/{job_id}; "
        f"{rdagent_py} "
        f"{rdagent_cli} "
        f"fin_factor --loop-n {loop_n} --no-checkout{resume_flag}'"
    )


# ────────────────────────────────────────────────────────────────
#  进度解析
# ────────────────────────────────────────────────────────────────
def _update_progress_from_log(job_id: str, loop_n: int):
    """读取日志尾部，识别最新阶段，更新 RDAGENT_STATUS"""
    log_path = _job_log_path(job_id)
    if not log_path.exists():
        return
    try:
        text = log_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return
    matches = _STEP_RE.findall(text)
    if matches:
        loop, step_idx, step_name = matches[-1]
        loop, step_idx = int(loop), int(step_idx)
        info = STEPS.get(step_name, {"label": step_name, "idx": step_idx})
        RDAGENT_STATUS["loop"] = loop
        RDAGENT_STATUS["step"] = step_name
        RDAGENT_STATUS["step_label"] = info["label"]
        # 粗略进度：已完成 step 数 / 总 step 数（main 分支每 loop 5 步）
        total_steps = max(loop_n, 1) * 5
        done_steps = loop * 5 + step_idx
        RDAGENT_STATUS["progress_pct"] = min(95, int(done_steps / total_steps * 100))
        RDAGENT_STATUS["message"] = f"Loop {loop} · {info['label']}"


# ────────────────────────────────────────────────────────────────
#  结果解析
# ────────────────────────────────────────────────────────────────
def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


def _parse_qlib_res(path) -> dict:
    """解析 qlib_res.csv → 关键指标 dict"""
    metrics = {}
    path = Path(path)
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if "," not in line:
                continue
            key, _, val = line.partition(",")
            key = key.strip()
            val = val.strip()
            if not key:
                continue
            try:
                metrics[key] = float(val)
            except ValueError:
                metrics[key] = val
    except Exception:
        pass
    return metrics


def _pick_metric(metrics: dict, *keys):
    for k in keys:
        if k in metrics:
            return metrics[k]
    return None


def _extract_factor_name(code: str) -> str:
    m = re.search(r"def\s+calculate_(\w+)", code)
    return m.group(1) if m else None


def _extract_sota_comparison(log_text: str) -> dict:
    """从日志 Combined Results 行提取「最终一轮」的 当前 vs SOTA 对比。

    ⚠️ 每轮迭代都会打印一行对比，必须取**最后一次**匹配：用 re.search 拿到的是
    每轮第一行（Loop 0）的数字，与页面上「回测结果」（最终会话状态）来自不同轮次，
    会出现「与 SOTA 对比不像这轮回测结果」的现象。
    """
    cmp = {}
    patterns = [
        # (?<!Rank ) 防止误抓未来可能新增的 "Rank IC of Current Result is ..."
        ("IC", r"(?<!Rank )IC of Current Result is ([-\d.e]+), of SOTA Result is ([-\d.e]+)"),
        ("annualized_return_with_cost",
         r"annualized_return of Current Result is ([-\d.e]+), of SOTA Result is ([-\d.e]+)"),
        ("max_drawdown_with_cost",
         r"max_drawdown of Current Result is ([-\d.e]+), of SOTA Result is ([-\d.e]+)"),
        ("calmar_with_cost",
         r"Calmar \(= annualized_return / \|max_drawdown\|, with cost\) of Current Result is "
         r"([-\d.e]+), of SOTA Result is ([-\d.e]+)"),
    ]
    for key, pat in patterns:
        matches = re.findall(pat, log_text)
        if not matches:
            continue
        cur, sota = matches[-1]
        try:
            cmp[key] = {"current": float(cur), "sota": float(sota)}
        except ValueError:
            pass
    return cmp


def _extract_skip_reason(log_text: str) -> dict:
    """兜底说明：RDLoop 跳圈（如「提案因子全部与历史重复」）时日志里没有复盘 JSON，
    这里从 'Skip loop N due to ...' 提取原因，返回一条可展示的说明，避免前端空白。

    ⚠️ 同 _extract_sota_comparison：多圈日志里会多次出现该行，取**最后一次**
    （最近一次跳圈），用 re.search 会把第一圈的原因当成本轮的。
    """
    ms = re.findall(r"Skip loop \d+ due to (.+)", log_text)
    if not ms:
        return None
    reason = ms[-1].strip().rstrip("：:").strip()
    if not reason:
        reason = "本轮任务失败，未产出因子"
    return {
        "Observations": f"⚠️ 本轮未产出因子，挖掘循环被跳过：{reason}",
        "Feedback for Hypothesis": "本轮没有生成新的因子与回测结果，历史 SOTA 组合保持不变。",
    }


def _extract_feedback(log_text: str) -> dict:
    """提取最后一次复盘 JSON（Observations / Feedback / New Hypothesis）。
    日志里没有复盘 JSON 时兜底提取跳圈原因，避免页面空白。"""
    key = '"Observations"'
    idx = log_text.rfind(key)
    if idx < 0:
        return _extract_skip_reason(log_text)
    start = log_text.rfind("{", 0, idx)
    if start < 0:
        return None
    # 花括号匹配（处理字符串内的花括号与转义）
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(log_text)):
        c = log_text[i]
        if esc:
            esc = False
            continue
        if c == "\\" and in_str:
            esc = True
            continue
        if c == '"':
            in_str = not in_str
        elif not in_str:
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(log_text[start:i + 1])
                    except Exception:
                        return None
    return None


def _translate_via_llm(prompt: str) -> str:
    """调用 DeepSeek 翻译/生成，返回文本回复；失败或无 key 时返回 None"""
    api_key = os.environ.get("QUANTLAB_LLM_API_KEY", "")
    if not api_key:
        return None
    try:
        import requests
        resp = requests.post(
            "https://api.deepseek.com/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": "deepseek-chat",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.3,
                "max_tokens": 4000,
            },
            timeout=60,
        )
        if resp.status_code == 200:
            return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"[RD-Agent] LLM 翻译失败: {e}")
    return None


def _clean_json_output(content: str) -> str:
    """去掉 LLM 输出可能包裹的 markdown 代码块/前缀"""
    content = content.strip().strip("`")
    if content.lower().startswith("json"):
        content = content[4:].strip()
    return content


def _translate_feedback(feedback: dict) -> dict:
    """把复盘结论的英文字段翻译成中文（失败时保留原文）"""
    if not feedback:
        return feedback
    text_fields = ["Observations", "Feedback for Hypothesis", "New Hypothesis", "Reasoning"]
    items = [(k, feedback[k]) for k in text_fields
             if isinstance(feedback.get(k), str) and feedback[k].strip()]
    if not items:
        return feedback
    payload = json.dumps({k: v for k, v in items}, ensure_ascii=False)
    content = _translate_via_llm(
        "把下面 JSON 对象里每个字段的英文值翻译成简洁、专业的中文（金融量化语境），"
        "保持 JSON 结构不变，只输出 JSON 本体，不要 markdown 代码块、不要任何解释：\n" + payload
    )
    if not content:
        return feedback
    try:
        translated = json.loads(_clean_json_output(content))
    except Exception:
        return feedback
    if not isinstance(translated, dict):
        return feedback
    out = dict(feedback)
    for k, _ in items:
        v = translated.get(k)
        if isinstance(v, str) and v.strip():
            out[k] = v
    return out


def _translate_factor_names(factors: list) -> list:
    """给每个因子加 factor_name_cn 字段（失败时保留原名）"""
    if not factors:
        return factors
    names = [f.get("factor_name") for f in factors if f.get("factor_name")]
    if not names:
        return factors
    payload = json.dumps(names, ensure_ascii=False)
    content = _translate_via_llm(
        "把下面英文因子名逐个翻译成简洁中文（量化语境，如 5d_momentum → 5日动量、"
        "mean_reversion → 均值回归、daily_range → 日振幅、volume_price_trend → 量价趋势）。"
        "只输出 JSON 字符串数组，与输入顺序一一对应，不要 markdown 代码块、不要任何解释：\n" + payload
    )
    if not content:
        return factors
    try:
        translated = json.loads(_clean_json_output(content))
    except Exception:
        return factors
    if not isinstance(translated, list):
        return factors
    for f, cn in zip(factors, translated):
        if isinstance(cn, str) and cn.strip():
            f["factor_name_cn"] = cn
    return factors


def _snapshot_workspace() -> dict:
    """记录 workspace 下每个目录的 mtime。

    不能用「目录名集合 + 差集」判定本轮产物：续跑（--no-checkout 复用旧会话）时
    RD-Agent 会复用上次的哈希目录名，只是覆盖里面的文件，目录名不变 → 差集为空。
    改用 mtime 比对，才能识别「已存在但本轮被改写」的目录。
    """
    if not RDAGENT_WORKSPACE.exists():
        return {}
    snap = {}
    for p in RDAGENT_WORKSPACE.iterdir():
        if not p.is_dir():
            continue
        try:
            snap[p.name] = p.stat().st_mtime
        except Exception:
            snap[p.name] = 0
    return snap


def _read_combined_factors(dir_name: str) -> list:
    """读本轮回测 combined_factors_df.parquet 的因子列名（= 回测时实际生效的组合）

    用独立 rdagent 环境（有 pyarrow）只读 schema，避免在 QuantLab venv 引入重依赖。
    返回因子名列表（不含 datetime/instrument 索引列）。
    """
    parquet = RDAGENT_WORKSPACE / dir_name / "combined_factors_df.parquet"
    if not parquet.exists():
        return []
    code = (
        "import pyarrow.parquet as pq, json, re, sys\n"
        "sc = pq.read_schema(sys.argv[1])\n"
        "out = []\n"
        "for n in sc.names:\n"
        "    if n in ('datetime', 'instrument'):\n"
        "        continue\n"
        "    m = re.search(r\"\\('feature',\\s*'([^']+)'\\)\", n)\n"
        "    out.append(m.group(1) if m else n)\n"
        "print(json.dumps(out))\n"
    )
    try:
        proc = subprocess.run(
            [str(RDAGENT_PYTHON), "-c", code, str(parquet)],
            capture_output=True, text=True, timeout=30,
        )
        if proc.returncode == 0:
            return json.loads(proc.stdout.strip())
    except Exception:
        pass
    return []


def _find_prev_active_factors(current_job_id: str) -> list:
    """从历史里找最近一个 done 任务的 active_factors（jobs 最新在前）

    ⚠️ 已**不再**用于 _compute_active_factors：它扫全局 jobs.json，可能跨会话
       张冠李戴；会话内的 SOTA 解析改走 `_find_session_sota_factors`（只走 resume 链）。
    仅保留给需要「全局最近一条」语义的地方。
    """
    for j in _load_jobs():
        if j.get("job_id") == current_job_id:
            continue
        if j.get("status") != "done":
            continue
        r = j.get("result") or {}
        af = r.get("active_factors")
        if af:
            return af
    return []


_FACTOR_SELECT_RE = re.compile(r"\[factor-select\] 池\s*\d+\s*→\s*选中\s*\d+：\s*(\[[^\]]*\])")
_CUR_CALMAR_RE = re.compile(
    r"Calmar \(= annualized_return / \|max_drawdown\|, with cost\) of Current Result is ([0-9.]+)"
)


_SOTA_CAL_RE = re.compile(r"of SOTA Result is ([0-9.]+)")

_CALMAR_PAIR_RE = re.compile(
    r"Calmar \(= annualized_return / \|max_drawdown\|, with cost\) of Current Result is ([0-9.]+)"
    r", of SOTA Result is ([0-9.]+)"
)


def _log_loop_facts(log_text: str) -> dict:
    """把日志里「每圈 (Calmar, 选中组合)」抽出来，并给出 SOTA 判定所需的几个量。

    日志里每圈会先后打印：
      · `[factor-select] 池 X → 选中 N：[...]`                        ← 本圈回测用的组合
      · `Calmar (= ...) of Current Result is Y, of SOTA Result is Z`   ← 本圈 Calmar 与当时的 SOTA Calmar
    返回：
      pairs        [(calmar, factors)]  每圈一个，按时间顺序
      first_sota   第一圈比较时引用的 SOTA Calmar（=会话初始 SOTA；无则 None）
      last_cur     最后一圈的 Calmar（=本圈候选的成绩）
      last_factors 最后一圈选中的组合
      best         本日志里 Calmar 最高的一圈 (calmar, factors)
    """
    fs = [(m.start(), m.group(1)) for m in _FACTOR_SELECT_RE.finditer(log_text)]
    pairs, sotas = [], []
    if fs:
        for m in _CALMAR_PAIR_RE.finditer(log_text):
            pos = m.start()
            prev = None
            for start, factors in fs:
                if start < pos:
                    prev = (start, factors)
                else:
                    break
            if prev is None:
                continue
            try:
                pairs.append((float(m.group(1)), _parse_factor_list(prev[1])))
                sotas.append(float(m.group(2)))
            except (TypeError, ValueError):
                continue
    return {
        "pairs": pairs,
        "first_sota": sotas[0] if sotas else None,
        "last_cur": pairs[-1][0] if pairs else None,
        "last_factors": pairs[-1][1] if pairs else [],
        "best": max(pairs, key=lambda p: p[0]) if pairs else None,
    }


def _extract_session_sota_factors(log_text: str) -> dict:
    """（单任务自查用）取**本日志内** Calmar 最高的一圈的组合 + Calmar。

    ⚠️ 注意：只在「一个任务跑完整会话」时才对。跨任务的续跑要靠 `_session_prev_sota`，
       因为续跑任务的日志里只有本圈。
    """
    f = _log_loop_facts(log_text)
    if not f["best"]:
        return {}
    return {"calmar": f["best"][0], "factors": f["best"][1]}


def _session_prev_sota(job_id: str) -> tuple:
    """取**同一会话内、比当前任务更早发起**的最近一条记录里存的 SOTA。

    返回 (factors, calmar, job_id)；找不到返回 ([], None, "")

    ⚠️ 2026-09-25 三次修：早前版本沿 `resume_from` 向上走——**错**。续跑任务的 resume_from
       通常直接指回**会话第一个任务**（RD-Agent 的会话检查点目录是固定的），不是前一圈：
       rd_20260925_144005 → {145845, 153914, 195928, 201036} 的 resume_from 全是 144005，
       于是 201036（第 5 圈，Replace=no）被算成 144005 当时的 3 因子，
       而真 SOTA 是 195928 的 5 因子（Calmar 0.2526）。
       改用**会话身份** `session_path`（同一会话的任务共享同一个 __session__ 目录）。
    """
    cur = _job_record(job_id) or {}
    sess = cur.get("session_path")
    started = cur.get("started") or ""
    if not sess:
        return ([], None, "")
    cands = []
    for j in _load_jobs():
        if j.get("job_id") == job_id or j.get("session_path") != sess:
            continue
        st = j.get("started") or ""
        if started and st and st >= started:  # 只看比当前任务更早发起的
            continue
        r = j.get("result") or {}
        af = list(r.get("active_factors") or [])
        if af:
            cands.append((st, j.get("job_id"), af, r.get("active_factors_calmar")))
    if not cands:
        return ([], None, "")
    _st, jid, af, cal = max(cands, key=lambda c: c[0])
    return (af, cal, jid)



def _parse_factor_list(raw: str) -> list:
    """把日志里的 Python 列表字面量（单引号）转成 str 列表"""
    try:
        val = ast.literal_eval(raw)
        return [str(x) for x in val] if isinstance(val, (list, tuple)) else []
    except (ValueError, SyntaxError):
        return [x.strip().strip("'\"") for x in raw.strip("[]").split(",") if x.strip()]


def _compute_active_factors(job_id: str, results: dict, log_text: str = "") -> list:
    """最新生效的 SOTA 因子组合。

    **语义（2026-09-25 改定）**：SOTA = **会话内 Calmar 最高的那一圈**（在会话内单调前进）。
    日志证据：`Replace Best=no` 只意味着「新因子不并入因子库」，但**只要 Calmar 更高，
    SOTA 结果依然会前进** —— rd_20260925_104411 被判 no，而下一圈 105644 日志里引用的
    SOTA Calmar 已经是 104411 的 0.214375（而不是上一圈的 0.189546）。

    判定顺序：
      · Replace Best=yes → 本轮回测组合（本轮就是新 SOTA）
      · 否则：本任务内最高 Calmar > 上一圈 SOTA 的 Calmar → 本轮组合就是新 SOTA
              否则 → 保持上一圈 SOTA（同会话 chain）
              会话首个任务（没有上一圈）→ 只有跑赢初始 SOTA 才认，否则返回 []
      ⚠️ 历次踩坑（同一个字段错了三次）：
        ① 拿「上一个 done 任务」→ 全新会话张冠李戴（本会话 5 因子 0.2868 → 上一会话 1 因子）
        ② 日志兜底取「Calmar 最大的一圈」→ 续跑时把**本圈候选**当 SOTA
           （rd_20260925_145845：应 3 因子 0.1690，误显 5 因子 0.1089）
        ③ 沿 `resume_from` 向上走 → 续跑任务的 resume_from 指回**会话第一个任务**，取到过期值
           （rd_20260925_201036：应 5 因子 0.2526，误显 144005 当时的 3 因子）
    """
    replace_best = "no"
    fb = results.get("feedback")
    if isinstance(fb, dict):
        replace_best = str(fb.get("Replace Best Result", "no")).strip().lower()
    combined = results.get("combined_factors") or []
    facts = _log_loop_facts(log_text) if log_text else {
        "best": None, "last_cur": None, "last_factors": [], "first_sota": None}
    own = facts["best"]                       # (calmar, factors) 本任务内最高
    own_cal, own_f = (own if own else (None, []))
    prev_f, prev_cal, prev_id = _session_prev_sota(job_id)

    if replace_best == "yes":
        results["active_factors_source"] = "本轮（Replace Best=yes）"
        results["active_factors_calmar"] = facts["last_cur"]
        return combined or facts["last_factors"] or own_f or prev_f

    # SOTA 单调前进：本任务跑出了更高的 Calmar → 本轮组合即当前 SOTA
    if own_f and prev_cal is not None and own_cal is not None and own_cal > prev_cal + 1e-9:
        results["active_factors_source"] = f"本任务刷新的 SOTA（Calmar≈{own_cal:.4f}）"
        results["active_factors_calmar"] = own_cal
        return own_f

    if prev_f:
        results["active_factors_source"] = f"保持本会话 SOTA（{prev_id}）"
        results["active_factors_calmar"] = prev_cal
        return prev_f

    # 会话首个任务：只有跑赢「初始 SOTA」（日志第一圈引用的 Calmar）才认
    if own_f and (facts["first_sota"] is None or own_cal > facts["first_sota"] + 1e-9):
        results["active_factors_source"] = f"本会话 SOTA（Calmar≈{own_cal:.4f}）"
        results["active_factors_calmar"] = own_cal
        return own_f

    results["active_factors_source"] = "本会话尚无有效组合"
    results["active_factors_calmar"] = None
    return []


def _collect_results(snapshot_before) -> dict:
    """比对 workspace 目录（新增 or 本轮被改写），解析因子代码 + 回测指标"""
    after = _snapshot_workspace()
    if isinstance(snapshot_before, dict):
        before = snapshot_before
    else:  # 兼容旧的集合快照（老进程传参）
        before = {name: -1 for name in (snapshot_before or set())}
    new_dirs = {n for n, m in after.items() if n not in before or m > before.get(n, 0)}

    factors = {}       # factor_name -> {"dir","factor_name","code","mtime"}
    backtest_dirs = []  # (mtime, dir_path)

    for name in new_dirs:
        d = RDAGENT_WORKSPACE / name
        try:
            mtime = d.stat().st_mtime
        except Exception:
            mtime = 0
        if (d / "factor.py").exists():
            try:
                code = (d / "factor.py").read_text(encoding="utf-8", errors="replace")
            except Exception:
                code = ""
            fn = _extract_factor_name(code) or name[:8]
            # 同名因子保留最新实现（retry 会生成多份）
            prev = factors.get(fn)
            if prev is None or mtime > prev["mtime"]:
                factors[fn] = {"factor_name": fn, "code": code, "mtime": mtime, "dir": name}
        if (d / "qlib_res.csv").exists():
            backtest_dirs.append((mtime, d))

    # 回测指标：取最新一个含 qlib_res.csv 的目录
    backtest = None
    combined_factors = []
    if backtest_dirs:
        backtest_dirs.sort(key=lambda x: x[0], reverse=True)
        _, bdir = backtest_dirs[0]
        metrics = _parse_qlib_res(bdir / "qlib_res.csv")
        ann_cost = _pick_metric(metrics, "1day.excess_return_with_cost.annualized_return")
        mdd_cost = _pick_metric(metrics, "1day.excess_return_with_cost.max_drawdown")
        ir_cost = _pick_metric(metrics, "1day.excess_return_with_cost.information_ratio")
        # Calmar = 年化收益(含成本) / |最大回撤(含成本)|
        calmar_cost = None
        if ann_cost is not None and mdd_cost not in (None, 0):
            calmar_cost = ann_cost / abs(mdd_cost)
        backtest = {
            "dir": bdir.name,
            "IC": _pick_metric(metrics, "IC"),
            "ICIR": _pick_metric(metrics, "ICIR"),
            "Rank IC": _pick_metric(metrics, "Rank IC"),
            "Rank ICIR": _pick_metric(metrics, "Rank ICIR"),
            "annualized_return_with_cost": ann_cost,
            "max_drawdown_with_cost": mdd_cost,
            "information_ratio_with_cost": ir_cost,
            "calmar_with_cost": calmar_cost,
        }
        combined_factors = _read_combined_factors(bdir.name)

    return {
        "factors": sorted(factors.values(), key=lambda x: x["factor_name"]),
        "backtest": backtest,
        "combined_factors": combined_factors,
        "gate": _build_gate(backtest),
    }


# ────────────────────────────────────────────────────────────────
#  主流程
# ────────────────────────────────────────────────────────────────
def _session_loop_count(session_dir: Path) -> int:
    """粗略统计某会话目录已完成的圈数（取该目录下最大 Loop_N 编号 + 1）"""
    mx = -1
    try:
        for p in session_dir.glob("Loop_*"):
            try:
                mx = max(mx, int(p.name.split("_", 1)[1]))
            except (IndexError, ValueError):
                continue
    except OSError:
        pass
    return mx + 1


def _session_completed_loops(session_path) -> int:
    """统计 __session__ 检查点里「已完成」的圈数：含 4_record 的圈号子目录数。

    RD-Agent 的 __session__ 下按圈号建目录（0/1/2/...），每圈 5 步，最后一步
    4_record 落盘才算该圈完成。续跑的 --loop-n 是「总圈数」语义：目标总圈数
    ≤ 已完成圈数时 CLI 会跳过全部并立即退出（一圈不挖）⇒ 这里给出真实已完成
    圈数，供 start_mining 抬高目标圈数（2026-09-20 复盘）。
    """
    p = Path(session_path)
    if not p.is_dir():
        return 0
    n = 0
    try:
        for d in p.iterdir():
            try:
                if d.is_dir() and d.name.isdigit() and (d / "4_record").exists():
                    n += 1
            except OSError:
                continue
    except OSError:
        return 0
    return n


def _tail_text(path, max_lines: int = 15, max_chars: int = 800) -> str:
    """读文件末尾若干非空行（去 ANSI、截断），失败时留证据用"""
    try:
        if not path:
            return ""
        p = Path(path)
        if not p.exists():
            return ""
        raw = p.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""
    lines = [ln for ln in _strip_ansi(raw).splitlines() if ln.strip()]
    return "\n".join(lines[-max_lines:]).strip()[-max_chars:]


def _find_resume_target() -> dict:
    """找最近一个会话检查点（__session__）仍存在的任务，用于续跑。

    C 方案（2026-09-12）：不再只信 jobs.json —— CLI 直跑 / 网页外启动的任务不会
    登记 jobs.json，导致网页续跑接不上最新链路。改为直接扫 RDAGENT_SESSION_DIR
    下所有 */__session__ 检查点，按 mtime 取最新那个；jobs.json 里若有对应记录
    （按目录名或 session_path 匹配）则沿用其 total_loops，否则按目录 Loop_* 估算。
    """
    candidates = []
    if RDAGENT_SESSION_DIR.exists():
        for d in RDAGENT_SESSION_DIR.iterdir():
            sp = d / "__session__"
            try:
                if sp.is_dir():
                    candidates.append((sp.stat().st_mtime, d))
            except OSError:
                continue
    if not candidates:
        return None
    mtime, sess_dir = max(candidates, key=lambda x: x[0])
    session_path = str(sess_dir / "__session__")

    loops = None
    for j in _load_jobs():
        if j.get("job_id") == sess_dir.name or j.get("session_path") == session_path:
            loops = int(j.get("total_loops") or j.get("loop_n") or 0)
            break
    session_loops = _session_completed_loops(session_path)
    if not loops:
        loops = session_loops or _session_loop_count(sess_dir)

    return {
        "job_id": sess_dir.name,
        "session_path": session_path,
        "total_loops": loops,
        "session_loops": session_loops,
        "mtime": mtime,
    }


def _llm_env(name: str, default):
    """读取本轮开始挖掘时实际生效的 LLM/规则参数（由 rdagent_demo/.env 注入子进程）。

    2026-09-24（P0-6）：把影响「随机性」的参数（温度 / 种子 / 最短窗口）随任务落盘，
    以后复盘时能直接看出这轮是在什么随机性设置下跑出来的。

    注意：API 进程自己并没有这些变量（它们只在 _build_command 里 source 进子 shell），
    所以这里按 os.environ → rdagent_demo/.env 文件 的优先序读取。
    """
    v = os.environ.get(name)
    if v not in (None, ""):
        return v
    env_path = RDAGENT_DIR / ".env"
    try:
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
                s = line.strip()
                if not s or s.startswith("#") or "=" not in s:
                    continue
                k, _, val = s.partition("=")
                if k.strip() == name:
                    val = val.strip().strip('"').strip("'")
                    return val if val != "" else default
    except Exception as e:
        print(f"[rdagent] 读取 .env 失败（{name}）：{e}")
    return default


def _session_checkpoint_exists(session_path: str) -> bool:
    """会话检查点目录是否还在（清理脚本会把历史 job 目录丢进废纸篓）。"""
    try:
        p = Path(session_path)
        return p.is_dir() and any(p.iterdir())
    except Exception:
        return False


def _record_calmar(rec: dict) -> float | None:
    """从 jobs.json 记录里取该轮回测的含成本 Calmar（取不到返回 None）。"""
    bt = ((rec.get("result") or {}).get("backtest")) or {}
    try:
        c = bt.get("calmar_with_cost")
        if c is not None:
            return float(c)
    except (TypeError, ValueError):
        pass
    ann, mdd = bt.get("annualized_return_with_cost"), bt.get("max_drawdown_with_cost")
    try:
        if ann is not None and mdd:
            return float(ann) / abs(float(mdd))
    except (TypeError, ValueError):
        pass
    return None


def find_best_sota_session() -> dict | None:
    """P0-4（2026-09-24）：找「续挖到当前 SOTA 最高会话」的目标。

    口径①（既定口径）：按各会话**当前生效 SOTA** 的 Calmar 排序，而不是历史最高单轮。
    「当前生效 SOTA」= 该会话中**最后一次 Replace Best=yes** 的那一轮（它决定了当前的
    active_factors）。若某会话后来因停滞重启/异常把标记清空，其当前 SOTA 会退化到更早的
    一轮 —— 这是预期语义（跟的是「现在生效的那个 SOTA」，不是历史峰值）。

    只会返回**会话检查点仍存在**的目标（否则续跑根本跑不起来）；若全局最优（口径①）那次
    的检查点已被清理，则退回次优的可续跑会话，并在 `best_overall_*` 字段里说明被跳过的对象。
    """
    jobs = _load_jobs()
    sessions: dict[str, list] = {}
    for rec in jobs:
        sp = rec.get("session_path")
        if sp:
            sessions.setdefault(sp, []).append(rec)

    candidates: list[dict] = []
    for sp, recs in sessions.items():
        recs = sorted(recs, key=lambda r: str(r.get("started") or ""))
        cur = None
        for rec in recs:
            fb = ((rec.get("result") or {}).get("feedback")) or {}
            if str(fb.get("Replace Best Result", "")).strip().lower() == "yes":
                cur = rec
        if cur is None:
            continue
        calmar = _record_calmar(cur)
        if calmar is None:
            continue
        # ⚠️ 2026-09-25 修复：基准圈数必须取「会话**当前实际**已完成圈数」。
        #    `cur` 是「最后一次 Replace Best=yes」那一轮，它可能落在链条**中段**
        #    （其 session_loops/total_loops 是当时的值）。只用记录值 → 算出的目标总圈数
        #    可能 ≤ 会话已跑圈数 → CLI 载入后判定"已跑满"、一圈不挖直接秒退。
        #    事故：job rd_20260925_102603 目标 15 圈 vs 会话实际 33 圈，13 秒"完成"且零产物。
        actual_loops = _session_completed_loops(sp)
        rec_loops = int(cur.get("session_loops") or 0)
        rec_total = int(cur.get("total_loops") or 0)
        job_dir = RDAGENT_SESSION_DIR / str(cur.get("job_id"))
        candidates.append(
            {
                "job_id": cur.get("job_id"),
                "session_path": sp,
                "session_root": str(Path(sp).parent),
                "total_loops": max(rec_total, actual_loops) or None,
                "session_loops": max(rec_loops, actual_loops),
                "record_session_loops": rec_loops,
                "job_dir_exists": job_dir.is_dir(),
                "calmar": round(float(calmar), 4),
                "decision_at": cur.get("started"),
                "factors": list(((cur.get("result") or {}).get("active_factors")) or []),
                "resumable": _session_checkpoint_exists(sp),
            }
        )

    if not candidates:
        return None

    best_overall = max(candidates, key=lambda c: c["calmar"])
    resumable = [c for c in candidates if c["resumable"]]
    if not resumable:
        return None

    target = max(resumable, key=lambda c: c["calmar"])
    if target["session_path"] != best_overall["session_path"]:
        # 全局最优的检查点已被清理：退回可续跑的最优，并说明差异
        target = dict(target)
        target["best_overall_job_id"] = best_overall["job_id"]
        target["best_overall_calmar"] = best_overall["calmar"]
        target["best_overall_resumable"] = False
    # 2026-09-25：SOTA 决策那一轮的 job 目录可能已被清理（会话数据仍在 session_path 下），
    # 这种「标签指向已删除 job」的情况要明确告知，避免前端把它当成本轮产物去翻目录。
    if not target.get("job_dir_exists", True):
        target = dict(target)
        target["note"] = (
            f"SOTA 决策轮 {target['job_id']} 的 job 目录已被清理；"
            f"会话数据仍在 {target.get('session_root')}，续跑不受影响"
        )
    return target


def start_mining(loop_n: int = 1, resume: bool = False, resume_best: bool = False) -> dict:
    """启动一次自动因子挖掘（或续跑上次会话），秒回 job_id，后台异步跑"""
    if RDAGENT_STATUS["running"]:
        raise RuntimeError("已有挖掘任务在运行中")

    job_id = f"rd_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    loop_n = max(1, min(loop_n, 10))

    # 续跑：定位上次会话，计算实际要跑的 --loop-n
    resume_from = None
    resume_path = None
    cli_loop_n = loop_n
    session_loops = 0
    if resume_best:
        # P0-4（2026-09-24）：一键「续挖到当前 SOTA 最高会话」
        parent = find_best_sota_session()
        if parent is None:
            raise RuntimeError("找不到带会话检查点的历史 SOTA 会话，无法「续挖到最佳会话」")
        resume = True
        print(
            f"[rdagent] 续挖到最佳会话: {parent['job_id']} Calmar={parent['calmar']} "
            f"因子={parent['factors']}"
        )
    if resume:
        if not resume_best:
            parent = _find_resume_target()
            if parent is None:
                raise RuntimeError("没有可续跑的历史任务（需先成功跑过至少一次）")
        resume_from = parent["job_id"]
        resume_path = parent.get("session_path")
        # loop_n 是「总圈数」语义（load 后 loop_idx 归 0，已完成圈会快速跳过但计入预算）：
        # 续跑 N 圈 = 已累计圈数 + N
        # ⚠️ 基准取「jobs.json 记录圈数」与「会话检查点实际已完成圈数」的较大值：
        #    只信 jobs.json 时，一旦会话被网页之外的 CLI 跑在前面（jobs.json 不知道），
        #    目标总圈数 ≤ 已完成圈数 → CLI 跳过全部、秒退、一圈不挖（2026-09-20 复盘）
        parent_total = int(parent.get("total_loops") or parent.get("loop_n") or 0)
        session_loops = int(parent.get("session_loops") or 0)
        base_loops = max(parent_total, session_loops)
        print(f"[rdagent] 续跑基准: jobs.json={parent_total} 圈, 会话已完成={session_loops} 圈 "
              f"→ 取 {base_loops} 圈, 目标总圈数={base_loops + loop_n}")
        cli_loop_n = base_loops + loop_n

    total_loops = cli_loop_n
    session_path = str(_session_path(job_id)) if resume_path is None else resume_path

    RDAGENT_STATUS.update({
        "running": True,
        "job_id": job_id,
        "loop": 0,
        "step": "",
        "step_label": "",
        "progress_pct": 0,
        "message": "续跑启动中..." if resume else "启动中...",
        "started": datetime.now().isoformat(),
        "finished": None,
        "error": None,
    })

    # 记录历史（running 状态）
    jobs = _load_jobs()
    jobs.insert(0, {"job_id": job_id, "loop_n": loop_n, "total_loops": total_loops,
                    "resume_from": resume_from, "session_path": session_path,
                    "session_loops": session_loops,
                    "status": "running",
                    "started": RDAGENT_STATUS["started"], "finished": None,
                    # P0-6（2026-09-24）：落盘本轮随机性设置，便于事后核对抽签来源
                    "chat_temperature": _llm_env("CHAT_TEMPERATURE", "0.5"),
                    "chat_seed": _llm_env("CHAT_SEED", None),
                    "factor_min_window": _llm_env("RDAGENT_MIN_FACTOR_WINDOW", "5")})
    _save_jobs(jobs)

    snapshot_before = _snapshot_workspace()

    t = threading.Thread(target=_run, args=(job_id, cli_loop_n, snapshot_before, resume_path), daemon=True)
    t.start()
    return {"job_id": job_id, "resume": resume, "resume_from": resume_from,
            "total_loops": total_loops}


def _run(job_id: str, loop_n: int, snapshot_before: dict, resume_path: str = None):
    try:
        os.nice(10)  # 降低优先级，避免抢 QuantLab 资源
    except Exception:
        pass

    log_path = _job_log_path(job_id)
    fallback_log_path = Path("/tmp") / f"rdagent_{job_id}.err"

    # ── 预检：RD-Agent 跑在独立 conda 环境（默认 <repo>/data/rdagent_demo）──
    # 缺环境时直接报错返回，避免界面一直卡在「挖掘中」而日志里只有 ModuleNotFoundError。
    env_file = RDAGENT_DIR / ".env"
    missing = [str(p) for p in (RDAGENT_PYTHON, RDAGENT_CLI, env_file) if not p.exists()]
    if missing:
        RDAGENT_STATUS.update({
            "running": False, "job_id": job_id, "loop": 0, "total_loops": total_loops,
            "step": "error", "message": "未检测到 RD-Agent 运行环境",
            "error": ("缺少：" + "、".join(missing) + "\n"
                      "RD-Agent 是可选组件，工作目录通过 RDAGENT_HOME 指定"
                      f"（当前为 {RDAGENT_DIR}），\n"
                      "它需要：① 一个装了 rdagent 的 conda 环境（RDAGENT_CONDA_ENV / CONDA_ROOT）、\n"
                      "② 工作目录里的 .env（LLM 凭证等，参照 README）。\n"
                      "未安装时请忽略本页（其余功能不受影响）。"),
            "finished": datetime.now().isoformat(),
        })
        return

    cmd = _build_command(loop_n, job_id, resume_path)
    RDAGENT_STATUS["message"] = "挖掘中..."

    try:
        log_fh = open(log_path, "w", encoding="utf-8")
    except Exception as e:
        # 兜底：日志打不开也不能把 CLI 输出丢进 DEVNULL（2026-09-20 那次 2.2s「退出码 1」
        # 没有任何日志可查，只能靠这个 /tmp 兜底文件留证据）
        print(f"[rdagent][warn] 日志 {log_path} 打不开: {e}")
        try:
            log_fh = open(fallback_log_path, "w", encoding="utf-8")
        except Exception:
            log_fh = None

    proc = None
    try:
        proc = subprocess.Popen(
            cmd,
            shell=True,
            cwd=str(RDAGENT_DIR),
            stdout=log_fh if log_fh else subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
        )

        # 监控循环：读日志更新进度，直到进程退出
        while True:
            ret = proc.poll()
            if ret is not None:
                break
            _update_progress_from_log(job_id, loop_n)
            time.sleep(2)

        _update_progress_from_log(job_id, loop_n)

        if ret == 0:
            RDAGENT_STATUS["progress_pct"] = 100
            RDAGENT_STATUS["message"] = "挖掘完成，解析结果中..."
            # 读完整日志，提取 SOTA 对比 + 复盘结论
            try:
                raw = log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else ""
            except Exception:
                raw = ""
            clean = _strip_ansi(raw)
            results = _collect_results(snapshot_before)
            results["sota_comparison"] = _extract_sota_comparison(clean)
            results["feedback"] = _extract_feedback(clean)
            if results["feedback"] or results["factors"]:
                RDAGENT_STATUS["message"] = "翻译结果中..."
                results["feedback"] = _translate_feedback(results["feedback"])
                results["factors"] = _translate_factor_names(results["factors"])
            # 计算最新生效因子组合（SOTA）
            results["active_factors"] = _compute_active_factors(job_id, results, clean)

            # 2026-09-25 修复：退出码 0 不等于"跑出东西了"。零产物（0 新因子 + 无回测）
            # 说明 CLI 根本没干活（典型：续跑基准算错/会话已跑满 → 载入后秒退），
            # 必须判异常，否则静默"完成"（事故：rd_20260925_102603 13 秒假完成）。
            if not results.get("factors") and results.get("backtest") is None:
                elapsed = _job_elapsed_seconds(job_id)
                rec = _job_record(job_id) or {}
                hint = ""
                if rec.get("resume_from"):
                    hint = (
                        f"；本轮为续跑（resume_from={rec.get('resume_from')}，"
                        f"目标总圈数={rec.get('total_loops')}）→ 优先核对是否"
                        f"「目标圈数 ≤ 会话已完成圈数」导致秒退"
                    )
                detail = (
                    f"rdagent 退出码 0，但本轮**零产物**：0 个新因子、无回测结果"
                    f"（耗时 {elapsed:.0f}s）——疑似载入后秒退/一圈未挖{hint}"
                )
                logger_msg = f"[rdagent] {job_id} {detail}"
                print(logger_msg)
                RDAGENT_STATUS["message"] = "异常：零产物（疑似秒退）"
                RDAGENT_STATUS["error"] = detail
                _finalize_job(job_id, "failed", results, detail)
                return

            RDAGENT_STATUS["message"] = "完成"
            RDAGENT_STATUS["error"] = None
            _finalize_job(job_id, "done", results)
        else:
            src = log_path if log_path.exists() else fallback_log_path
            tail = _tail_text(src, 15, 800)
            detail = f"rdagent 退出码 {ret}"
            if tail:
                detail += f"\n[末尾输出]\n{tail}"
            else:
                detail += f"（无日志输出；兜底文件 {fallback_log_path}）"
            RDAGENT_STATUS["message"] = f"失败（退出码 {ret}）"
            RDAGENT_STATUS["error"] = detail
            _finalize_job(job_id, "failed", None, detail)
    except Exception as e:
        RDAGENT_STATUS["message"] = f"失败: {e}"
        RDAGENT_STATUS["error"] = str(e)
        _finalize_job(job_id, "failed", None, str(e))
    finally:
        if log_fh:
            try:
                log_fh.close()
            except Exception:
                pass
        RDAGENT_STATUS["running"] = False
        RDAGENT_STATUS["finished"] = datetime.now().isoformat()


def _finalize_job(job_id: str, status: str, results: dict, error: str = None):
    jobs = _load_jobs()
    for j in jobs:
        if j.get("job_id") == job_id:
            j["status"] = status
            j["finished"] = datetime.now().isoformat()
            if results:
                j["result"] = results
            if error:
                j["error"] = error
            break
    _save_jobs(jobs)


# ────────────────────────────────────────────────────────────────
#  查询接口
# ────────────────────────────────────────────────────────────────
def get_status() -> dict:
    return dict(RDAGENT_STATUS)


def get_result(job_id: str = None) -> dict:
    jobs = _load_jobs()
    if job_id:
        for j in jobs:
            if j.get("job_id") == job_id:
                return j
        return {"job_id": job_id, "status": "not_found"}
    # 默认返回最近一次任务
    if jobs:
        return jobs[0]
    return {"status": "none", "note": "尚无挖掘任务"}


def get_history() -> list:
    # 只返回摘要（不含大段代码，避免响应过大）
    jobs = _load_jobs()
    summary = []
    for j in jobs:
        item = {k: j.get(k) for k in ("job_id", "loop_n", "total_loops", "resume_from", "session_loops", "status", "started", "finished", "error")}
        result = j.get("result") or {}
        item["factor_names"] = [f.get("factor_name") for f in result.get("factors", [])]
        item["factor_names_cn"] = [f.get("factor_name_cn") or f.get("factor_name") for f in result.get("factors", [])]
        bt = result.get("backtest") or {}
        item["IC"] = bt.get("IC")
        item["ICIR"] = bt.get("ICIR")
        gate = result.get("gate")
        item["gate_pass"] = gate.get("pass") if gate else None
        summary.append(item)
    return summary


# ────────────────────────────────────────────────────────────────
#  历史缓存清理（复用既有脚本 scripts/rdagent_cleanup.py）
#  原则：只清「可再生中间产物」，保留「续跑依赖 + 当前 SOTA 资产」；
#  全部走 trash（废纸篓，可恢复）；挖掘任务运行中直接拒绝（避免破坏在跑的回测）。
# ────────────────────────────────────────────────────────────────
CLEANUP_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "rdagent_cleanup.py"
CLEANUP_PICKLE_CACHE = RDAGENT_DIR / "pickle_cache"

# 僵尸 running 判定：running 但探测不到进程、且距启动不足此时长 → 视为刚启动，保守放过
STALE_RUNNING_GRACE_S = 180


def _running_process_alive(job_id: str) -> bool:
    """某 running 任务的挖掘进程是否真的还在跑。

    启动命令写死了 LOG_TRACE_PATH=<RDAGENT_DIR>/log/jobs/<job_id>，进程 cmdline 必含
    该串；探测不到说明进程已死（服务重启/被杀）而 jobs.json 没写回终态。
    探测失败时保守返回 True（宁可不清，也不误伤正在跑的任务）。
    """
    if not job_id:
        return True
    try:
        rc = subprocess.run(["pgrep", "-f", f"log/jobs/{job_id}"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            timeout=10).returncode
        return rc == 0
    except Exception:
        return True


def _job_age_seconds(rec: dict) -> float:
    """该轮距启动已过秒数（取不到 started 时返回极大值，视作早已过期）。"""
    started = rec.get("started")
    if not started:
        return 1e9
    try:
        return max(0.0, (datetime.now().astimezone()
                         - datetime.fromisoformat(str(started)).astimezone()).total_seconds())
    except Exception:
        return 1e9


def reconcile_stale_running() -> int:
    """把「僵尸 running」任务（进程已不存在）落回 failed，返回修复条数。

    ⚠️ 背景（2026-10-10 事故）：挖掘跑到一半后端服务重启，`_run()` 的 finally 没执行，
    jobs.json 里该任务永远停在 running，导致历史缓存清理被误判为「有任务在跑」而整体
    跳过（rd_20261010_093636）。服务启动时自愈：进程不在 + 已过启动宽限期 → 判 failed。
    """
    jobs = _load_jobs()
    fixed = 0
    for j in jobs:
        if j.get("status") != "running":
            continue
        jid = j.get("job_id")
        if _running_process_alive(jid) or _job_age_seconds(j) < STALE_RUNNING_GRACE_S:
            continue
        log_path = _job_log_path(jid)
        if log_path.exists():
            fin = datetime.fromtimestamp(log_path.stat().st_mtime).astimezone().isoformat()
        else:
            fin = datetime.now().astimezone().isoformat()
        j["status"] = "failed"
        j["finished"] = fin
        j["error"] = ("[自动标记·僵尸running修复] 进程已不存在、记录滞留 running"
                      "（多为服务重启中断 _run() 未写回终态）；按日志最后写入时间判定为 failed。")
        fixed += 1
        print(f"[rdagent][reconcile] 僵尸 running 归零: {jid} -> failed")
    if fixed:
        _save_jobs(jobs)
    return fixed


def _dir_size_mb(path: Path) -> int:
    """目录体积（MB）。用原生 du，失败返回 0（不阻塞清理）。"""
    if not path.exists():
        return 0
    try:
        out = subprocess.run(["du", "-sk", str(path)], capture_output=True,
                             text=True, timeout=300).stdout
        return int(out.split()[0]) // 1024
    except Exception:
        return 0


def _paths_size_mb(paths: list) -> int:
    """若干路径体积合计（MB）；dry-run 用它估算「预计可释放」。"""
    total = 0
    for i in range(0, len(paths), 50):
        chunk = paths[i:i + 50]
        try:
            out = subprocess.run(["du", "-sk"] + chunk, capture_output=True,
                                 text=True, timeout=300).stdout
        except Exception:
            return total // 1024
        for ln in out.splitlines():
            head = ln.split("\t")[0].strip()
            if head.isdigit():
                total += int(head)
    return total // 1024


def get_disk_info() -> dict:
    """RD-Agent 产物体积 + 磁盘余量（MB）。"""
    usage = shutil.disk_usage(str(_HOME))
    return {
        "rdagent_mb": _dir_size_mb(RDAGENT_DIR),
        "workspace_mb": _dir_size_mb(RDAGENT_WORKSPACE),
        "pickle_cache_mb": _dir_size_mb(CLEANUP_PICKLE_CACHE),
        "log_jobs_mb": _dir_size_mb(RDAGENT_SESSION_DIR),
        "free_mb": usage.free // 1024 // 1024,
        "total_mb": usage.total // 1024 // 1024,
        "script": rel_path(CLEANUP_SCRIPT),
        "script_exists": CLEANUP_SCRIPT.exists(),
    }


def run_cleanup(dry_run: bool = False) -> dict:
    """执行历史缓存清理。dry_run=True 只预览不删除。"""
    if RDAGENT_STATUS.get("running"):
        raise RuntimeError("有挖掘任务在运行中，暂不清理（避免破坏正在跑的回测），等它结束再来")
    if not CLEANUP_SCRIPT.exists():
        raise RuntimeError(f"清理脚本不存在：{CLEANUP_SCRIPT}")

    before_mb = _dir_size_mb(RDAGENT_DIR)
    cmd = [sys.executable, str(CLEANUP_SCRIPT)] + (["--dry-run"] if dry_run else [])
    env = dict(os.environ)
    env["PATH"] = "/usr/bin:/bin:/usr/sbin:/sbin:" + env.get("PATH", "")
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=1800,
                              cwd=str(CLEANUP_SCRIPT.parent.parent), env=env)
    except subprocess.TimeoutExpired:
        raise RuntimeError("清理超时（>30 分钟）已中止")
    after_mb = _dir_size_mb(RDAGENT_DIR)

    raw = [ln.rstrip() for ln in (proc.stdout or "").splitlines() if ln.strip()]
    targets = [ln.split("[dry-run] trash", 1)[1].strip()
               for ln in raw if "[dry-run] trash" in ln]
    lines = [ln for ln in raw if "[dry-run] trash" not in ln]
    if targets:
        lines.append(f"（另有 {len(targets)} 条逐项明细已省略）")
    for ln in (proc.stderr or "").strip().splitlines()[-2:]:
        lines.append("[stderr] " + ln[:200])

    estimate_mb = _paths_size_mb(targets) if (dry_run and targets) else 0
    info = {
        "ok": proc.returncode == 0,
        "dry_run": dry_run,
        "before_mb": before_mb,
        "after_mb": after_mb,
        "freed_mb": max(before_mb - after_mb, 0) if not dry_run else 0,
        "estimate_mb": estimate_mb,
        "returncode": proc.returncode,
        "message": ("预览完成（未删除任何文件）" if dry_run else
                    ("清理完成" if proc.returncode == 0 else "清理异常退出，见下方输出")),
        "lines": lines,
    }
    print(f"[rdagent][cleanup] dry_run={dry_run} {before_mb}MB -> {after_mb}MB "
          f"est={estimate_mb}MB rc={proc.returncode}")
    return info
