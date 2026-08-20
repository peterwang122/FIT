# 异机编码与 PR 开发规范（Sol + DeepSeek）

**Plan-Version:** v2
**任务标识:** `sol-deepseek-pr-workflow`
**执行角色:** Windows 开发机 DeepSeek V4 Flash（implementer）
**审核角色:** 本机 Sol（planner/reviewer）
**配套采集仓库 Issue:** https://github.com/peterwang122/akshareProkect/issues/12

本文档是 FIT 与 akshareProkect 两个仓库共用的完整流程来源；采集仓库在
akshareProkect 仓库内维护配套的采集侧补充说明（见
https://github.com/peterwang122/akshareProkect/issues/12 关联 PR）。

## 1. 已确认的新边界

Windows 电脑只承担代码编辑、Git 分支、Mock/纯单元测试、静态检查和提交中文
Draft PR，不启动任何开发版本或完整测试站点。

Windows 电脑不得：

- 启动 FIT API、前端站点、MySQL、Redis、Celery worker/Beat、stock-temp、
  akshareProkect 服务或浏览器集成环境。
- 连接正式 MySQL/Redis、正式采集服务、正式 Cookie/登录状态、短信、邮件、
  通知或第三方账号。
- 手动执行真实采集、历史回补、数据库迁移、任务中心运行或生产重启。
- 保存生产密钥、Cookie、数据库凭据、短信/邮件凭据或第三方登录配置。

因此不再建设 `APP_ENV=lan-test`、测试数据库、SSH 数据库隧道、采集白名单、
测试运行时或局域网测试站点。

## 2. 角色与责任

### 本机 Sol（planner/reviewer）

- 理解需求，检查两个仓库、数据库契约、现有 PR 和生产运行约束；一次只询问
  一个关键问题。
- 用户确认最终方案后创建中文 GitHub Issue。Issue 是唯一施工合同，必须包含
  `Plan-Version`、范围、数据口径、接口、测试、部署和回滚。
- 审核固定 head SHA、开放 PR、本机未提交改动、数据来源发布时间、无未来数据、
  写库范围和敏感文件。
- 使用普通 Merge 合并；合并不等于部署。

### Windows 开发机 DeepSeek（implementer）

- 从最新 `origin/main` 创建 `codex/<issue-number>-<slug>` 分支，做最小准备
  提交后立即创建中文 Draft PR。
- 只能执行 Issue 已确定内容；遇到歧义时在 Issue 一次问一个问题，并暂停相关实现。
- 不得直接提交 main、越过 Issue、启动项目服务、访问生产资源或执行真实采集。

## 3. 标准流程

1. Sol 在本机理解需求、检查两个仓库、数据库契约、现有 PR 和生产运行约束，
   一次只询问一个关键问题。
2. 用户确认最终方案后，Sol 创建中文 GitHub Issue。Issue 是唯一施工合同，
   必须包含 `Plan-Version`、范围、数据口径、接口、测试、部署和回滚。
3. DeepSeek 从最新 `origin/main` 创建 `codex/<issue-number>-<slug>` 分支，
   做最小准备提交后立即创建中文 Draft PR。
4. DeepSeek 只能执行 Issue 已确定内容；遇到歧义时在 Issue 一次问一个问题，
   并暂停相关实现。
5. Windows 可执行的验证仅限不依赖运行中服务、真实数据库和外部账号的项目内
   检查，例如 Mock/fixture 单元测试、类型检查、lint、compile、`git diff --check`
   和不访问后端的前端构建。
6. DeepSeek 合并最新 `origin/main`、解决功能分支冲突、重跑可安全执行的检查，
   将 PR 转 Ready，并注明最终 head SHA、测试结果、截图或无法在 Windows
   执行的项目及原因。
7. Sol 对固定 head SHA 审核代码、数据口径、生产写入、敏感信息、无未来数据、
   测试与界面。
8. 依赖本机数据库、Redis、采集服务、登录状态、浏览器或真实数据的集成验证，
   由 Sol 在本机独立 worktree/临时检出中完成；不得要求 Windows 启动测试站点。
9. DeepSeek 在原分支修复审核意见；Sol 重新审核固定的新 head SHA。
10. 全部通过后由 Sol 使用普通 Merge 合并。合并不等于部署，服务重启、采集、
    回补和正式任务执行需单独确认。

## 4. Issue 是唯一施工合同

- Issue 必须包含 `Plan-Version`（每次 Sol 决策变更 +1）。
- 使用仓库内 Issue 模板“Sol 实施方案”，强制填写目标、不做事项、验收标准、
  数据来源与发布时间、日期映射、API/数据库/采集器/前端/缓存影响、测试、
  部署、回滚和跨仓库链接。
- 只有 Sol 可以追加决策变更；DeepSeek 不得自行决定业务和数据口径。

## 5. Draft PR 要求

- 完成范围确认和最小提交后立即创建中文 Draft PR，base 为 `main`。
- PR 说明必须包含：关联 Issue 与 `Plan-Version`、最终 head SHA、实际改动、
  数据读写、collector_key、网络/通知影响、Windows 已执行的测试及结果、
  必须由 Sol 执行的集成验证清单、未执行验证及原因、截图、部署顺序和回滚。
- 明确区分“Windows 已验证”与“待本机 Sol 集成验证”。
- 不使用 `git push --force` 或 `--force-with-lease`；不 rebase 已发布分支；
  冲突只能在功能分支解决。

## 6. 验证边界

### Windows 可执行（DeepSeek）

- Mock/fixture 单元测试
- 类型检查、lint、compile
- `git diff --check`
- 不访问后端的前端构建

### 待本机 Sol 集成验证

- 依赖本机数据库、Redis、采集服务、登录状态、浏览器或真实数据的场景
- 真实最小请求、目标表写入、任务中心、历史回补、服务健康和实际发布日期核验

## 7. 跨仓库与快速通道

- 跨仓库需求创建两个相互引用的 Issue 和 Draft PR，使用同一任务标识。
- 默认先合并向后兼容的 akshareProkect 采集端，再合并 FIT 调用端。
- Sol 只审核，DeepSeek 负责修改 PR 分支；两个代理不得同时修改同一功能分支。
- 用户明确说“本机直接改 main”时才能使用快速通道；Sol 开始前检查开放 PR、
  本机改动和重叠路径。
- 不强推、不改写历史；冲突只在功能分支解决。

## 8. 合并与部署边界

- 使用普通 Merge（不使用 Squash 或 Rebase merge）。
- 合并前由 Sol 检查 head SHA、开放 PR、本机未提交文件和敏感文件。
- PR 合并不等于部署。没有用户明确要求时，不重启服务、不执行正式采集、
  不应用生产数据回补。

## 9. 敏感信息红线

任何情况下不允许：

- 提交 `.env*`、密钥、Cookie、浏览器 profile、数据库导出或第三方登录状态。
- 在 Windows 保存正式数据库管理员密码或生产凭据。
- 用测试结果伪装正式数据，或把测试写入正式库。

## 10. 试运行

工作流合并后，选择一个低风险、单仓库的小功能试运行。连续记录前三个 PR 的
一次通过率、审核问题数、返工轮数、测试耗时、冲突次数和模型费用；两轮审核
仍重复同类问题时暂停施工，由 Sol 修订 Issue 或 AGENTS 规则。

## 11. 相关文件

- [AGENTS.md](../AGENTS.md)：角色规则与验证边界
- [Issue 模板](../.github/ISSUE_TEMPLATE/sol-implementation-plan.md)
- [PR 模板](../.github/PULL_REQUEST_TEMPLATE.md)
