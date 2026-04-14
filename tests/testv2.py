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

    # 清理数据：删除该用户创建的所有问卷、题目、回答和用户本身
    u_oid = ObjectId(user_id)
    surveys = list(mongo_db.surveys.find({"user_id": u_oid}))
    s_ids = [s['_id'] for s in surveys]
    
    mongo_db.answers.delete_many({"survey_id": {"$in": s_ids}})
    mongo_db.questions.delete_many({"owner_id": u_oid})
    mongo_db.surveys.delete_many({"user_id": u_oid})
    mongo_db.users.delete_one({"_id": u_oid})

# ==========================================
# 2. 核心功能测试类
# ==========================================

class TestSurveyVersioning:
    """重点测试：题目解耦与版本分裂逻辑"""

    def test_version_split_on_reuse(self, auth_session, mongo_db):
        """
        测试维度：当题目被两个问卷复用时，修改其中一个问卷的题干，是否触发版本分裂
        """
        session, user_id = auth_session

        # 1. 创建问卷 A 并添加一个题目
        survey_a = session.post(f"{BASE_URL}/api/surveys", json={"title": "问卷A"}).json()
        sa_id = survey_a['survey_id']
        
        q_resp = session.post(f"{BASE_URL}/api/surveys/{sa_id}/questions", json={
            "type": "text", "content": "原始题干", "is_required": True
        }).json()
        original_q_id = q_resp['question_id']

        # 2. 创建问卷 B 并复用该题目
        survey_b = session.post(f"{BASE_URL}/api/surveys", json={"title": "问卷B"}).json()
        sb_id = survey_b['survey_id']
        session.post(f"{BASE_URL}/api/surveys/{sb_id}/reuse_question", json={"question_id": original_q_id})

        # 验证数据库：此时该题目应被两个问卷使用
        q_doc = mongo_db.questions.find_one({"_id": ObjectId(original_q_id)})
        assert len(q_doc['used_in_surveys']) == 2

        # 3. 在问卷 B 中修改题干内容 (触发核心逻辑：Copy-on-Write)
        new_content = "修改后的新题干"
        update_resp = session.put(f"{BASE_URL}/api/questions/{original_q_id}", json={
            "survey_id": sb_id,
            "content": new_content
        })
        assert update_resp.status_code == 200

        # 4. 数据库断言：
        # - 应该生成了一个新的题目文档
        new_q_doc = mongo_db.questions.find_one({"content": new_content})
        assert new_q_doc is not None
        assert new_q_doc['_id'] != ObjectId(original_q_id)
        assert str(new_q_doc['previous_version_id']) == original_q_id
        
        # - 问卷 B 的题目引用应该已经指向了新 ID
        survey_b_updated = mongo_db.surveys.find_one({"_id": ObjectId(sb_id)})
        assert survey_b_updated['questions'][0]['question_id'] == new_q_doc['_id']

        # - 问卷 A 的题目引用应该保持原样（原始 ID）
        survey_a_doc = mongo_db.surveys.find_one({"_id": ObjectId(sa_id)})
        assert survey_a_doc['questions'][0]['question_id'] == ObjectId(original_q_id)

    def test_context_update_no_split(self, auth_session, mongo_db):
        """
        测试维度：仅修改上下文属性（如是否必填），不应触发题目版本分裂，只更新问卷内的 context
        """
        session, _ = auth_session
        
        # 创建问卷和题目
        s_id = session.post(f"{BASE_URL}/api/surveys", json={"title": "上下文测试"}).json()['survey_id']
        q_id = session.post(f"{BASE_URL}/api/surveys/{s_id}/questions", json={
            "type": "text", "content": "不变的题干", "is_required": False
        }).json()['question_id']

        # 修改 is_required (属于上下文)
        session.put(f"{BASE_URL}/api/questions/{q_id}", json={
            "survey_id": s_id,
            "is_required": True
        })

        # 断言：题目实体的 content 没变，且没有产生新文档
        q_count = mongo_db.questions.count_documents({"base_question_id": ObjectId(q_id)})
        assert q_count == 1
        
        # 断言：问卷内的上下文已更新
        survey_doc = mongo_db.surveys.find_one({"_id": ObjectId(s_id)})
        assert survey_doc['questions'][0]['is_required'] is True

class TestSurveyExecution:
    """测试填写、发布及统计逻辑"""

    def test_published_survey_protection(self, auth_session, mongo_db):
        """
        测试维度：已发布的问卷修改题目，必须强制分裂版本，保护历史数据
        """
        session, _ = auth_session
        s_id = session.post(f"{BASE_URL}/api/surveys", json={"title": "已发布问卷"}).json()['survey_id']
        q_id = session.post(f"{BASE_URL}/api/surveys/{s_id}/questions", json={
            "type": "text", "content": "发布前内容"
        }).json()['question_id']
        
        # 发布问卷
        session.post(f"{BASE_URL}/api/surveys/{s_id}/publish")

        # 修改题干
        session.put(f"{BASE_URL}/api/questions/{q_id}", json={
            "survey_id": s_id, "content": "发布后修改"
        })

        # 断言：即便只有这一个问卷在使用，因为已发布，也会触发分裂
        q_docs = list(mongo_db.questions.find({"base_question_id": ObjectId(q_id)}))
        assert len(q_docs) == 2

    def test_cross_survey_aggregation(self, auth_session):
        """
        测试维度：不同问卷使用相同 base_question_id 时，提交数据后统计逻辑是否正常（向下兼容性）
        """
        session, _ = auth_session
        
        # 1. 创建题目
        s1 = session.post(f"{BASE_URL}/api/surveys", json={"title": "调查1"}).json()
        q1_id = session.post(f"{BASE_URL}/api/surveys/{s1['survey_id']}/questions", json={
            "type": "number", "content": "评分"
        }).json()['question_id']
        session.post(f"{BASE_URL}/api/surveys/{s1['survey_id']}/publish")

        # 2. 提交一份答案
        session.post(f"{BASE_URL}/api/surveys/{s1['slug']}/submit", json={
            "responses": [{"question_id": q1_id, "value": 10}]
        })

        # 3. 获取统计
        stats_resp = session.get(f"{BASE_URL}/api/surveys/{s1['survey_id']}/statistics")
        assert stats_resp.status_code == 200
        # 验证统计中是否包含该题目 ID
        assert q1_id in stats_resp.json()['statistics']
        assert stats_resp.json()['statistics'][q1_id]['results']['average'] == 10