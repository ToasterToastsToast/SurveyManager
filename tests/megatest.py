# -*- coding: utf-8 -*-
"""
问卷系统 v2 新功能完整测试套件
覆盖需求变更说明中的全部八项新需求，基于 app.py 的实际实现逻辑编写。

运行方式：
    pytest test_v2_features.py -v
"""

import pytest
import requests
from bson import ObjectId
from pymongo import MongoClient

# ==========================================
# 全局配置
# ==========================================

BASE_URL = "http://127.0.0.1:5000"
MONGO_URI = "mongodb://localhost:27017/"
DB_NAME = "survey_system"


# ==========================================
# Fixtures：统一的登录、数据创建与清理逻辑
# ==========================================

@pytest.fixture(scope="session")
def mongo_db():
    """提供全局数据库连接"""
    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]
    yield db
    client.close()


@pytest.fixture
def auth_session(mongo_db):
    """
    创建一个已注册并登录的用户会话。
    测试结束后自动清理该用户产生的所有数据（问卷、题目、回答、题库、用户本身）。
    """
    session = requests.Session()
    username = f"user_{ObjectId()}"
    password = "password123"

    session.post(f"{BASE_URL}/api/register", json={
        "username": username,
        "password": password,
        "email": f"{username}@test.com"
    })
    login_resp = session.post(f"{BASE_URL}/api/login", json={
        "username": username,
        "password": password
    })
    assert login_resp.status_code == 200, f"登录失败: {login_resp.text}"
    user_id = login_resp.json()["user_id"]

    yield session, user_id

    # 清理：按依赖顺序删除
    u_oid = ObjectId(user_id)
    surveys = list(mongo_db.surveys.find({"user_id": u_oid}))
    s_ids = [s["_id"] for s in surveys]

    mongo_db.question_banks.delete_many({"owner_id": u_oid})
    mongo_db.answers.delete_many({"survey_id": {"$in": s_ids}})
    mongo_db.questions.delete_many({"owner_id": u_oid})
    mongo_db.surveys.delete_many({"user_id": u_oid})
    mongo_db.users.delete_one({"_id": u_oid})


# ==========================================
# 通用辅助函数
# ==========================================

def create_survey(session, title="测试问卷"):
    """创建问卷，返回 (survey_id, slug)"""
    resp = session.post(f"{BASE_URL}/api/surveys", json={"title": title})
    assert resp.status_code == 201, f"创建问卷失败: {resp.text}"
    data = resp.json()
    return data["survey_id"], data["slug"]


def add_question(session, survey_id, content="测试题目", q_type="text", is_required=True, **kwargs):
    """向问卷添加题目，返回 question_id"""
    payload = {"type": q_type, "content": content, "is_required": is_required, **kwargs}
    resp = session.post(f"{BASE_URL}/api/surveys/{survey_id}/questions", json=payload)
    assert resp.status_code == 201, f"创建题目失败: {resp.text}"
    return resp.json()["question_id"]


def publish_survey(session, survey_id):
    """发布问卷"""
    resp = session.post(f"{BASE_URL}/api/surveys/{survey_id}/publish")
    assert resp.status_code == 200, f"发布问卷失败: {resp.text}"


def reuse_question(session, survey_id, question_id):
    """在问卷中复用题目，返回新题目的 question_id"""
    resp = session.post(f"{BASE_URL}/api/surveys/{survey_id}/reuse_question",
                        json={"question_id": question_id})
    assert resp.status_code == 200, f"复用题目失败: {resp.text}"
    return resp.json()["question_id"]


def submit_survey(session, slug, responses):
    """提交问卷回答"""
    resp = session.post(f"{BASE_URL}/api/surveys/{slug}/submit",
                        json={"responses": responses})
    assert resp.status_code == 201, f"提交问卷失败: {resp.text}"
    return resp


# ==========================================
# 需求一：保存常用题目，方便重复使用
# ==========================================

