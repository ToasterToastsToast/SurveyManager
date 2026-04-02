#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import pytest
import requests
import random
import string
import uuid
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure

# 全局配置
BASE_URL = 'http://localhost:5000'
MONGO_URI = 'mongodb://localhost:27017/'
DB_NAME = 'survey_system'

def generate_random_string(length=8):
    """生成随机字符串用于测试数据去重"""
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))

# ==========================================
# Fixtures (夹具): 处理前置条件、依赖注入和清理操作 (优化点4 & 5)
# ==========================================

@pytest.fixture(scope="session", autouse=True)
def check_server_and_db():
    """测试前置检查：确保服务和数据库可用 (优化点3)"""
    try:
        response = requests.get(BASE_URL, timeout=3)
        response.raise_for_status()
    except requests.RequestException:
        pytest.exit(f"无法连接到 API 服务器 {BASE_URL}，请确保 app.py 已启动！")

    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=2000)
        client.admin.command('ping')
        client.close()
    except ConnectionFailure:
        pytest.exit(f"无法连接到 MongoDB {MONGO_URI}，请确保数据库已启动！")

@pytest.fixture(scope="session")
def db_cleanup():
    """Teardown：在整个测试会话结束后清理测试产生的数据 (优化点4)"""
    yield  # 让测试先执行
    
    print("\n--- 开始清理测试产生的脏数据 ---")
    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]
    
    # 清理带 test_ 前缀的用户及其关联数据
    users_to_delete = list(db.users.find({"username": {"$regex": "^test_"}}))
    user_ids = [u['_id'] for u in users_to_delete]
    
    if user_ids:
        # 清理问卷、题目和回答
        surveys = list(db.surveys.find({"user_id": {"$in": user_ids}}))
        survey_ids = [s['_id'] for s in surveys]
        
        db.questions.delete_many({"survey_id": {"$in": survey_ids}})
        db.answers.delete_many({"survey_id": {"$in": survey_ids}})
        db.surveys.delete_many({"user_id": {"$in": user_ids}})
        db.users.delete_many({"_id": {"$in": user_ids}})
        print(f"清理完成: 删除了 {len(user_ids)} 个测试用户及相关的问卷/题目/答卷。")
    client.close()

@pytest.fixture
def api_client():
    """提供一个保持 Session 的客户端"""
    session = requests.Session()
    return session

@pytest.fixture
def auth_client(api_client):
    """提供一个已登录的客户端和用户信息"""
    username = f"test_user_{generate_random_string()}"
    password = "password123"
    api_client.post(f'{BASE_URL}/api/register', json={
        'username': username, 'password': password, 'email': f'{username}@test.com'
    })
    api_client.post(f'{BASE_URL}/api/login', json={
        'username': username, 'password': password
    })
    return {'client': api_client, 'username': username}

# ==========================================
# 测试用例 (Test Cases)
# ==========================================

class TestBatchOperations:
    """批量操作测试"""
    
    def test_batch_register_accounts(self, api_client):
        """测试维度：批量设置新账号"""
        success_count = 0
        for i in range(5):
            username = f"test_batch_{generate_random_string()}"
            resp = api_client.post(f'{BASE_URL}/api/register', json={
                'username': username,
                'password': "batchpassword",
                'email': f"{username}@test.com"
            })
            if resp.status_code == 201:
                success_count += 1
        
        assert success_count == 5, "批量注册 5 个账号应当全部成功"


class TestAccessControl:
    """权限与状态控制测试"""
    
    def test_unauthorized_survey_creation(self, api_client):
        """测试维度：非登录状态下尝试创建问卷应被拒绝"""
        resp = api_client.post(f'{BASE_URL}/api/surveys', json={'title': 'Hack Survey'})
        assert resp.status_code == 401
        assert resp.json()['error'] == '请先登录'

    def test_anonymous_survey_access_and_submit(self, auth_client, api_client):
        """测试维度：未登录状态下访问并提交已发布的公开问卷"""
        creator_client = auth_client['client']
        
        # 1. 登录用户创建并发布公开问卷
        survey_resp = creator_client.post(f'{BASE_URL}/api/surveys', json={
            'title': 'Public Survey', 'is_anonymous': True, 'allow_multiple_submissions': True
        }).json()
        survey_id, slug = survey_resp['survey_id'], survey_resp['slug']
        
        creator_client.post(f'{BASE_URL}/api/surveys/{survey_id}/questions', json={
            'type': 'text', 'content': 'Any feedback?', 'is_required': False
        })
        creator_client.post(f'{BASE_URL}/api/surveys/{survey_id}/publish')
        
        # 2. 未登录用户 (api_client 是干净的 Session) 访问问卷
        get_resp = api_client.get(f'{BASE_URL}/api/fill_survey/{slug}')
        assert get_resp.status_code == 200
        assert get_resp.json()['survey']['title'] == 'Public Survey'
        question_id = get_resp.json()['questions'][0]['_id']
        
        # 3. 未登录用户提交问卷
        submit_resp = api_client.post(f'{BASE_URL}/api/surveys/{slug}/submit', json={
            'responses': [{'question_id': question_id, 'text': 'Anonymous feedback'}]
        })
        assert submit_resp.status_code == 201


