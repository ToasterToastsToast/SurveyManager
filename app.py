# -*- coding: utf-8 -*-

import logging
from flask import Flask, request, jsonify, session, send_from_directory
from flask.json.provider import DefaultJSONProvider
from pymongo import MongoClient
from bson.objectid import ObjectId
import bcrypt
import datetime
import uuid
import os
from functools import wraps
from werkzeug.exceptions import HTTPException

# ==========================================
# 1. 配置与初始化
# ==========================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('system.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
# 使用环境变量提升部署灵活性
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'your_secret_key')
MONGO_URI = os.getenv('MONGO_URI', 'mongodb://localhost:27017/')

client = MongoClient(MONGO_URI)
db = client['survey_system']

users_collection = db['users']
surveys_collection = db['surveys']
questions_collection = db['questions']
answers_collection = db['answers']

# ==========================================
# 2. 核心扩展：自定义 JSON 编码器 (彻底消除 ObjectId 转换的样板代码)
# ==========================================
class MongoJSONProvider(DefaultJSONProvider):
    def default(self, obj):
        if isinstance(obj, ObjectId):
            return str(obj)
        if isinstance(obj, datetime.datetime):
            return obj.isoformat()
        return super().default(obj)

app.json = MongoJSONProvider(app)

# ==========================================
# 3. 装饰器与中间件 (集中处理鉴权和权限)
# ==========================================
def login_required(f):
    """验证登录状态的装饰器"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': '请先登录'}), 401
        return f(*args, **kwargs)
    return decorated_function

def survey_owner_required(f):
    """验证问卷所有权的装饰器（需配合login_required使用）"""
    @wraps(f)
    def decorated_function(survey_id, *args, **kwargs):
        survey = surveys_collection.find_one({'_id': ObjectId(survey_id)})
        if not survey:
            return jsonify({'error': '问卷不存在'}), 404
        if str(survey['user_id']) != session['user_id']:
            logger.warning(f'越权操作警告：用户 {session.get("username")} 尝试操作问卷 {survey_id}')
            return jsonify({'error': '无权操作此问卷'}), 403
        # 将查询到的survey传递给视图函数，避免重复查询
        return f(survey_id, survey=survey, *args, **kwargs)
    return decorated_function

# ==========================================
# 4. 辅助工具类 (为二阶段扩展做准备)
# ==========================================
class Utils:
    @staticmethod
    def hash_password(password):
        return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())

    @staticmethod
    def check_password(password, hashed_password):
        return bcrypt.checkpw(password.encode('utf-8'), hashed_password)

    @staticmethod
    def generate_slug():
        return str(uuid.uuid4())[:8]

class QuestionValidator:
    """
    题目校验策略类。
    二阶段如果新增题型，只需在这里新增校验方法，无需修改核心路由逻辑。
    """
    @classmethod
    def validate(cls, question, val, text, q_name):
        is_empty = (val is None or val == "" or (isinstance(val, list) and len(val) == 0))
        
        # 1. 必填项通用校验
        if question.get('is_required') and is_empty:
            return False, f'{q_name} 是必填项'
            
        if is_empty:
            return True, "" # 非必填且为空，直接放行

        # 2. 根据题型路由到对应的校验逻辑
        validator_method = getattr(cls, f"_validate_{question['type']}", None)
        if validator_method:
            return validator_method(question, val, q_name)
        
        return True, "" # 未知题型默认放行或可配置为报错

    @staticmethod
    def _validate_multiple_choice(question, val, q_name):
        if not isinstance(val, list):
            return False, f'{q_name} 数据格式错误'
        min_c = question.get('min_choices')
        max_c = question.get('max_choices')
        if min_c is not None and len(val) < min_c:
            return False, f'{q_name} 最少需要选择 {min_c} 项'
        if max_c is not None and len(val) > max_c:
            return False, f'{q_name} 最多只能选择 {max_c} 项'
        return True, ""

    @staticmethod
    def _validate_text(question, val, q_name):
        content_len = len(str(val))
        min_l = question.get('min_length')
        max_l = question.get('max_length')
        if min_l is not None and content_len < min_l:
            return False, f'{q_name} 长度不能少于 {min_l}'
        if max_l is not None and content_len > max_l:
            return False, f'{q_name} 长度不能超过 {max_l}'
        return True, ""

    @staticmethod
    def _validate_number(question, val, q_name):
        try:
            num = float(val)
        except (ValueError, TypeError):
            return False, f'{q_name} 必须是数字'
        
        if question.get('is_integer') and not num.is_integer():
            return False, f'{q_name} 必须是整数'
            
        min_v = question.get('min_value')
        max_v = question.get('max_value')
        if min_v is not None and num < min_v:
            return False, f'{q_name} 不能小于 {min_v}'
        if max_v is not None and num > max_v:
            return False, f'{q_name} 不能大于 {max_v}'
        return True, ""


# ==========================================
# 5. 路由控制器
# ==========================================

@app.route('/')
def index():
    return send_from_directory('static', 'index.html')

@app.route('/static/<path:filename>')
def serve_static(filename):
    return send_from_directory('static', filename)

@app.route('/api/register', methods=['POST'])
def register():
    data = request.get_json()
    username, password, email = data.get('username'), data.get('password'), data.get('email')
    
    if not username or not password:
        logger.warning('注册失败：用户名或密码为空')
        return jsonify({'error': '用户名和密码不能为空'}), 400
    
    if users_collection.find_one({'username': username}):
        return jsonify({'error': '用户名已存在'}), 400
    
    user_id = users_collection.insert_one({
        'username': username,
        'password': Utils.hash_password(password),
        'email': email,
        'created_at': datetime.datetime.now(),
        'created_surveys': [],
        'submitted_answers': []
    }).inserted_id
    
    logger.info(f'新用户注册成功：{username}, ID: {user_id}')
    return jsonify({'message': '注册成功', 'user_id': str(user_id)}), 201

@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    username, password = data.get('username'), data.get('password')
    
    if not username or not password:
        return jsonify({'error': '用户名和密码不能为空'}), 400
    
    user = users_collection.find_one({'username': username})
    if not user or not Utils.check_password(password, user['password']):
        return jsonify({'error': '用户名或密码错误'}), 401
    
    session['user_id'] = str(user['_id'])
    session['username'] = user['username']
    return jsonify({'message': '登录成功', 'user_id': str(user['_id']), 'username': user['username']}), 200

@app.route('/api/logout', methods=['POST'])
def logout():
    username = session.pop('username', None)
    session.clear()
    logger.info(f'用户已登出：{username}' if username else '登出操作：当前并无用户登录')
    return jsonify({'message': '已登出'}), 200

@app.route('/api/me', methods=['GET'])
@login_required
def get_me():
    return jsonify({'user_id': session['user_id'], 'username': session['username']}), 200

@app.route('/api/my_surveys', methods=['GET'])
@login_required
def get_my_surveys():
    surveys = list(surveys_collection.find({'user_id': ObjectId(session['user_id'])}))
    return jsonify(surveys), 200

@app.route('/api/surveys/<survey_id>', methods=['GET'])
@login_required
@survey_owner_required
def get_survey_details(survey_id, survey):
    # 得益于自定义的 MongoJSONProvider，这里无需再手动遍历转换 ObjectId 和 Datetime
    questions = list(questions_collection.find({'survey_id': ObjectId(survey_id)}).sort('order', 1))
    return jsonify({'survey': survey, 'questions': questions}), 200

@app.route('/api/surveys', methods=['POST'])
@login_required
def create_survey():
    data = request.get_json()
    title = data.get('title')
    
    if not title:
        return jsonify({'error': '问卷标题不能为空'}), 400
        
    expire_at = None
    if data.get('expire_at'):
        try:
            expire_at = datetime.datetime.fromisoformat(data.get('expire_at').replace('Z', '+00:00'))
        except ValueError:
            logger.warning('创建问卷提示：截止时间格式解析失败')

    survey = {
        'user_id': ObjectId(session['user_id']),
        'title': title,
        'description': data.get('description'),
        'is_anonymous': data.get('is_anonymous', False),
        'allow_multiple_submissions': data.get('allow_multiple_submissions', False),
        'status': 'draft',
        'created_at': datetime.datetime.now(),
        'published_at': None,
        'expire_at': expire_at,
        'slug': Utils.generate_slug(),
        'question_count': 0,
        'submission_count': 0
    }
    
    survey_id = surveys_collection.insert_one(survey).inserted_id
    users_collection.update_one({'_id': ObjectId(session['user_id'])}, {'$push': {'created_surveys': survey_id}})
    
    return jsonify({'message': '问卷创建成功', 'survey_id': str(survey_id), 'slug': survey['slug']}), 201

@app.route('/api/surveys/<survey_id>/questions', methods=['POST'])
@login_required
@survey_owner_required
def add_question(survey_id, survey):
    data = request.get_json()
    question_type = data.get('type')
    if not question_type or not data.get('content'):
        return jsonify({'error': '问题类型和内容不能为空'}), 400
    
    if question_type in ['single_choice', 'multiple_choice']:
        options = data.get('options', [])
        # 确保 options 是个列表，且至少包含一个有效选项
        if not isinstance(options, list) or len(options) == 0:
            return jsonify({'error': '选择题必须至少设置一个选项'}), 400
    max_order = questions_collection.count_documents({'survey_id': ObjectId(survey_id)})
    
    question = {
        'survey_id': ObjectId(survey_id),
        'order': max_order + 1,
        **{k: v for k, v in data.items() if k in [
            'type', 'content', 'is_required', 'options', 'min_choices', 
            'max_choices', 'min_length', 'max_length', 'min_value', 
            'max_value', 'is_integer', 'jumps'
        ]}
    }
    # 设置默认值以防前端遗漏
    question.setdefault('is_required', False)
    question.setdefault('options', [])
    question.setdefault('jumps', [])
    
    question_id = questions_collection.insert_one(question).inserted_id
    surveys_collection.update_one({'_id': ObjectId(survey_id)}, {'$inc': {'question_count': 1}})
    
    return jsonify({'message': '问题添加成功', 'question_id': str(question_id)}), 201

@app.route('/api/surveys/<survey_id>/publish', methods=['POST'])
@login_required
@survey_owner_required
def publish_survey(survey_id, survey):
    surveys_collection.update_one(
        {'_id': ObjectId(survey_id)},
        {'$set': {'status': 'published', 'published_at': datetime.datetime.now()}}
    )
    return jsonify({'message': '问卷发布成功'}), 200

@app.route('/api/surveys/<survey_id>/close', methods=['POST'])
@login_required
@survey_owner_required
def close_survey(survey_id, survey):
    surveys_collection.update_one(
        {'_id': ObjectId(survey_id)},
        {'$set': {'status': 'closed'}}
    )
    return jsonify({'message': '问卷已关闭'}), 200

@app.route('/api/questions/<question_id>', methods=['PUT'])
@login_required
def update_question(question_id):
    question = questions_collection.find_one({'_id': ObjectId(question_id)})
    if not question:
        return jsonify({'error': '题目不存在'}), 404
    
    survey = surveys_collection.find_one({'_id': question['survey_id']})
    if str(survey['user_id']) != session['user_id']:
        return jsonify({'error': '无权操作此问卷'}), 403
    
    data = request.get_json()
    update_data = {}
    question_type = data.get('type')
    if not question_type or not data.get('content'):
        return jsonify({'error': '问题类型和内容不能为空'}), 400
    
    if question_type in ['single_choice', 'multiple_choice']:
        options = data.get('options', [])
        # 确保 options 是个列表，且至少包含一个有效选项
        if not isinstance(options, list) or len(options) == 0:
            return jsonify({'error': '选择题必须至少设置一个选项'}), 400
    if 'jumps' in data:
        jumps = data['jumps']
        for jump in jumps:
            if jump.get('target_question_id'):
                jump['target_question_id'] = ObjectId(jump['target_question_id'])
            for cond in jump.get('conditions', []):
                if cond.get('question_id'):
                    cond['question_id'] = ObjectId(cond['question_id'])
        update_data['jumps'] = jumps
    
    if 'content' in data: update_data['content'] = data['content']

    questions_collection.update_one({'_id': ObjectId(question_id)}, {'$set': update_data})
    return jsonify({'message': '题目更新成功'}), 200

@app.route('/api/fill_survey/<slug>', methods=['GET'])
def get_survey_for_fill(slug):
    survey = surveys_collection.find_one({'slug': slug})
    if not survey: return jsonify({'error': '问卷不存在'}), 404
    if survey['status'] != 'published': return jsonify({'error': '问卷尚未发布或已关闭'}), 400
    if survey.get('expire_at') and datetime.datetime.now() > survey['expire_at']:
        return jsonify({'error': '问卷已过期'}), 400
    
    # 同样得益于 MongoJSONProvider，去掉了大段的嵌套 ObjectId 转换逻辑
    questions = list(questions_collection.find({'survey_id': survey['_id']}).sort('order', 1))
    return jsonify({'survey': survey, 'questions': questions}), 200

@app.route('/api/surveys/<slug>/submit', methods=['POST'])
def submit_survey(slug):
    survey = surveys_collection.find_one({'slug': slug})
    if not survey or survey['status'] != 'published':
        return jsonify({'error': '问卷不存在或未发布'}), 404 if not survey else 400
    
    if survey.get('expire_at') and datetime.datetime.now() > survey['expire_at']:
        return jsonify({'error': '问卷已过期'}), 400
    
    if not survey['allow_multiple_submissions'] and 'user_id' in session:
        if answers_collection.find_one({'survey_id': survey['_id'], 'user_id': ObjectId(session['user_id'])}):
            return jsonify({'error': '您已经填写过此问卷'}), 400
    
    data = request.get_json()
    responses = data.get('responses', [])
    questions_dict = {str(q['_id']): q for q in questions_collection.find({'survey_id': survey['_id']})}
    
    processed_responses = []
    for resp in responses:
        q_id_str = resp.get('question_id')
        if q_id_str not in questions_dict:
            return jsonify({'error': f'无效的问题ID: {q_id_str}'}), 400
            
        question = questions_dict[q_id_str]
        val, text = resp.get('value'), resp.get('text')
        q_name = f"第 {question['order']} 题 '{question['content']}'"

        # 调用提取出的策略校验模块
        is_valid, error_msg = QuestionValidator.validate(question, val, text, q_name)
        if not is_valid:
            logger.warning(f'业务校验未通过：{error_msg}')
            return jsonify({'error': error_msg}), 400

        processed_responses.append({
            'question_id': ObjectId(q_id_str),
            'value': val,
            'text': text
        })
    
    answer = {
        'survey_id': survey['_id'],
        'user_id': ObjectId(session['user_id']) if 'user_id' in session and not survey['is_anonymous'] else None,
        'created_at': datetime.datetime.now(),
        'responses': processed_responses
    }
    answers_collection.insert_one(answer)
    surveys_collection.update_one({'_id': survey['_id']}, {'$inc': {'submission_count': 1}})
    
    if answer['user_id']:
        users_collection.update_one({'_id': answer['user_id']}, {'$push': {'submitted_answers': answer['_id']}})
    
    return jsonify({'message': '问卷提交成功'}), 201

@app.route('/api/surveys/<survey_id>/statistics', methods=['GET'])
@login_required
@survey_owner_required
def get_statistics(survey_id, survey):
    questions = list(questions_collection.find({'survey_id': ObjectId(survey_id)}).sort('order'))
    answers = list(answers_collection.find({'survey_id': ObjectId(survey_id)}))
    
    statistics = {}
    for question in questions:
        q_id_str = str(question['_id'])
        statistics[q_id_str] = {
            'content': question['content'],
            'type': question['type'],
            'total_responses': 0,
            'results': {}
        }
        
        # 统计逻辑暂时保留，但由于使用了 q_id_str 作为键，结构更加清晰
        # 未来二阶段如果需要扩展图表类型，可以抽出一个 StatisticsBuilder 类
        options = {option['value']: 0 for option in question.get('options', [])}
        values, text_responses = [], []
        
        for answer in answers:
            for response in answer['responses']:
                if response['question_id'] == question['_id']:
                    statistics[q_id_str]['total_responses'] += 1
                    val = response.get('value')
                    
                    if question['type'] in ['single_choice', 'multiple_choice']:
                        val_list = val if isinstance(val, list) else [val]
                        for v in val_list:
                            v_str = str(v)
                            options[v_str] = options.get(v_str, 0) + 1
                    elif question['type'] == 'text':
                        text_responses.append(response.get('text') or val)
                    elif question['type'] == 'number':
                        try:
                            values.append(float(val))
                        except:
                            pass
                            
        if question['type'] in ['single_choice', 'multiple_choice']:
            statistics[q_id_str]['results'] = options
        elif question['type'] == 'text':
            statistics[q_id_str]['results'] = text_responses
        elif question['type'] == 'number':
            statistics[q_id_str]['results'] = {
                'values': values,
                'average': round(sum(values) / len(values), 2) if values else 0
            }
            
    return jsonify({'statistics': statistics}), 200

@app.errorhandler(Exception)
def handle_exception(e):
    if isinstance(e, HTTPException):
        return e
    logger.error(f'系统发生未捕获异常：{str(e)}', exc_info=True)
    return jsonify({'error': '服务器内部错误'}), 500

if __name__ == '__main__':
    os.makedirs('static', exist_ok=True)
    app.run(debug=True, port=5000)