class TestQuestionReuse:
    """需求一 & 二：题目复用与跨问卷共享"""

    def test_reuse_creates_independent_copy(self, auth_session, mongo_db):
        """
        复用题目时，应在目标问卷中创建一个独立的题目副本，
        而非直接共享同一文档，保证原题目的 used_in_surveys 不被污染。
        """
        session, _ = auth_session

        s1_id, _ = create_survey(session, "问卷A")
        q_id = add_question(session, s1_id, "原始题目")

        s2_id, _ = create_survey(session, "问卷B")
        new_q_id = reuse_question(session, s2_id, q_id)

        # 复用应产生新的题目ID
        assert new_q_id != q_id, "复用应创建新题目文档，不应是同一个ID"

        # 新题应与原题共享同一 base_question_id
        orig_doc = mongo_db.questions.find_one({"_id": ObjectId(q_id)})
        new_doc = mongo_db.questions.find_one({"_id": ObjectId(new_q_id)})
        assert str(new_doc["base_question_id"]) == str(orig_doc["base_question_id"]), \
            "复用的题目应继承原题的 base_question_id"

        # 原题的 used_in_surveys 不应包含问卷B（因为问卷B拿到的是副本）
        assert ObjectId(s2_id) not in orig_doc.get("used_in_surveys", []), \
            "原题的 used_in_surveys 不应被污染"

        # 副本的 used_in_surveys 应只包含问卷B
        assert ObjectId(s2_id) in new_doc.get("used_in_surveys", []), \
            "复用副本的 used_in_surveys 应指向目标问卷"

    def test_reuse_copies_question_content(self, auth_session, mongo_db):
        """复用的题目应包含与原题相同的内容字段"""
        session, _ = auth_session

        s1_id, _ = create_survey(session, "问卷A")
        q_id = add_question(session, s1_id, "需要被复用的题目", q_type="number")

        s2_id, _ = create_survey(session, "问卷B")
        new_q_id = reuse_question(session, s2_id, q_id)

        orig_doc = mongo_db.questions.find_one({"_id": ObjectId(q_id)})
        new_doc = mongo_db.questions.find_one({"_id": ObjectId(new_q_id)})

        assert new_doc["content"] == orig_doc["content"], "内容应相同"
        assert new_doc["type"] == orig_doc["type"], "题型应相同"

    def test_one_question_used_in_multiple_surveys(self, auth_session, mongo_db):
        """验证同一题目（通过复用）可被多个问卷使用"""
        session, _ = auth_session

        s1_id, _ = create_survey(session, "问卷1")
        q_id = add_question(session, s1_id, "年龄题")

        # 复用到问卷2和问卷3
        s2_id, _ = create_survey(session, "问卷2")
        q2_id = reuse_question(session, s2_id, q_id)

        s3_id, _ = create_survey(session, "问卷3")
        q3_id = reuse_question(session, s3_id, q_id)

        # 所有副本应有相同的 base_question_id
        orig = mongo_db.questions.find_one({"_id": ObjectId(q_id)})
        c2 = mongo_db.questions.find_one({"_id": ObjectId(q2_id)})
        c3 = mongo_db.questions.find_one({"_id": ObjectId(q3_id)})

        assert str(c2["base_question_id"]) == str(orig["base_question_id"])
        assert str(c3["base_question_id"]) == str(orig["base_question_id"])


# ==========================================
# 需求二：题目分享
# ==========================================

class TestQuestionSharing:
    """需求二：题目分享给其他用户"""

    def test_share_question_publicly(self, auth_session, mongo_db):
        """题目所有者可以将题目设为公开"""
        session, _ = auth_session

        s_id, _ = create_survey(session)
        q_id = add_question(session, s_id, "公开分享题目")

        resp = session.post(f"{BASE_URL}/api/questions/{q_id}/share", json={
            "is_public": True,
            "shared_with_users": []
        })
        assert resp.status_code == 200, f"分享失败: {resp.text}"

        q_doc = mongo_db.questions.find_one({"_id": ObjectId(q_id)})
        assert q_doc["is_public"] is True, "is_public 应被设置为 True"

    def test_share_question_with_specific_users(self, auth_session, mongo_db):
        """题目可以只分享给指定用户"""
        session, user_id = auth_session

        s_id, _ = create_survey(session)
        q_id = add_question(session, s_id, "指定用户分享题目")

        # 创建另一个用户来分享
        other_username = f"other_{ObjectId()}"
        reg_resp = requests.post(f"{BASE_URL}/api/register", json={
            "username": other_username,
            "password": "password123",
            "email": f"{other_username}@test.com"
        })
        other_user_id = reg_resp.json()["user_id"]

        try:
            resp = session.post(f"{BASE_URL}/api/questions/{q_id}/share", json={
                "is_public": False,
                "shared_with_users": [other_user_id]
            })
            assert resp.status_code == 200

            q_doc = mongo_db.questions.find_one({"_id": ObjectId(q_id)})
            assert q_doc["is_public"] is False
            assert ObjectId(other_user_id) in q_doc.get("shared_with_users", []), \
                "目标用户应出现在 shared_with_users 中"
        finally:
            mongo_db.users.delete_one({"_id": ObjectId(other_user_id)})

    def test_non_owner_cannot_share(self, auth_session, mongo_db):
        """非题目所有者不能分享题目"""
        session, _ = auth_session

        s_id, _ = create_survey(session)
        q_id = add_question(session, s_id, "权限测试题目")

        # 创建另一个已登录的会话
        other_session = requests.Session()
        other_username = f"other_{ObjectId()}"
        other_session.post(f"{BASE_URL}/api/register", json={
            "username": other_username, "password": "pw", "email": f"{other_username}@t.com"
        })
        login_resp = other_session.post(f"{BASE_URL}/api/login", json={
            "username": other_username, "password": "pw"
        })
        other_user_id = login_resp.json()["user_id"]

        try:
            resp = other_session.post(f"{BASE_URL}/api/questions/{q_id}/share", json={
                "is_public": True, "shared_with_users": []
            })
            assert resp.status_code == 403, "非所有者不应有分享权限"
        finally:
            mongo_db.users.delete_one({"_id": ObjectId(other_user_id)})

    def test_public_question_can_be_reused_by_others(self, auth_session, mongo_db):
        """公开的题目可以被其他用户的问卷复用"""
        session, _ = auth_session

        s_id, _ = create_survey(session)
        q_id = add_question(session, s_id, "公开题目")

        # 设为公开
        session.post(f"{BASE_URL}/api/questions/{q_id}/share", json={
            "is_public": True, "shared_with_users": []
        })

        # 另一个用户复用
        other_session = requests.Session()
        other_username = f"other_{ObjectId()}"
        other_session.post(f"{BASE_URL}/api/register", json={
            "username": other_username, "password": "pw", "email": f"{other_username}@t.com"
        })
        login_resp = other_session.post(f"{BASE_URL}/api/login", json={
            "username": other_username, "password": "pw"
        })
        other_user_id = login_resp.json()["user_id"]

        try:
            other_s_id, _ = create_survey(other_session, "他人问卷")
            other_q_id = reuse_question(other_session, other_s_id, q_id)
            assert other_q_id is not None, "公开题目应可被他人复用"
        finally:
            mongo_db.questions.delete_many({"owner_id": ObjectId(other_user_id)})
            mongo_db.surveys.delete_many({"user_id": ObjectId(other_user_id)})
            mongo_db.users.delete_one({"_id": ObjectId(other_user_id)})


