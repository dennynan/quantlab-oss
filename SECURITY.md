# Security Policy

## 支持的版本

| 版本 | 支持 |
|------|------|
| 0.1.x | ✅ |

## 报告漏洞

请**不要**通过公开 Issue 报告安全问题。请通过以下方式私下联系：

- 请使用 GitHub 的 [Private Vulnerability Reporting](https://docs.github.com/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/privately-reporting-a-security-vulnerability)（仓库 **Security → Report a vulnerability**）

我们会在 72 小时内回复，并在修复后致谢。

## 部署注意

- 本项目**开源版不含用户认证**，请勿直接暴露到公网生产环境；
  如需上线请自行在前置网关/反代层加认证与限流。
- 若需**公网演示**，可启用演示模式 `OSS_DEMO=1`：会禁用 RD-Agent 的写操作（仅保留历史查看，
  避免被消耗付费 LLM 额度）并对训练 / 回测 / 筛选等重接口按来源 IP 限流。这仅是缓解措施，
  不能替代前置网关的认证与限流。
- `.env` 中的 LLM Key 等凭据请勿提交入库。
- 数据接口均按「只读本地数据」设计，请自行评估数据来源合规性。