class TestSurveyContentAndLogic:
    """问卷内容、多语言与逻辑测试"""

    def test_multilingual_support(self, auth_client):
        """测试维度：处理中文、英文、特殊字符及 Emoji"""
        client = auth_client['client']
        
        # 创建多语言问卷
        title = "全球化测试 Global Test 🌍"
        desc = "支持中文、English and Español"
        survey_resp = client.post(f'{BASE_URL}/api/surveys', json={
            'title': title, 'description': desc, 'allow_multiple_submissions': True
        }).json()
        survey_id, slug = survey_resp['survey_id'], survey_resp['slug']
        
        # 添加多语言问题
        client.post(f'{BASE_URL}/api/surveys/{survey_id}/questions', json={
            'type': 'text', 'content': '你的名字？What is your name? Nombre?', 'is_required': True
        })
        client.post(f'{BASE_URL}/api/surveys/{survey_id}/publish')
        
        # 验证获取到的多语言内容不乱码
        get_resp = client.get(f'{BASE_URL}/api/fill_survey/{slug}').json()
        assert get_resp['survey']['title'] == title
        question_id = get_resp['questions'][0]['_id']
        
        # 提交多语言答案
        submit_resp = client.post(f'{BASE_URL}/api/surveys/{slug}/submit', json={
            'responses': [{'question_id': question_id, 'value': '张三 John Doe 👦'}]
        })
        assert submit_resp.status_code == 201

    def test_logical_contradiction_design(self, auth_client):
        """测试维度：应对'至少选2个，至多选1个'的荒谬题目设计"""
        client = auth_client['client']
        
        survey_resp = client.post(f'{BASE_URL}/api/surveys', json={'title': 'Contradiction Test'}).json()
        survey_id, slug = survey_resp['survey_id'], survey_resp['slug']
        
        # 创建逻辑矛盾的题目：后端目前没有校验创建时的逻辑矛盾，应该会创建成功
        q_resp = client.post(f'{BASE_URL}/api/surveys/{survey_id}/questions', json={
            'type': 'multiple_choice',
            'content': '矛盾题：选2-1项',
            'is_required': True,
            'min_choices': 2,
            'max_choices': 1,
            'options': [{'value': 'A', 'text': 'A'}, {'value': 'B', 'text': 'B'}]
        })
        assert q_resp.status_code == 201
        question_id = q_resp.json()['question_id']
        client.post(f'{BASE_URL}/api/surveys/{survey_id}/publish')
        
        # 尝试提交：选1个会触发 min_choices 拦截，选2个会触发 max_choices 拦截，注定失败
        submit_1 = client.post(f'{BASE_URL}/api/surveys/{slug}/submit', json={
            'responses': [{'question_id': question_id, 'value': ['A']}]
        })
        assert submit_1.status_code == 400
        assert "最少需要选择 2 项" in submit_1.json()['error']
        
        submit_2 = client.post(f'{BASE_URL}/api/surveys/{slug}/submit', json={
            'responses': [{'question_id': question_id, 'value': ['A', 'B']}]
        })
        assert submit_2.status_code == 400
        assert "最多只能选择 1 项" in submit_2.json()['error']


class TestValidationIsolation:
    """隔离的 Negative Testing (优化点2)"""

    @pytest.fixture(autouse=True)
    def setup_validation_survey(self, auth_client):
        """为校验测试准备统一的问卷"""
        self.client = auth_client['client']
        survey_resp = self.client.post(f'{BASE_URL}/api/surveys', json={'title': 'Validation Test'}).json()
        self.survey_id = survey_resp['survey_id']
        self.slug = survey_resp['slug']
        
        # 准备各类题目
        self.q_text_id = self.client.post(f'{BASE_URL}/api/surveys/{self.survey_id}/questions', json={
            'type': 'text', 'content': '必填填空', 'is_required': True, 'min_length': 3
        }).json()['question_id']
        
        self.q_num_id = self.client.post(f'{BASE_URL}/api/surveys/{self.survey_id}/questions', json={
            'type': 'number', 'content': '数字18-60', 'is_required': False, 'min_value': 18, 'max_value': 60
        }).json()['question_id']
        
        self.client.post(f'{BASE_URL}/api/surveys/{self.survey_id}/publish')

    def test_validation_missing_required(self):
        """隔离测试：必填项未填"""
        resp = self.client.post(f'{BASE_URL}/api/surveys/{self.slug}/submit', json={
            'responses': [{'question_id': self.q_text_id, 'value': ''}] # 为空
        })
        assert resp.status_code == 400
        assert "是必填项" in resp.json()['error']

    def test_validation_out_of_bounds_number(self):
        """隔离测试：数字越界"""
        # 满足文本必填条件，仅触发数字错误
        resp = self.client.post(f'{BASE_URL}/api/surveys/{self.slug}/submit', json={
            'responses': [
                {'question_id': self.q_text_id, 'value': 'abc'},
                {'question_id': self.q_num_id, 'value': 17} # 小于 18
            ]
        })
        assert resp.status_code == 400
        assert "不能小于 18" in resp.json()['error']

    def test_validation_type_error(self):
        """隔离测试：类型错误 (应传数字传了字符串)"""
        resp = self.client.post(f'{BASE_URL}/api/surveys/{self.slug}/submit', json={
            'responses': [
                {'question_id': self.q_text_id, 'value': 'abc'},
                {'question_id': self.q_num_id, 'value': "我不是数字"} 
            ]
        })
        assert resp.status_code == 400
        assert "必须是数字" in resp.json()['error']