# ==========================================
# 需求三：修改题目不影响已发布的问卷
# ==========================================

class TestPublishedSurveyProtection:
    """需求三：已发布问卷的题目不可被直接修改"""

    def test_cannot_modify_question_in_published_survey(self, auth_session):
        """对已发布问卷中的题目发起修改请求，应返回 403"""
        session, _ = auth_session

        s_id, _ = create_survey(session, "将发布的问卷")
        q_id = add_question(session, s_id, "发布前的内容")
        publish_survey(session, s_id)

        resp = session.put(f"{BASE_URL}/api/questions/{q_id}", json={
            "survey_id": s_id,
            "content": "尝试修改已发布问卷中的题目"
        })
        assert resp.status_code == 403, "已发布问卷的题目不应允许修改"

    def test_published_survey_content_unchanged_after_attempted_edit(self, auth_session, mongo_db):
        """已发布问卷的题目被拒绝修改后，内容应保持原样"""
        session, _ = auth_session

        original_content = "原始内容不应变化"
        s_id, _ = create_survey(session)
        q_id = add_question(session, s_id, original_content)
        publish_survey(session, s_id)

        session.put(f"{BASE_URL}/api/questions/{q_id}", json={
            "survey_id": s_id,
            "content": "尝试覆盖"
        })

        q_doc = mongo_db.questions.find_one({"_id": ObjectId(q_id)})
        assert q_doc["content"] == original_content, "原始内容应保持不变"

    def test_save_as_new_creates_new_version_for_published_question(self, auth_session, mongo_db):
        """
        题目在已发布问卷中使用时，若强制 save_as_new=True（脱离问卷上下文修改），
        应生成新版本而非覆盖原题。
        """
        session, _ = auth_session

        s_id, _ = create_survey(session)
        q_id = add_question(session, s_id, "原始版本")
        publish_survey(session, s_id)

        # 不传 survey_id，使用 save_as_new（题库独立编辑场景）
        resp = session.put(f"{BASE_URL}/api/questions/{q_id}", json={
            "save_as_new": True,
            "content": "新版本内容"
        })
        assert resp.status_code == 200

        # 数据库中应出现新题目文档
        new_doc = mongo_db.questions.find_one({"content": "新版本内容"})
        assert new_doc is not None, "save_as_new 应创建新题目文档"
        assert str(new_doc["previous_version_id"]) == q_id, \
            "新版本的 previous_version_id 应指向旧版本"

        # 原题目内容应不变
        orig_doc = mongo_db.questions.find_one({"_id": ObjectId(q_id)})
        assert orig_doc["content"] == "原始版本", "原题目内容不应被修改"


# ==========================================
# 需求四：题目修改历史
# ==========================================

