# 🚀 MongoDB 灵活问卷调研系统 v2

本项目是一个基于 **Flask + MongoDB + Alpine.js** 构建的全栈问卷调查系统。v2 版本在原有基础上新增了**题目版本管理**、**题库系统**、**题目共享**等高级功能，支持复杂的题目类型、动态跳转逻辑、实时数据统计以及高并发下的自动化压力测试。

---

## ✨ 核心特性

### 1. 强力后端 (Python/Flask)
* **无缝 MongoDB 集成**：通过自定义 `MongoJSONProvider` 彻底消除 `ObjectId` 和 `Datetime` 转换的样板代码。
* **装饰器鉴权**：内置 `@login_required` 与 `@survey_owner_required`，确保 API 安全与越权访问拦截。
* **策略模式校验**：采用 `QuestionValidator` 策略类，支持单选、多选（最少/最多项）、文本（长度限制）、数字（范围/整数限制）的业务级校验。
* **动态跳转逻辑**：支持基于题目答案的跳转（跳题、提前结束），并在后端实现逻辑兼容。

### 2. 题目版本管理系统（v2 新增）
* **版本控制**：题目支持多版本管理，每个题目都有版本号（version）和上一版本ID（previous_version_id），支持版本追溯和历史记录查看。
* **智能版本策略**：已发布问卷中的题目不能直接修改，系统自动检测并强制创建新版本，确保历史数据完整性。
* **另存为新题**：支持将现有题目另存为新版本，可在题库或问卷中独立使用。
* **历史快照**：修改题目时自动保存历史快照，支持查看和恢复旧版本。

### 3. 题库与共享系统（v2 新增）
* **题库管理**：支持创建个人题库和公共题库，可对题目进行分类管理。
* **题目共享**：支持将题目公开到公共题库或共享给指定用户，实现团队协作。
* **跨问卷复用**：同一题目可被多个问卷使用，修改时自动处理版本关系。
* **使用追踪**：记录题目被哪些问卷使用（used_in_surveys），修改时可查看影响范围。

### 4. 跨问卷统计（v2 新增）
* **全局题目统计**：通过 base_question_id 聚合同一题目在所有问卷中的回答数据，支持跨问卷的统计分析。
* **多维度分析**：自动对收集到的数据进行多维度分析（平均值、频次统计等）。

### 5. 响应式前端 (Alpine.js)
* **单页应用体验**：利用 `Alpine.js` 实现轻量级状态驱动界面，无需重量级框架即可完成复杂逻辑。
* **单题渲染模式**：问卷填写采用"单题推进"模式，支持实时校验与跳转逻辑触发。
* **向下兼容**：后端通过 `Utils.merge_survey_questions()` 方法将分离的题目和问卷上下文合并，前端无需改动即可渲染。

### 6. 完备的自动化测试
* **数据工厂**：`seed.py`（基础数据）与 `seed_mega.py`（50题/500份答卷的高压数据）。
* **测试矩阵**：`tests/megatest.py`（主要测试脚本，涵盖 v2 新功能的所有链路）。

---

## 🛠️ 技术栈
* **后端**: Flask, PyMongo, Bcrypt (加密), Werkzeug
* **前端**: Alpine.js, HTML5, CSS3
* **数据库**: MongoDB
* **测试**: Pytest, Requests

---

## 📦 快速开始

### 1. 安装环境
确保已安装 Python 3.8+ 和 MongoDB。
```bash
pip install -r requirements.txt
```

### 2. 启动数据库
确保 MongoDB 在本地 `27017` 端口运行。

### 3. 初始化数据 (可选)
运行以下脚本注入包含复杂跳转逻辑的测试数据：
```bash
python seed.py
```
*或者使用巨量压测数据：* `python seed_mega.py`

### 4. 启动服务
```bash
python app.py
```
访问地址：`http://localhost:5000`

---

## 🧪 自动化测试

项目提供了严谨的测试套件以验证系统稳定性：

* **运行主要测试脚本（v2 功能测试）：**
    ```bash
    pytest tests/megatest.py
    ```

> **注意**：v2 版本中，除 `tests/megatest.py` 外，其他测试脚本（如 test_api.py、test_demo.py 等）已弃用。

---

## 🛰️ 关键 API 概览

### 用户认证
| 接口            | 方法 | 说明              |
| :-------------- | :--- | :---------------- |
| `/api/register` | POST | 注册新账号        |
| `/api/login`    | POST | 建立 Session 登录 |
| `/api/logout`   | POST | 退出登录          |

