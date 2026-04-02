根据你提供的完整代码和架构，我为你重新编写了 `README.md`。这份文档不仅涵盖了基础安装，还详细描述了你代码中体现出的**高阶特性**（如自定义 JSON 处理、自动跳转逻辑、多种验证策略等），并整合了你提供的多个测试与数据脚本。

---

# 🚀 MongoDB 灵活问卷调研系统

本项目是一个基于 **Flask + MongoDB + Alpine.js** 构建的全栈问卷调查系统。支持复杂的题目类型、动态跳转逻辑、实时数据统计以及高并发下的自动化压力测试。

---

## ✨ 核心特性

### 1. 强力后端 (Python/Flask)
* **无缝 MongoDB 集成**：通过自定义 `MongoJSONProvider` 彻底消除 `ObjectId` 和 `Datetime` 转换的样板代码。
* **装饰器鉴权**：内置 `@login_required` 与 `@survey_owner_required`，确保 API 安全与越权访问拦截。
* **策略模式校验**：采用 `QuestionValidator` 策略类，支持单选、多选（最少/最多项）、文本（长度限制）、数字（范围/整数限制）的业务级校验。
* **动态跳转逻辑**：支持基于题目答案的跳转（跳题、提前结束），并在后端实现逻辑兼容。

### 2. 响应式前端 (Alpine.js)
* **单页应用体验**：利用 `Alpine.js` 实现轻量级状态驱动界面，无需重量级框架即可完成复杂逻辑。
* **单题渲染模式**：问卷填写采用“单题推进”模式，支持实时校验与跳转逻辑触发。
* **实时统计图表**：自动对收集到的数据进行多维度分析（平均值、频次统计等）。

### 3. 完备的自动化脚本
* **数据工厂**：`seed.py`（基础数据）与 `seed_mega.py`（50题/500份答卷的高压数据）。
* **测试矩阵**：`test_api.py`（Pytest 框架）、`test_demo.py`（流程演示脚本）涵盖了从注册登录到复杂逻辑拦截的所有链路。

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

* **运行标准 API 测试：**
    ```bash
    pytest test_api.py
    ```
* **运行全流程演示脚本：**
    ```bash
    python test_demo.py
    ```

---

## 🛰️ 关键 API 概览

### 用户认证
| 接口            | 方法 | 说明                 |
| :-------------- | :--- | :------------------- |
| `/api/register` | POST | 注册新账号           |
| `/api/login`    | POST | 建立 Session 登录    |
| `/api/me`       | GET  | 获取当前登录用户信息 |

### 问卷管理
| 接口                           | 方法 | 说明                        |
| :----------------------------- | :--- | :-------------------------- |
| `/api/surveys`                 | POST | 创建问卷草稿                |
| `/api/surveys/<id>/questions`  | POST | 批量/单个添加题目及限制条件 |
| `/api/questions/<id>`          | PUT  | 更新题目（含跳转逻辑配置）  |
| `/api/surveys/<id>/publish`    | POST | 发布问卷（生成 Slug）       |
| `/api/surveys/<id>/statistics` | GET  | 获取聚合统计数据            |

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
├── app.py                  # Flask 应用核心逻辑、API 路由与中间件
├── README.md               # 项目说明文档
├── requirements.txt        # Python 依赖清单
├── schema                  # 数据库文档结构定义 (JSON 格式参考)
├── seed.py                 # 基础数据初始化脚本
├── seed_mega.py            # 史诗级压力测试数据生成脚本
├── system.log              # 系统运行日志
├── test_api.py             # 基于 Pytest 的 API 自动化测试
├── test_demo.py            # API 全流程演示/冒烟测试脚本
├── mongodb_data/           # (本地) MongoDB 挂载数据目录
└── .pytest_cache/          # Pytest 缓存目录             # 静态资源 (CSS/JS)
```

---

> **注意**：生产环境下请务必通过环境变量 `FLASK_SECRET_KEY` 和 `MONGO_URI` 修改默认配置。