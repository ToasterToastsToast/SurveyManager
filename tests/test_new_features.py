import pytest
import requests
from bson import ObjectId
from pymongo import MongoClient

# 配置
BASE_URL = "http://127.0.0.1:5000"
MONGO_URI = "mongodb://localhost:27017/"
DB_NAME = "survey_system"

# ==========================================
# 1. Fixtures: 自动化处理登录与清理
# ==========================================

@pytest.fixture(scope="session")
def mongo_db():
    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]
    yield db
    client.close()

@pytest.fixture
def auth_session(mongo_db):
    """创建一个已登录的会话，并在测试后清理该用户产生的所有数据"""
    session = requests.Session()
    username = f"user_{ObjectId()}"
    password = "password123"
    
    # 注册并登录
    session.post(f"{BASE_URL}/api/register", json={
        "username": username, "password": password, "email": f"{username}@test.com"
    })
    login_resp = session.post(f"{BASE_URL}/api/login", json={
        "username": username, "password": password
    })
    user_id = login_resp.json()['user_id']
    
    yield session, user_id

    # 清理数据：删除该用户创建的所有问卷、题目、回答、题库和用户本身
    u_oid = ObjectId(user_id)
    surveys = list(mongo_db.surveys.find({"user_id": u_oid}))
    s_ids = [s['_id'] for s in surveys]
    
    # 清理题库
    mongo_db.question_banks.delete_many({"owner_id": u_oid})
    
    # 清理其他数据
    mongo_db.answers.delete_many({"survey_id": {"$in": s_ids}})
    mongo_db.questions.delete_many({"owner_id": u_oid})
    mongo_db.surveys.delete_many({"user_id": u_oid})
    mongo_db.users.delete_one({"_id": u_oid})

# ==========================================
# 2. 核心功能测试类
# ==========================================

class TestQuestionSharing:
    """测试题目分享功能"""

    def test_share_question(self, auth_session, mongo_db):
        """测试题目分享功能"""
        session, user_id = auth_session

        # 创建问卷和题目
        s_id = session.post(f"{BASE_URL}/api/surveys", json={"title": "测试问卷"}).json()['survey_id']
        q_id = session.post(f"{BASE_URL}/api/surveys/{s_id}/questions", json={
            "type": "text", "content": "测试题目", "is_required": True
        }).json()['question_id']

        # 分享题目
        share_resp = session.post(f"{BASE_URL}/api/questions/{q_id}/share", json={
            "is_public": True,
            "shared_with_users": []
        })
        assert share_resp.status_code == 200

        # 验证题目状态
        q_doc = mongo_db.questions.find_one({"_id": ObjectId(q_id)})
        assert q_doc['is_public'] is True

class TestQuestionHistory:
    """测试题目历史版本功能"""

    def test_get_question_history(self, auth_session):
        """测试获取题目历史版本"""
        session, user_id = auth_session

        # 创建问卷和题目
        s_id = session.post(f"{BASE_URL}/api/surveys", json={"title": "测试问卷"}).json()['survey_id']
        q_id = session.post(f"{BASE_URL}/api/surveys/{s_id}/questions", json={
            "type": "text", "content": "原始题目", "is_required": True
        }).json()['question_id']

        # 发布问卷，确保修改题目时触发版本分裂
        session.post(f"{BASE_URL}/api/surveys/{s_id}/publish")

        # 修改题目，触发版本分裂
        session.put(f"{BASE_URL}/api/questions/{q_id}", json={
            "survey_id": s_id,
            "content": "修改后的题目"
        })

        # 获取题目历史
        history_resp = session.get(f"{BASE_URL}/api/questions/{q_id}/history")
        assert history_resp.status_code == 200
        history = history_resp.json()['history']
        assert len(history) >= 2

    def test_restore_question_version(self, auth_session):
        """测试恢复题目到旧版本"""
        session, user_id = auth_session

        # 创建问卷和题目
        s_id = session.post(f"{BASE_URL}/api/surveys", json={"title": "测试问卷"}).json()['survey_id']
        q_id = session.post(f"{BASE_URL}/api/surveys/{s_id}/questions", json={
            "type": "text", "content": "原始题目", "is_required": True
        }).json()['question_id']

        # 修改题目，触发版本分裂
        session.put(f"{BASE_URL}/api/questions/{q_id}", json={
            "survey_id": s_id,
            "content": "修改后的题目"
        })

        # 获取题目历史
        history_resp = session.get(f"{BASE_URL}/api/questions/{q_id}/history")
        history = history_resp.json()['history']
        old_version_id = history[0]['_id']  # 第一个版本是旧版本

        # 恢复到旧版本
        restore_resp = session.post(f"{BASE_URL}/api/questions/{q_id}/restore", json={
            "version_id": old_version_id,
            "survey_id": s_id
        })
        assert restore_resp.status_code == 200