class TestQuestionHistory:
    """需求四：查看题目修改历史"""

    def test_in_place_update_creates_history_snapshot(self, auth_session, mongo_db):
        """
        在草稿问卷中修改题目（原地更新）时，
        应自动保存一份历史快照，使历史记录可追溯。
        """
        session, _ = auth_session

        s_id, _ = create_survey(session)
        q_id = add_question(session, s_id, "初始版本")

        # 草稿状态下原地修改
        resp = session.put(f"{BASE_URL}/api/questions/{q_id}", json={
            "survey_id": s_id,
            "content": "第二版本"
        })
        assert resp.status_code == 200

        # history 端点应返回至少2条记录（原始快照 + 当前）
        history_resp = session.get(f"{BASE_URL}/api/questions/{q_id}/history")
        assert history_resp.status_code == 200
        history = history_resp.json()["history"]
        assert len(history) >= 2, "修改后应有至少2条历史记录"

    def test_history_contains_old_and_new_content(self, auth_session, mongo_db):
        """历史记录中应同时包含旧内容和新内容"""
        session, _ = auth_session

        s_id, _ = create_survey(session)
        q_id = add_question(session, s_id, "旧内容")

        session.put(f"{BASE_URL}/api/questions/{q_id}", json={
            "survey_id": s_id,
            "content": "新内容"
        })

        history_resp = session.get(f"{BASE_URL}/api/questions/{q_id}/history")
        history = history_resp.json()["history"]
        contents = [h["content"] for h in history]

        assert "旧内容" in contents, "历史记录应包含旧版本内容"
        assert "新内容" in contents, "历史记录应包含新版本内容"

    def test_history_ordered_by_version(self, auth_session):
        """历史记录应按版本号升序排列"""
        session, _ = auth_session

        s_id, _ = create_survey(session)
        q_id = add_question(session, s_id, "v1")

        session.put(f"{BASE_URL}/api/questions/{q_id}", json={
            "survey_id": s_id, "content": "v2"
        })
        session.put(f"{BASE_URL}/api/questions/{q_id}", json={
            "survey_id": s_id, "content": "v3"
        })

        history_resp = session.get(f"{BASE_URL}/api/questions/{q_id}/history")
        history = history_resp.json()["history"]
        versions = [h.get("version", 1) for h in history]
        assert versions == sorted(versions), "历史应按版本号升序排列"

    def test_version_increments_on_update(self, auth_session, mongo_db):
        """每次内容修改后题目版本号应递增"""
        session, _ = auth_session

        s_id, _ = create_survey(session)
        q_id = add_question(session, s_id, "原始题目")

        orig_doc = mongo_db.questions.find_one({"_id": ObjectId(q_id)})
        original_version = orig_doc.get("version", 1)

        session.put(f"{BASE_URL}/api/questions/{q_id}", json={
            "survey_id": s_id,
            "content": "修改后"
        })

        updated_doc = mongo_db.questions.find_one({"_id": ObjectId(q_id)})
        assert updated_doc.get("version", 1) > original_version, "版本号应递增"

    def test_history_accessible_by_owner_only(self, auth_session, mongo_db):
        """非所有者（且未被分享）不应看到题目历史"""
        session, _ = auth_session

        s_id, _ = create_survey(session)
        q_id = add_question(session, s_id, "私有题目")

        other_session = requests.Session()
        other_username = f"other_{ObjectId()}"
        other_session.post(f"{BASE_URL}/api/register", json={
            "username": other_username, "password": "pw", "email": f"{other_username}@t.com"
        })
        login_resp = other_session.post(f"{BASE_URL}/api/login", json={
            "username": other_username, "password": "pw"
        })
        other_user_id = login_resp.json()["user_id"]

        try:
            resp = other_session.get(f"{BASE_URL}/api/questions/{q_id}/history")
            assert resp.status_code == 403, "非所有者不应访问题目历史"
        finally:
            mongo_db.users.delete_one({"_id": ObjectId(other_user_id)})


# ==========================================
# 需求五：同一题目的不同版本共存
# ==========================================

class TestQuestionVersionCoexistence:
    """需求五：不同版本可以同时存在，供不同问卷独立使用"""

    def test_save_as_new_both_versions_coexist(self, auth_session, mongo_db):
        """save_as_new 后，旧版本和新版本应同时存在于数据库"""
        session, _ = auth_session

        s_id, _ = create_survey(session)
        q_id = add_question(session, s_id, "版本1")

        resp = session.put(f"{BASE_URL}/api/questions/{q_id}", json={
            "save_as_new": True,
            "content": "版本2"
        })
        assert resp.status_code == 200

        v1 = mongo_db.questions.find_one({"_id": ObjectId(q_id)})
        v2 = mongo_db.questions.find_one({"content": "版本2"})

        assert v1 is not None, "旧版本应仍然存在"
        assert v2 is not None, "新版本应已创建"
        assert v1["_id"] != v2["_id"], "两个版本应是不同文档"

    def test_different_surveys_can_use_different_versions(self, auth_session, mongo_db):
        """问卷A 使用旧版本，问卷B 复用后更新为新版本，两者独立互不干扰"""
        session, _ = auth_session

        # 问卷A 有一个题目
        sa_id, _ = create_survey(session, "问卷A")
        q_id = add_question(session, sa_id, "旧版本内容")

        # 问卷B 复用该题，得到副本
        sb_id, _ = create_survey(session, "问卷B")
        new_q_id = reuse_question(session, sb_id, q_id)

        # 在问卷B 中修改副本（原地更新，因副本只被问卷B使用且是草稿）
        session.put(f"{BASE_URL}/api/questions/{new_q_id}", json={
            "survey_id": sb_id,
            "content": "新版本内容"
        })

        # 验证问卷A 的题目内容未变
        orig = mongo_db.questions.find_one({"_id": ObjectId(q_id)})
        assert orig["content"] == "旧版本内容", "问卷A 的题目不应受影响"

        # 验证问卷B 的题目内容已更新
        updated = mongo_db.questions.find_one({"_id": ObjectId(new_q_id)})
        assert updated["content"] == "新版本内容", "问卷B 的题目应已更新"

    def test_context_only_update_no_new_version(self, auth_session, mongo_db):
        """
        仅修改上下文属性（is_required），不应创建新版本文档，
        只更新原有文档中的上下文字段。
        """
        session, _ = auth_session

        s_id, _ = create_survey(session)
        q_id = add_question(session, s_id, "不变的题干", is_required=False)

        initial_count = mongo_db.questions.count_documents(
            {"base_question_id": ObjectId(q_id)}
        )

        session.put(f"{BASE_URL}/api/questions/{q_id}", json={
            "survey_id": s_id,
            "is_required": True
        })

        final_count = mongo_db.questions.count_documents(
            {"base_question_id": ObjectId(q_id)}
        )
        assert final_count == initial_count, "仅修改上下文属性不应产生新文档"

        q_doc = mongo_db.questions.find_one({"_id": ObjectId(q_id)})
        assert q_doc["is_required"] is True, "is_required 应已被更新"
        assert q_doc["content"] == "不变的题干", "题干内容应保持不变"