### 问卷管理
| 接口                           | 方法 | 说明                   |
| :----------------------------- | :--- | :--------------------- |
| `/api/surveys`                 | POST | 创建问卷草稿           |
| `/api/my_surveys`              | GET  | 获取当前用户的问卷列表 |
| `/api/surveys/<id>`            | GET  | 获取问卷详情（含题目） |
| `/api/surveys/<id>/questions`  | POST | 添加题目               |
| `/api/surveys/<id>/publish`    | POST | 发布问卷（生成 Slug）  |
| `/api/surveys/<id>/statistics` | GET  | 获取聚合统计数据       |

### 题目管理（v2 新增）
| 接口                          | 方法 | 说明                     |
| :---------------------------- | :--- | :----------------------- |
| `/api/questions/<id>`         | PUT  | 更新题目（支持版本控制） |
| `/api/questions/<id>/history` | GET  | 获取题目历史版本         |
| `/api/questions/<id>/restore` | POST | 恢复题目到指定版本       |
| `/api/questions/<id>/usage`   | GET  | 查看题目被哪些问卷使用   |

### 题库管理（v2 新增）
| 接口                                       | 方法   | 说明           |
| :----------------------------------------- | :----- | :------------- |
| `/api/question_banks`                      | POST   | 创建题库       |
| `/api/question_banks`                      | GET    | 获取题库列表   |
| `/api/question_banks/<id>`                 | GET    | 获取题库详情   |
| `/api/question_banks/<id>/questions`       | POST   | 向题库添加题目 |
| `/api/question_banks/<id>/questions/<qid>` | DELETE | 从题库移除题目 |

### 跨问卷统计（v2 新增）
| 接口                                     | 方法 | 说明               |
| :--------------------------------------- | :--- | :----------------- |
| `/api/questions/<id>/cross_survey_stats` | GET  | 获取题目跨问卷统计 |

### 填写端
| 接口                         | 方法 | 说明                             |
| :--------------------------- | :--- | :------------------------------- |
| `/api/fill_survey/<slug>`    | GET  | 公开获取问卷内容（包含逻辑检查） |
| `/api/surveys/<slug>/submit` | POST | 提交答卷（触发后端强校验）       |

---

## 📂 项目结构
```
.
├── static/                 # 前端静态资源
│   ├── css/
│   │   └── style.css       # 样式表
│   ├── js/
│   │   ├── api.js          # 封装 Fetch API 的后端通信模块
│   │   └── app.js          # 基于 Alpine.js 的前端状态与逻辑控制
│   └── index.html          # 主页面（单页应用入口）
├── tests/                  # 测试目录
│   └── megatest.py         # v2 主要测试脚本（推荐使用）
├── app.py                  # Flask 应用核心逻辑、API 路由与中间件
├── README.md               # 项目说明文档
├── requirements.txt        # Python 依赖清单
├── v2schema               # v2 数据库文档结构定义
├── seed.py                # 基础数据初始化脚本
├── seed_mega.py           # 史诗级压力测试数据生成脚本
├── system.log             # 系统运行日志
├── mongodb_data/           # (本地) MongoDB 挂载数据目录
└── .pytest_cache/          # Pytest 缓存目录
```

---

## 🔄 v2 版本更新说明

### 新增功能
1. **题目版本管理**：支持题目多版本控制，自动处理版本关系
2. **题库系统**：支持个人题库和公共题库管理
3. **题目共享**：支持题目公开和用户间共享
4. **跨问卷统计**：支持同一题目在所有问卷中的聚合统计
5. **智能版本控制**：已发布问卷中的题目自动保护，强制创建新版本

### 数据库变更
- 新增 `question_banks` 集合：存储题库信息
- `questions` 集合新增字段：`base_question_id`、`version`、`previous_version_id`、`owner_id`、`is_public`、`shared_with_users`、`used_in_surveys`
- `answers` 集合新增字段：`base_question_id`（支持跨问卷统计）
- `users` 集合新增字段：`question_banks`

### 向下兼容
- 后端通过 `Utils.merge_survey_questions()` 方法保持前端 API 兼容性
- 前端无需改动即可使用 v2 功能

---

> **注意**：生产环境下请务必通过环境变量 `FLASK_SECRET_KEY` 和 `MONGO_URI` 修改默认配置。