class TestQuestionUsage:
    """测试题目使用情况功能"""

    def test_get_question_usage(self, auth_session):
        """测试查看题目被哪些问卷使用"""
        session, user_id = auth_session

        # 创建第一个问卷和题目
        s1_id = session.post(f"{BASE_URL}/api/surveys", json={"title": "问卷1"}).json()['survey_id']
        q_id = session.post(f"{BASE_URL}/api/surveys/{s1_id}/questions", json={
            "type": "text", "content": "测试题目", "is_required": True
        }).json()['question_id']

        # 创建第二个问卷并复用该题目
        s2_id = session.post(f"{BASE_URL}/api/surveys", json={"title": "问卷2"}).json()['survey_id']
        session.post(f"{BASE_URL}/api/surveys/{s2_id}/reuse_question", json={"question_id": q_id})

        # 获取题目使用情况
        usage_resp = session.get(f"{BASE_URL}/api/questions/{q_id}/usage")
        assert usage_resp.status_code == 200
        usage = usage_resp.json()['usage']
        assert len(usage) == 2

class TestQuestionBank:
    """测试题库管理功能"""

    def test_create_and_manage_bank(self, auth_session, mongo_db):
        """测试创建和管理题库"""
        session, user_id = auth_session

        # 创建题库
        bank_resp = session.post(f"{BASE_URL}/api/question_banks", json={
            "name": "测试题库",
            "description": "测试题库描述",
            "is_public": False
        })
        assert bank_resp.status_code == 201
        bank_id = bank_resp.json()['bank_id']

        # 获取题库列表
        banks_resp = session.get(f"{BASE_URL}/api/question_banks")
        assert banks_resp.status_code == 200
        banks = banks_resp.json()['banks']
        assert any(bank['_id'] == bank_id for bank in banks)

        # 更新题库
        update_resp = session.put(f"{BASE_URL}/api/question_banks/{bank_id}", json={
            "name": "更新后的题库名称"
        })
        assert update_resp.status_code == 200

        # 删除题库
        delete_resp = session.delete(f"{BASE_URL}/api/question_banks/{bank_id}")
        assert delete_resp.status_code == 200

    def test_bank_questions_management(self, auth_session):
        """测试题库题目管理"""
        session, user_id = auth_session

        # 创建题库
        bank_resp = session.post(f"{BASE_URL}/api/question_banks", json={
            "name": "测试题库",
            "description": "测试题库描述"
        })
        bank_id = bank_resp.json()['bank_id']

        # 创建题目
        s_id = session.post(f"{BASE_URL}/api/surveys", json={"title": "测试问卷"}).json()['survey_id']
        q_id = session.post(f"{BASE_URL}/api/surveys/{s_id}/questions", json={
            "type": "text", "content": "测试题目", "is_required": True
        }).json()['question_id']

        # 向题库添加题目
        add_resp = session.post(f"{BASE_URL}/api/question_banks/{bank_id}/questions", json={
            "question_id": q_id
        })
        assert add_resp.status_code == 201

        # 获取题库中的题目
        banks_questions_resp = session.get(f"{BASE_URL}/api/question_banks/{bank_id}/questions")
        assert banks_questions_resp.status_code == 200
        questions = banks_questions_resp.json()['questions']
        assert len(questions) == 1

        # 从题库移除题目
        remove_resp = session.delete(f"{BASE_URL}/api/question_banks/{bank_id}/questions/{q_id}")
        assert remove_resp.status_code == 200

class TestCrossSurveyStatistics:
    """测试跨问卷统计功能"""

    def test_cross_survey_statistics(self, auth_session):
        """测试基于base_question_id的跨问卷统计"""
        session, user_id = auth_session

        # 创建第一个问卷和题目
        s1_resp = session.post(f"{BASE_URL}/api/surveys", json={"title": "问卷1"}).json()
        s1_id = s1_resp['survey_id']
        s1_slug = s1_resp['slug']
        
        q_resp = session.post(f"{BASE_URL}/api/surveys/{s1_id}/questions", json={
            "type": "number", "content": "评分", "is_required": True
        }).json()
        q_id = q_resp['question_id']

        # 发布第一个问卷
        session.post(f"{BASE_URL}/api/surveys/{s1_id}/publish")

        # 提交第一个问卷的回答
        session.post(f"{BASE_URL}/api/surveys/{s1_slug}/submit", json={
            "responses": [{"question_id": q_id, "value": 8}]
        })

        # 创建第二个问卷并复用该题目
        s2_resp = session.post(f"{BASE_URL}/api/surveys", json={"title": "问卷2"}).json()
        s2_id = s2_resp['survey_id']
        s2_slug = s2_resp['slug']
        session.post(f"{BASE_URL}/api/surveys/{s2_id}/reuse_question", json={"question_id": q_id})

        # 发布第二个问卷
        session.post(f"{BASE_URL}/api/surveys/{s2_id}/publish")

        # 提交第二个问卷的回答
        session.post(f"{BASE_URL}/api/surveys/{s2_slug}/submit", json={
            "responses": [{"question_id": q_id, "value": 9}]
        })

        # 获取题目信息，获取base_question_id
        question_resp = session.get(f"{BASE_URL}/api/surveys/{s1_id}")
        base_question_id = question_resp.json()['questions'][0]['base_question_id']

        # 获取跨问卷统计
        stats_resp = session.get(f"{BASE_URL}/api/questions/{base_question_id}/statistics")
        assert stats_resp.status_code == 200
        statistics = stats_resp.json()['statistics']
        assert statistics['total_responses'] == 2
        assert statistics['survey_count'] == 2
        assert statistics['results']['average'] == 8.5