# ==========================================
# 需求六：查看题目被哪些问卷使用
# ==========================================

class TestQuestionUsage:
    """需求六：查看题目被哪些问卷使用"""

    def test_usage_shows_owning_survey(self, auth_session):
        """刚创建的题目应显示被其原始问卷使用"""
        session, _ = auth_session

        s_id, _ = create_survey(session, "唯一问卷")
        q_id = add_question(session, s_id, "使用情况测试题")

        resp = session.get(f"{BASE_URL}/api/questions/{q_id}/usage")
        assert resp.status_code == 200
        usage = resp.json()["usage"]
        survey_ids = [u["survey_id"] for u in usage]
        assert s_id in survey_ids, "题目应显示被其原始问卷使用"

    def test_usage_shows_all_surveys_after_reuse(self, auth_session, mongo_db):
        """
        复用题目后，通过原题目的 usage 端点，
        应能发现所有使用了相关版本的问卷（原题 + 副本）。
        """
        session, _ = auth_session

        s1_id, _ = create_survey(session, "问卷1")
        q_id = add_question(session, s1_id, "被复用的题目")

        s2_id, _ = create_survey(session, "问卷2")
        reuse_question(session, s2_id, q_id)

        resp = session.get(f"{BASE_URL}/api/questions/{q_id}/usage")
        assert resp.status_code == 200
        usage = resp.json()["usage"]
        # 至少能看到原始问卷（问卷1），因为原题的 used_in_surveys=[s1]
        assert len(usage) >= 1

    def test_usage_inaccessible_to_non_owner(self, auth_session, mongo_db):
        """非所有者不应查看题目的使用情况"""
        session, _ = auth_session

        s_id, _ = create_survey(session)
        q_id = add_question(session, s_id, "权限测试")

        other_session = requests.Session()
        other_username = f"other_{ObjectId()}"
        other_session.post(f"{BASE_URL}/api/register", json={
            "username": other_username, "password": "pw", "email": f"{other_username}@t.com"
        })
        login_resp = other_session.post(f"{BASE_URL}/api/login", json={
            "username": other_username, "password": "pw"
        })
        other_user_id = login_resp.json()["user_id"]

        try:
            resp = other_session.get(f"{BASE_URL}/api/questions/{q_id}/usage")
            assert resp.status_code == 403
        finally:
            mongo_db.users.delete_one({"_id": ObjectId(other_user_id)})


# ==========================================
# 需求四（续）：恢复旧版本
# ==========================================

class TestQuestionRestore:
    """需求四（恢复）：恢复题目到历史版本"""

    def test_restore_creates_new_version_based_on_old(self, auth_session, mongo_db):
        """
        恢复旧版本后，应创建一个新题目文档，
        内容与旧版本一致，previous_version_id 指向被恢复前的版本。
        """
        session, _ = auth_session

        s_id, _ = create_survey(session)
        q_id = add_question(session, s_id, "原始内容")

        # 修改题目，产生历史快照
        session.put(f"{BASE_URL}/api/questions/{q_id}", json={
            "survey_id": s_id, "content": "修改后内容"
        })

        history_resp = session.get(f"{BASE_URL}/api/questions/{q_id}/history")
        history = history_resp.json()["history"]
        # 找到内容为"原始内容"的历史版本
        old_version = next(h for h in history if h["content"] == "原始内容")
        old_version_id = old_version["_id"]

        restore_resp = session.post(f"{BASE_URL}/api/questions/{q_id}/restore", json={
            "version_id": old_version_id,
            "survey_id": s_id
        })
        assert restore_resp.status_code == 200
        new_q_id = restore_resp.json()["new_question_id"]

        restored_doc = mongo_db.questions.find_one({"_id": ObjectId(new_q_id)})
        assert restored_doc["content"] == "原始内容", "恢复后内容应与旧版本一致"
        assert str(restored_doc["previous_version_id"]) == q_id, \
            "previous_version_id 应指向被恢复前的版本"

    def test_restore_to_published_survey_is_rejected(self, auth_session):
        """已发布问卷不允许恢复版本（因为不允许修改已发布问卷内容）"""
        session, _ = auth_session

        s_id, _ = create_survey(session)
        q_id = add_question(session, s_id, "原始题目")
        publish_survey(session, s_id)

        resp = session.post(f"{BASE_URL}/api/questions/{q_id}/restore", json={
            "version_id": q_id,  # 即使恢复到自身也不行
            "survey_id": s_id
        })
        assert resp.status_code == 403, "已发布的问卷不应允许恢复版本"


