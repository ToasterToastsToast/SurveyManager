# -*- coding: utf-8 -*-
import bcrypt
import datetime
import uuid
from pymongo import MongoClient

# 1. 连接数据库
client = MongoClient('mongodb://localhost:27017/')
db = client['survey_system']

def seed_database():
    print("🌱 开始注入测试数据...")

    # 清理可能存在的旧测试账号（保持脚本可重复运行）
    db.users.delete_one({'username': 'test_admin'})
    
    # ==========================================
    # 阶段 1：创建测试用户
    # ==========================================
    password = b'123456'
    hashed_password = bcrypt.hashpw(password, bcrypt.gensalt())
    
    user = {
        'username': 'test_admin',
        'password': hashed_password,
        'email': 'test@example.com',
        'created_at': datetime.datetime.now(),
        'created_surveys': [],
        'submitted_answers': []
    }
    user_id = db.users.insert_one(user).inserted_id
    print(f"✅ 创建用户成功 | 用户名: test_admin | 密码: 123456 | ID: {user_id}")

    # ==========================================
    # 阶段 2：创建一份复杂的测试问卷
    # ==========================================
    survey = {
        'user_id': user_id,
        'title': '复杂逻辑与全题型测试问卷',
        'description': '这是一份由脚本自动生成的问卷，包含单选、多选、文本、数字，以及基于单选题的跳转逻辑。',
        'is_anonymous': False,
        'allow_multiple_submissions': True,
        'status': 'published',  # 直接设为已发布状态，前端立即可填
        'created_at': datetime.datetime.now(),
        'published_at': datetime.datetime.now(),
        'expire_at': None,
        'slug': str(uuid.uuid4())[:8],
        'question_count': 4,
        'submission_count': 0
    }
    survey_id = db.surveys.insert_one(survey).inserted_id
    print(f"✅ 创建问卷成功 | 标题: {survey['title']} | Slug: {survey['slug']}")

    # ==========================================
    # 阶段 3：插入各类题目
    # ==========================================
    questions = []
    
    # 第1题：单选题（带跳转逻辑的前提）
    q1 = {
        'survey_id': survey_id,
        'type': 'single_choice',
        'content': '您的当前职业状态是？',
        'is_required': True,
        'order': 1,
        'options': [
            {'value': '1', 'text': '学生'},
            {'value': '2', 'text': '在职员工'},
            {'value': '3', 'text': '自由职业/其他'}
        ],
        'jumps': [] # 先留空，稍后更新
    }
    q1_id = db.questions.insert_one(q1).inserted_id

    # 第2题：多选题
    q2 = {
        'survey_id': survey_id,
        'type': 'multiple_choice',
        'content': '您平时经常使用哪些前端技术栈？（最少选2项）',
        'is_required': True,
        'order': 2,
        'options': [
            {'value': 'vue', 'text': 'Vue.js'},
            {'value': 'react', 'text': 'React'},
            {'value': 'alpine', 'text': 'Alpine.js'},
            {'value': 'vanilla', 'text': '原生 JS/HTML/CSS'}
        ],
        'min_choices': 2,
        'max_choices': 4,
        'jumps': []
    }
    q2_id = db.questions.insert_one(q2).inserted_id

    # 第3题：文本题
    q3 = {
        'survey_id': survey_id,
        'type': 'text',
        'content': '请简述您对当前项目的优化建议（至少10个字）：',
        'is_required': False,
        'order': 3,
        'min_length': 10,
        'max_length': 500,
        'jumps': []
    }
    q3_id = db.questions.insert_one(q3).inserted_id

    # 第4题：数字题
    q4 = {
        'survey_id': survey_id,
        'type': 'number',
        'content': '请为本次体验打分（1-10分的整数）：',
        'is_required': True,
        'order': 4,
        'min_value': 1,
        'max_value': 10,
        'is_integer': True,
        'jumps': []
    }
    q4_id = db.questions.insert_one(q4).inserted_id
    print("✅ 题目插入完成 (单选、多选、文本、数字)")

    # ==========================================
    # 阶段 4：设置复杂的跳转逻辑
    # ==========================================
    # 逻辑：如果 第1题 选了 "1"(学生)，则直接跳到 第3题 (跳过第2题)
    jump_rule = [{
        'target_question_id': q3_id,
        'conditions': [{'condition': 'equals', 'value': '1'}]
    }]
    db.questions.update_one({'_id': q1_id}, {'$set': {'jumps': jump_rule}})
    print("✅ 跳转逻辑设置完成：选[学生]将跳过第2题")

    # ==========================================
    # 阶段 5：更新用户数据关联
    # ==========================================
    db.users.update_one(
        {'_id': user_id},
        {'$push': {'created_surveys': survey_id}}
    )

    print("\n🎉 注入完成！你可以打开系统进行测试了。")
    print("-" * 40)
    print(f"👉 登录账号: test_admin")
    print(f"👉 登录密码: 123456")
    print(f"👉 问卷直达链接: http://127.0.0.1:5000/?slug={survey['slug']}")
    print("-" * 40)

if __name__ == "__main__":
    seed_database()