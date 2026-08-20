# Collaboration Preferences

- 当澄清问题能显著提升对用户意图或结果质量的理解时，主动向用户提问。
- 一次只问一个问题。等待用户回答后再问下一个。
- 当意图可以从工作区、现有上下文或保守实现选择中安全确定时，不提问。

# Roles

## planner/reviewer（本机 Sol）

- 理解需求，检查两个仓库、数据库契约、现有 PR 和生产运行约束；一次只询问
  一个关键问题。
- 用户确认最终方案后创建中文 GitHub Issue。Issue 是唯一施工合同，必须包含
  `Plan-Version`、范围、数据口径、接口、测试、部署和回滚。
- 审核固定 head SHA、开放 PR、本机未提交改动、数据来源发布时间、无未来数据、
  写库范围和敏感文件。
- 使用普通 Merge 合并；合并不等于部署。

## implementer（Windows 开发机 DeepSeek）

- 从最新 `origin/main` 创建 `codex/<issue-number>-<slug>` 分支；做最小准备
  提交后立即创建中文 Draft PR。
- 只执行 Issue 已确定内容；遇到歧义时在 Issue 一次问一个问题，并暂停相关实现。
- 提交 PR 时注明最终 head SHA、Windows 已验证项、待 Sol 集成验证项、截图或
  无法在 Windows 执行的项目及原因。

## implementer 禁止事项

- 直接提交 main。
- 越过 Issue 自行施工或扩大范围。
- 启动项目服务（API、前端、MySQL、Redis、Celery worker/Beat、stock-temp、
  浏览器集成环境等）。
- 访问生产资源（正式数据库/Redis、正式采集服务、正式账号/登录状态）。
- 执行真实采集、历史回补、数据库迁移、任务中心运行或生产重启。

# 验证边界

- Windows 仅可执行不依赖运行中服务、真实数据库和外部账号的项目内检查：
  Mock/fixture 单元测试、类型检查、lint、compile、`git diff --check`、
  不访问后端的前端构建。
- 依赖本机数据库、Redis、采集服务、登录状态、浏览器或真实数据的集成验证，
  由 Sol 在本机独立 worktree/临时检出中完成。

# 快速通道

- 只有用户明确说“本机直接改 main”时才能使用快速通道；开始前检查开放 PR、
  本机改动和重叠路径。

# 完整流程

- 完整流程见 [docs/REMOTE_CODING_AND_PR_WORKFLOW.md](docs/REMOTE_CODING_AND_PR_WORKFLOW.md)。