# ==========================================
# 需求七：题库管理
# ==========================================

class TestQuestionBank:
    """需求七：题库的创建、查询、更新、删除及题目管理"""

    def test_create_question_bank(self, auth_session, mongo_db):
        """用户可以创建题库"""
        session, user_id = auth_session

        resp = session.post(f"{BASE_URL}/api/question_banks", json={
            "name": "我的题库",
            "description": "常用题目集合",
            "is_public": False
        })
        assert resp.status_code == 201, f"创建题库失败: {resp.text}"
        bank_id = resp.json()["bank_id"]

        bank_doc = mongo_db.question_banks.find_one({"_id": ObjectId(bank_id)})
        assert bank_doc is not None
        assert bank_doc["name"] == "我的题库"
        assert str(bank_doc["owner_id"]) == user_id

    def test_list_question_banks(self, auth_session):
        """用户可以获取自己的题库列表"""
        session, _ = auth_session

        session.post(f"{BASE_URL}/api/question_banks", json={"name": "题库A"})
        session.post(f"{BASE_URL}/api/question_banks", json={"name": "题库B"})

        resp = session.get(f"{BASE_URL}/api/question_banks")
        assert resp.status_code == 200
        banks = resp.json()["banks"]
        names = [b["name"] for b in banks]
        assert "题库A" in names
        assert "题库B" in names

    def test_update_question_bank(self, auth_session):
        """用户可以更新题库信息"""
        session, _ = auth_session

        bank_id = session.post(f"{BASE_URL}/api/question_banks",
                               json={"name": "原名称"}).json()["bank_id"]

        resp = session.put(f"{BASE_URL}/api/question_banks/{bank_id}", json={
            "name": "新名称",
            "description": "新描述"
        })
        assert resp.status_code == 200

        get_resp = session.get(f"{BASE_URL}/api/question_banks/{bank_id}")
        assert get_resp.status_code == 200
        bank = get_resp.json()["bank"]
        assert bank["name"] == "新名称"

    def test_delete_question_bank(self, auth_session, mongo_db):
        """用户可以删除题库"""
        session, _ = auth_session

        bank_id = session.post(f"{BASE_URL}/api/question_banks",
                               json={"name": "待删题库"}).json()["bank_id"]

        resp = session.delete(f"{BASE_URL}/api/question_banks/{bank_id}")
        assert resp.status_code == 200

        assert mongo_db.question_banks.find_one({"_id": ObjectId(bank_id)}) is None

    def test_add_question_to_bank(self, auth_session):
        """可以向题库中添加题目"""
        session, _ = auth_session

        bank_id = session.post(f"{BASE_URL}/api/question_banks",
                               json={"name": "测试题库"}).json()["bank_id"]

        s_id, _ = create_survey(session)
        q_id = add_question(session, s_id, "题库题目")

        resp = session.post(f"{BASE_URL}/api/question_banks/{bank_id}/questions", json={
            "question_id": q_id
        })
        assert resp.status_code == 201

    def test_list_bank_questions(self, auth_session):
        """可以获取题库中的题目列表"""
        session, _ = auth_session

        bank_id = session.post(f"{BASE_URL}/api/question_banks",
                               json={"name": "题库"}).json()["bank_id"]

        s_id, _ = create_survey(session)
        q_id = add_question(session, s_id, "题库题目1")
        session.post(f"{BASE_URL}/api/question_banks/{bank_id}/questions",
                     json={"question_id": q_id})

        resp = session.get(f"{BASE_URL}/api/question_banks/{bank_id}/questions")
        assert resp.status_code == 200
        questions = resp.json()["questions"]
        assert len(questions) >= 1

    def test_remove_question_from_bank(self, auth_session):
        """可以从题库中移除题目"""
        session, _ = auth_session

        bank_id = session.post(f"{BASE_URL}/api/question_banks",
                               json={"name": "题库"}).json()["bank_id"]

        s_id, _ = create_survey(session)
        q_id = add_question(session, s_id, "待移除题目")
        session.post(f"{BASE_URL}/api/question_banks/{bank_id}/questions",
                     json={"question_id": q_id})

        resp = session.delete(
            f"{BASE_URL}/api/question_banks/{bank_id}/questions/{q_id}"
        )
        assert resp.status_code == 200

        list_resp = session.get(f"{BASE_URL}/api/question_banks/{bank_id}/questions")
        questions = list_resp.json()["questions"]
        q_ids_in_bank = [str(q.get("_id", "")) for q in questions]
        assert q_id not in q_ids_in_bank, "题目应已从题库移除"

    def test_create_question_directly_in_bank(self, auth_session):
        """可以在题库中直接创建新题目"""
        session, _ = auth_session

        bank_id = session.post(f"{BASE_URL}/api/question_banks",
                               json={"name": "题库"}).json()["bank_id"]

        resp = session.post(f"{BASE_URL}/api/question_banks/{bank_id}/questions/create", json={
            "type": "text",
            "content": "直接在题库创建的题目"
        })
        assert resp.status_code == 201, f"在题库中创建题目失败: {resp.text}"

    def test_public_bank_accessible_to_others(self, auth_session, mongo_db):
        """公开的题库及其题目可以被其他用户访问和复用"""
        session, _ = auth_session

        bank_id = session.post(f"{BASE_URL}/api/question_banks", json={
            "name": "公共题库", "is_public": True
        }).json()["bank_id"]

        s_id, _ = create_survey(session)
        q_id = add_question(session, s_id, "公共题库的题目")
        session.post(f"{BASE_URL}/api/questions/{q_id}/share",
                     json={"is_public": True, "shared_with_users": []})
        session.post(f"{BASE_URL}/api/question_banks/{bank_id}/questions",
                     json={"question_id": q_id})

        # 另一个用户访问该题库
        other_session = requests.Session()
        other_username = f"other_{ObjectId()}"
        other_session.post(f"{BASE_URL}/api/register", json={
            "username": other_username, "password": "pw", "email": f"{other_username}@t.com"
        })
        login_resp = other_session.post(f"{BASE_URL}/api/login", json={
            "username": other_username, "password": "pw"
        })
        other_user_id = login_resp.json()["user_id"]

        try:
            other_s_id, _ = create_survey(other_session, "他人问卷")
            # 公开题目可被复用
            other_q_id = reuse_question(other_session, other_s_id, q_id)
            assert other_q_id is not None
        finally:
            mongo_db.questions.delete_many({"owner_id": ObjectId(other_user_id)})
            mongo_db.surveys.delete_many({"user_id": ObjectId(other_user_id)})
            mongo_db.users.delete_one({"_id": ObjectId(other_user_id)})


