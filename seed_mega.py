# -*- coding: utf-8 -*-
import bcrypt
import datetime
import uuid
import random
import string
from pymongo import MongoClient

# 1. 连接数据库
client = MongoClient('mongodb://localhost:27017/')
db = client['survey_system']

def random_string(length=10):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

def seed_mega_database():
    print("🔥 警告：正在清空数据库以准备史诗级数据注入...")
    db.users.delete_many({})
    db.surveys.delete_many({})
    db.questions.delete_many({})
    db.answers.delete_many({})

    # ==========================================
    # 阶段 1：创建核心测试用户
    # ==========================================
    print("👤 正在生成多用户生态...")
    hashed_password = bcrypt.hashpw(b'123456', bcrypt.gensalt())
    
    # 主账号
    admin_user = {
        'username': 'admin',
        'password': hashed_password,
        'email': 'admin@system.com',
        'created_at': datetime.datetime.now(),
        'created_surveys': [],
        'submitted_answers': []
    }
    admin_id = db.users.insert_one(admin_user).inserted_id

    # ==========================================
    # 阶段 2：创建巨型问卷 (50道题)
    # ==========================================
    print("📝 正在构建超大型问卷 [2026全球开发者生态大调查]...")
    mega_survey = {
        'user_id': admin_id,
        'title': '【压力测试】2026全球开发者生态大调查',
        'description': '这是一份由压测脚本生成的拥有50道题目、复杂跳转逻辑和500份海量模拟答卷的巨型测试问卷。',
        'is_anonymous': True,
        'allow_multiple_submissions': True,
        'status': 'published',
        'created_at': datetime.datetime.now(),
        'published_at': datetime.datetime.now(),
        'expire_at': None,
        'slug': 'mega2026',
        'question_count': 50,
        'submission_count': 0
    }
    mega_survey_id = db.surveys.insert_one(mega_survey).inserted_id
    db.users.update_one({'_id': admin_id}, {'$push': {'created_surveys': mega_survey_id}})

    # --- 插入50道题目 ---
    questions = []
    
    # Q1: 决定命运的单选题 (控制跳转逻辑)
    q1 = {
        'survey_id': mega_survey_id, 'type': 'single_choice', 'content': '您的主要技术方向是？（将决定后续题目）',
        'is_required': True, 'order': 1, 'jumps': [],
        'options': [{'value': 'frontend', 'text': '前端开发'}, {'value': 'backend', 'text': '后端开发'}, {'value': 'student', 'text': '在校学生 (直接结束)'}]
    }
    q1_id = db.questions.insert_one(q1).inserted_id
    questions.append({'id': q1_id, 'type': 'single_choice', 'options': ['frontend', 'backend', 'student']})

    # Q2: 极限多选题 (模拟技术栈，20个选项)
    tech_options = [{'value': f'tech_{i}', 'text': f'前沿技术框架 {i}'} for i in range(1, 21)]
    q2 = {
        'survey_id': mega_survey_id, 'type': 'multiple_choice', 'content': '您在生产环境中使用过哪些技术？(海量选项测试)',
        'is_required': True, 'order': 2, 'options': tech_options,
        'min_choices': 1, 'max_choices': 10, 'jumps': []
    }
    q2_id = db.questions.insert_one(q2).inserted_id
    questions.append({'id': q2_id, 'type': 'multiple_choice', 'options': [opt['value'] for opt in tech_options]})

    # Q3-Q48: 批量生成普通题目以撑大 DOM 树
    for i in range(3, 49):
        q_type = random.choice(['single_choice', 'multiple_choice', 'number', 'text'])
        q_doc = {
            'survey_id': mega_survey_id, 'type': q_type, 'content': f'第 {i} 题：随机自动生成的压测题目 (类型: {q_type})',
            'is_required': random.choice([True, False]), 'order': i, 'jumps': []
        }
        
        if q_type in ['single_choice', 'multiple_choice']:
            opts = [{'value': f'opt_{j}', 'text': f'随机选项 {j}'} for j in range(1, random.randint(3, 8))]
            q_doc['options'] = opts
            questions.append({'id': None, 'type': q_type, 'options': [o['value'] for o in opts], 'req': q_doc['is_required']})
        elif q_type == 'number':
            q_doc['min_value'] = 0
            q_doc['max_value'] = 1000
            q_doc['is_integer'] = True
            questions.append({'id': None, 'type': q_type, 'req': q_doc['is_required']})
        else:
            questions.append({'id': None, 'type': 'text', 'req': q_doc['is_required']})
            
        q_id = db.questions.insert_one(q_doc).inserted_id
        questions[-1]['id'] = q_id

    # Q49: 文本框
    q49 = {
        'survey_id': mega_survey_id, 'type': 'text', 'content': '请留下您的长篇大论（测试极长文本统计展示）：',
        'is_required': False, 'order': 49, 'jumps': []
    }
    q49_id = db.questions.insert_one(q49).inserted_id
    questions.append({'id': q49_id, 'type': 'text'})

    # Q50: 数字题
    q50 = {
        'survey_id': mega_survey_id, 'type': 'number', 'content': '请为本次压测打分 (1-100)：',
        'is_required': True, 'order': 50, 'min_value': 1, 'max_value': 100, 'is_integer': True, 'jumps': []
    }
    q50_id = db.questions.insert_one(q50).inserted_id
    questions.append({'id': q50_id, 'type': 'number'})

    # --- 设置复杂跳转逻辑 ---
    # 如果Q1选了'student'，直接结束问卷
    # 如果Q1选了'backend'，跳过Q2直接去Q3
    db.questions.update_one({'_id': q1_id}, {'$set': {'jumps': [
        {'target_question_id': None, 'conditions': [{'condition': 'equals', 'value': 'student'}]},
        {'target_question_id': questions[2]['id'], 'conditions': [{'condition': 'equals', 'value': 'backend'}]}
    ]}})

    # ==========================================
    # 阶段 3：注入海量真实答卷 (500份)
    # ==========================================
    print("📈 正在暴力生成 500 份模拟答卷（这可能需要几秒钟，考验后端计算的时候到了）...")
    answers = []
    for _ in range(500):
        responses = []
        # Q1决定命运
        q1_ans = random.choice(questions[0]['options'])
        responses.append({'question_id': questions[0]['id'], 'value': q1_ans, 'text': None})
        
        if q1_ans == 'student':
            # 直接结束，不填后续
            pass
        else:
            # 遍历后续题目
            for idx, q_info in enumerate(questions[1:]):
                # 触发后端跳过逻辑
                if q1_ans == 'backend' and idx == 0:  # 索引0是Q2
                    continue
                
                # 有概率不填非必填项
                if q_info.get('req') is False and random.random() > 0.7:
                    continue
                    
                if q_info['type'] == 'single_choice':
                    val = random.choice(q_info['options'])
                    responses.append({'question_id': q_info['id'], 'value': val, 'text': None})
                elif q_info['type'] == 'multiple_choice':
                    k = random.randint(1, min(3, len(q_info['options'])))
                    val = random.sample(q_info['options'], k)
                    responses.append({'question_id': q_info['id'], 'value': val, 'text': None})
                elif q_info['type'] == 'number':
                    val = random.randint(0, 100)
                    responses.append({'question_id': q_info['id'], 'value': val, 'text': None})
                elif q_info['type'] == 'text':
                    val = "长文本测试：" + random_string(random.randint(20, 100))
                    responses.append({'question_id': q_info['id'], 'value': val, 'text': val})

        answers.append({
            'survey_id': mega_survey_id,
            'user_id': None,
            'created_at': datetime.datetime.now(),
            'responses': responses
        })
    
    # 批量插入答卷
    db.answers.insert_many(answers)
    db.surveys.update_one({'_id': mega_survey_id}, {'$set': {'submission_count': 500}})

    # ==========================================
    # 阶段 4：生成一些边缘状态的辅助问卷
    # ==========================================
    print("📦 正在生成草稿、关闭、过期等边界状态问卷...")
    # 1. 已关闭的问卷
    db.surveys.insert_one({
        'user_id': admin_id, 'title': '【已归档】2025年旧版问卷', 'status': 'closed',
        'created_at': datetime.datetime.now(), 'slug': 'old2025', 'question_count': 5, 'submission_count': 120
    })
    # 2. 草稿状态问卷
    db.surveys.insert_one({
        'user_id': admin_id, 'title': '【草稿】未命名的新业务调研', 'status': 'draft',
        'created_at': datetime.datetime.now(), 'slug': 'draft01', 'question_count': 0, 'submission_count': 0
    })

    print("\n" + "="*50)
    print("🎉 史诗级压测数据注入完美收官！")
    print("="*50)
    print("👑 管理员账号: admin")
    print("🔑 管理员密码: 123456")
    print("\n🎯 重点测试建议：")
    print(" 1. 登录后查看【我的问卷】，测试50道题的DOM渲染是否卡顿。")
    print(" 2. 点击巨型问卷的【查看统计】，挑战后端统计 API 及前台排版能力 (500份并发数据计算)。")
    print(" 3. 退出登录，直接访问以下链接，测试填答时的 50 题超长滚动和跳转逻辑：")
    print("    👉 http://127.0.0.1:5000/?slug=mega2026")
    print("="*50)

if __name__ == "__main__":
    seed_mega_database()