# ==========================================
# 需求八：跨问卷统计
# ==========================================

class TestCrossSurveyStatistics:
    """需求八：查看某个题目在所有问卷中的汇总统计"""

    def test_cross_survey_number_statistics(self, auth_session):
        """
        数字题跨问卷统计：多个问卷使用同一 base_question_id 的题目，
        提交回答后，统计应汇总所有问卷的数据。
        """
        session, _ = auth_session

        # 问卷1 + 原始题目
        s1_id, s1_slug = create_survey(session, "调查1")
        q_id = add_question(session, s1_id, "评分", q_type="number")
        publish_survey(session, s1_id)
        submit_survey(session, s1_slug, [{"question_id": q_id, "value": 8}])

        # 问卷2 复用题目
        s2_id, s2_slug = create_survey(session, "调查2")
        q2_id = reuse_question(session, s2_id, q_id)
        publish_survey(session, s2_id)
        submit_survey(session, s2_slug, [{"question_id": q2_id, "value": 10}])

        # 使用原始题目的 ID（即 base_question_id）调用跨问卷统计
        stats_resp = session.get(f"{BASE_URL}/api/questions/{q_id}/statistics")
        assert stats_resp.status_code == 200

        stats = stats_resp.json()["statistics"]
        assert stats["total_responses"] == 2, "应统计到来自2个问卷的共2条回答"
        assert stats["survey_count"] == 2, "应识别出2个问卷"
        assert stats["results"]["average"] == 9.0, "平均分应为 (8+10)/2=9.0"

    def test_cross_survey_text_statistics(self, auth_session):
        """文本题跨问卷统计：应汇总所有问卷的文本回答"""
        session, _ = auth_session

        s1_id, s1_slug = create_survey(session, "问卷X")
        q_id = add_question(session, s1_id, "请问你的意见", q_type="text", is_required=False)
        publish_survey(session, s1_id)
        submit_survey(session, s1_slug, [{"question_id": q_id, "value": "很好"}])

        s2_id, s2_slug = create_survey(session, "问卷Y")
        q2_id = reuse_question(session, s2_id, q_id)
        publish_survey(session, s2_id)
        submit_survey(session, s2_slug, [{"question_id": q2_id, "value": "非常好"}])

        stats_resp = session.get(f"{BASE_URL}/api/questions/{q_id}/statistics")
        assert stats_resp.status_code == 200
        stats = stats_resp.json()["statistics"]
        assert stats["total_responses"] == 2

    def test_cross_survey_stats_inaccessible_to_non_owner(self, auth_session, mongo_db):
        """非题目所有者不应查看跨问卷统计"""
        session, _ = auth_session

        s_id, _ = create_survey(session)
        q_id = add_question(session, s_id, "私有题")

        other_session = requests.Session()
        other_username = f"other_{ObjectId()}"
        other_session.post(f"{BASE_URL}/api/register", json={
            "username": other_username, "password": "pw", "email": f"{other_username}@t.com"
        })
        login_resp = other_session.post(f"{BASE_URL}/api/login", json={
            "username": other_username, "password": "pw"
        })
        other_user_id = login_resp.json()["user_id"]

        try:
            resp = other_session.get(f"{BASE_URL}/api/questions/{q_id}/statistics")
            assert resp.status_code == 403
        finally:
            mongo_db.users.delete_one({"_id": ObjectId(other_user_id)})

    def test_single_survey_stats_still_work(self, auth_session):
        """单问卷统计接口应仍然正常工作（向下兼容）"""
        session, _ = auth_session

        s_id, slug = create_survey(session, "兼容测试")
        q_id = add_question(session, s_id, "数字题", q_type="number")
        publish_survey(session, s_id)
        submit_survey(session, slug, [{"question_id": q_id, "value": 5}])

        resp = session.get(f"{BASE_URL}/api/surveys/{s_id}/statistics")
        assert resp.status_code == 200
        stats = resp.json()["statistics"]
        assert q_id in stats, "题目ID 应出现在统计结果中"
        assert stats[q_id]["results"]["average"] == 5.0


# ==========================================
# 集成测试：端到端完整流程
# ==========================================

class TestEndToEnd:
    """端到端集成测试：覆盖完整的题目生命周期"""

    def test_full_question_lifecycle(self, auth_session, mongo_db):
        """
        完整流程：创建题目 → 分享 → 复用 → 修改（版本分裂）
                  → 查询历史 → 恢复 → 查看使用情况 → 跨问卷统计
        """
        session, _ = auth_session

        # 1. 在问卷A中创建题目
        sa_id, sa_slug = create_survey(session, "生命周期问卷A")
        q_id = add_question(session, sa_id, "年龄", q_type="number")

        # 2. 分享题目
        share_resp = session.post(f"{BASE_URL}/api/questions/{q_id}/share", json={
            "is_public": True, "shared_with_users": []
        })
        assert share_resp.status_code == 200

        # 3. 在问卷B中复用
        sb_id, sb_slug = create_survey(session, "生命周期问卷B")
        q2_id = reuse_question(session, sb_id, q_id)

        # 4. 修改问卷B中的题目副本（原地更新）
        update_resp = session.put(f"{BASE_URL}/api/questions/{q2_id}", json={
            "survey_id": sb_id,
            "content": "您的年龄（周岁）"
        })
        assert update_resp.status_code == 200

        # 5. 查询历史版本
        history_resp = session.get(f"{BASE_URL}/api/questions/{q2_id}/history")
        assert history_resp.status_code == 200
        assert len(history_resp.json()["history"]) >= 2

        # 6. 发布两个问卷并提交回答
        publish_survey(session, sa_id)
        submit_survey(session, sa_slug, [{"question_id": q_id, "value": 25}])

        publish_survey(session, sb_id)
        submit_survey(session, sb_slug, [{"question_id": q2_id, "value": 30}])

        # 7. 查看题目使用情况
        usage_resp = session.get(f"{BASE_URL}/api/questions/{q_id}/usage")
        assert usage_resp.status_code == 200
        assert len(usage_resp.json()["usage"]) >= 1

        # 8. 跨问卷统计（使用原始 q_id，因为它是其自身的 base_question_id）
        stats_resp = session.get(f"{BASE_URL}/api/questions/{q_id}/statistics")
        assert stats_resp.status_code == 200
        stats = stats_resp.json()["statistics"]
        assert stats["total_responses"] == 2
        assert stats["results"]["average"] == 27.5

    def test_question_bank_to_survey_workflow(self, auth_session):
        """
        完整题库使用流程：创建题库 → 向题库添加题目 → 从题库复用到新问卷
        """
        session, _ = auth_session

        # 创建题库
        bank_id = session.post(f"{BASE_URL}/api/question_banks", json={
            "name": "通用题库", "is_public": False
        }).json()["bank_id"]

        # 在问卷中创建题目
        s_id, _ = create_survey(session, "源问卷")
        q_id = add_question(session, s_id, "常用题目")

        # 添加到题库
        session.post(f"{BASE_URL}/api/question_banks/{bank_id}/questions",
                     json={"question_id": q_id})

        # 验证题库中有该题目
        bank_q_resp = session.get(f"{BASE_URL}/api/question_banks/{bank_id}/questions")
        assert bank_q_resp.status_code == 200
        assert len(bank_q_resp.json()["questions"]) >= 1

        # 从题库选题复用到新问卷
        new_s_id, _ = create_survey(session, "目标问卷")
        new_q_id = reuse_question(session, new_s_id, q_id)
        assert new_q_id != q_id, "复用到新问卷应产生独立副本"