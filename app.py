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
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'your_secret_key')
MONGO_URI = os.getenv('MONGO_URI', 'mongodb://localhost:27017/')

client = MongoClient(MONGO_URI)
db = client['survey_system']

users_collection = db['users']
surveys_collection = db['surveys']
questions_collection = db['questions']
answers_collection = db['answers']
question_banks_collection = db['question_banks'] # 【二阶段新增】题库集合

# ==========================================
# 2. 核心扩展：自定义 JSON 编码器
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
# 3. 装饰器与中间件
# ==========================================
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': '请先登录'}), 401
        return f(*args, **kwargs)
    return decorated_function

def survey_owner_required(f):
    @wraps(f)
    def decorated_function(survey_id, *args, **kwargs):
        survey = surveys_collection.find_one({'_id': ObjectId(survey_id)})
        if not survey:
            return jsonify({'error': '问卷不存在'}), 404
        if str(survey['user_id']) != session['user_id']:
            logger.warning(f'越权操作警告：用户 {session.get("username")} 尝试操作问卷 {survey_id}')
            return jsonify({'error': '无权操作此问卷'}), 403
        return f(survey_id, survey=survey, *args, **kwargs)
    return decorated_function

# ==========================================
# 4. 辅助工具类
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

    # 【二阶段新增】工具方法：将分离的问卷上下文与题目实体合并（保持向下兼容）
    @staticmethod
    def merge_survey_questions(survey):
        survey_questions = survey.get('questions', [])
        question_ids = [sq['question_id'] for sq in survey_questions]
        questions_data = {str(q['_id']): q for q in questions_collection.find({'_id': {'$in': question_ids}})}
        
        merged_questions = []
        for sq in survey_questions:
            q_detail = questions_data.get(str(sq['question_id']))
            if q_detail:
                # 合并字典：以题目实体为底，用问卷上下文（order, is_required, jumps）覆盖
                merged = {**q_detail, **sq} 
                # 前端可能还需要旧版的 id 字段
                merged['_id'] = sq['question_id'] 
                merged_questions.append(merged)
        
        merged_questions.sort(key=lambda x: x.get('order', 0))
        return merged_questions

class QuestionValidator:
    # 保持原样，无需修改
    @classmethod
    def validate(cls, question, val, text, q_name):
        is_empty = (val is None or val == "" or (isinstance(val, list) and len(val) == 0))
        if question.get('is_required') and is_empty: return False, f'{q_name} 是必填项'
        if is_empty: return True, ""
        validator_method = getattr(cls, f"_validate_{question.get('type')}", None)
        if validator_method: return validator_method(question, val, q_name)
        return True, ""

    @staticmethod
    def _validate_multiple_choice(question, val, q_name):
        if not isinstance(val, list): return False, f'{q_name} 数据格式错误'
        min_c = question.get('min_choices')
        max_c = question.get('max_choices')
        if min_c is not None and len(val) < min_c: return False, f'{q_name} 最少需要选择 {min_c} 项'
        if max_c is not None and len(val) > max_c: return False, f'{q_name} 最多只能选择 {max_c} 项'
        return True, ""

    @staticmethod
    def _validate_text(question, val, q_name):
        content_len = len(str(val))
        min_l = question.get('min_length')
        max_l = question.get('max_length')
        if min_l is not None and content_len < min_l: return False, f'{q_name} 长度不能少于 {min_l}'
        if max_l is not None and content_len > max_l: return False, f'{q_name} 长度不能超过 {max_l}'
        return True, ""

    @staticmethod
    def _validate_number(question, val, q_name):
        try: num = float(val)
        except (ValueError, TypeError): return False, f'{q_name} 必须是数字'
        if question.get('is_integer') and not num.is_integer(): return False, f'{q_name} 必须是整数'
        min_v = question.get('min_value')
        max_v = question.get('max_value')
        if min_v is not None and num < min_v: return False, f'{q_name} 不能小于 {min_v}'
        if max_v is not None and num > max_v: return False, f'{q_name} 不能大于 {max_v}'
        return True, ""


# ==========================================
# 5. 路由控制器
# ==========================================

@app.route('/api/register', methods=['POST'])
def register():
    data = request.get_json()
    username, password, email = data.get('username'), data.get('password'), data.get('email')
    if not username or not password: return jsonify({'error': '用户名和密码不能为空'}), 400
    if users_collection.find_one({'username': username}): return jsonify({'error': '用户名已存在'}), 400
    
    user_id = users_collection.insert_one({
        'username': username,
        'password': Utils.hash_password(password),
        'email': email,
        'created_at': datetime.datetime.now(),
        'created_surveys': [],
        'submitted_answers': [],
        'question_banks': [] # 【二阶段新增】
    }).inserted_id
    return jsonify({'message': '注册成功', 'user_id': str(user_id)}), 201

@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    user = users_collection.find_one({'username': data.get('username')})
    if not user or not Utils.check_password(data.get('password'), user['password']):
        return jsonify({'error': '用户名或密码错误'}), 401
    session['user_id'] = str(user['_id'])
    session['username'] = user['username']
    return jsonify({'message': '登录成功', 'user_id': str(user['_id']), 'username': user['username']}), 200

@app.route('/api/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'message': '已登出'}), 200

@app.route('/api/my_surveys', methods=['GET'])
@login_required
def get_my_surveys():
    surveys = list(surveys_collection.find({'user_id': ObjectId(session['user_id'])}))
    return jsonify(surveys), 200

@app.route('/api/surveys/<survey_id>', methods=['GET'])
@login_required
@survey_owner_required
def get_survey_details(survey_id, survey):
    # 【二阶段修改】使用合并工具返回数据，前端无需改动代码即可渲染
    merged_questions = Utils.merge_survey_questions(survey)
    return jsonify({'survey': survey, 'questions': merged_questions}), 200

@app.route('/api/surveys', methods=['POST'])
@login_required
def create_survey():
    data = request.get_json()
    if not data.get('title'): return jsonify({'error': '问卷标题不能为空'}), 400
        
    expire_at = None
    if data.get('expire_at'):
        try: expire_at = datetime.datetime.fromisoformat(data.get('expire_at').replace('Z', '+00:00'))
        except ValueError: pass

    survey = {
        'user_id': ObjectId(session['user_id']),
        'title': data.get('title'),
        'description': data.get('description'),
        'is_anonymous': data.get('is_anonymous', False),
        'allow_multiple_submissions': data.get('allow_multiple_submissions', False),
        'status': 'draft',
        'created_at': datetime.datetime.now(),
        'published_at': None,
        'expire_at': expire_at,
        'slug': Utils.generate_slug(),
        'questions': [], # 【二阶段修改】显式维护包含的问题及上下文
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
    if not data.get('type') or not data.get('content'): return jsonify({'error': '问题类型和内容不能为空'}), 400
    
    # 【二阶段重构】解耦题目本体与问卷上下文
    new_q_id = ObjectId()
    
    # 1. 创建独立的问题文档
    question_doc = {
        '_id': new_q_id,
        'base_question_id': new_q_id, # 新建题目基础ID就是自己
        'version': 1,
        'previous_version_id': None,
        'owner_id': ObjectId(session['user_id']),
        'is_public': False,
        'shared_with_users': [],
        'used_in_surveys': [ObjectId(survey_id)], # 记录被当前问卷使用
        
        # 题干属性
        'type': data.get('type'),
        'content': data.get('content'),
        'options': data.get('options', []),
        'min_choices': data.get('min_choices'),
        'max_choices': data.get('max_choices'),
        'min_length': data.get('min_length'),
        'max_length': data.get('max_length'),
        'min_value': data.get('min_value'),
        'max_value': data.get('max_value'),
        'is_integer': data.get('is_integer')
    }
    questions_collection.insert_one(question_doc)
    
    # 2. 在问卷中保存上下文信息
    survey_question_context = {
        'question_id': new_q_id,
        'order': len(survey.get('questions', [])) + 1,
        'is_required': data.get('is_required', False),
        'jumps': data.get('jumps', [])
    }
    
    surveys_collection.update_one(
        {'_id': ObjectId(survey_id)}, 
        {'$push': {'questions': survey_question_context}, '$inc': {'question_count': 1}}
    )
    
    return jsonify({'message': '问题添加成功', 'question_id': str(new_q_id)}), 201

@app.route('/api/questions/<question_id>', methods=['PUT'])
@login_required
def update_question(question_id):
    # 【二阶段重构】引入写时复制（Copy-on-Write）版本控制
    data = request.get_json()
    survey_id_str = data.get('survey_id') # 前端修改时必须传入当前所在的 survey_id
    if not survey_id_str:
        return jsonify({'error': '缺少 survey_id 参数'}), 400
        
    question = questions_collection.find_one({'_id': ObjectId(question_id)})
    if not question: return jsonify({'error': '题目不存在'}), 404
    
    # 鉴权
    survey = surveys_collection.find_one({'_id': ObjectId(survey_id_str)})
    if not survey or str(survey['user_id']) != session['user_id']:
        return jsonify({'error': '无权操作'}), 403

    # ================= 分发更新 =================
    # 1. 更新上下文属性（is_required, jumps）只影响当前问卷，直接在 surveys 表更新
    update_survey_context = {}
    if 'is_required' in data: update_survey_context['questions.$.is_required'] = data['is_required']
    if 'jumps' in data:
        jumps = data['jumps']
        for jump in jumps:
            if jump.get('target_question_id'): jump['target_question_id'] = ObjectId(jump['target_question_id'])
            for cond in jump.get('conditions', []):
                if cond.get('question_id'): cond['question_id'] = ObjectId(cond['question_id'])
        update_survey_context['questions.$.jumps'] = jumps
        
    if update_survey_context:
        surveys_collection.update_one(
            {'_id': ObjectId(survey_id_str), 'questions.question_id': ObjectId(question_id)},
            {'$set': update_survey_context}
        )

    # 2. 检查是否修改了题干核心内容 (content, options 等)
    core_fields_updated = any(k in data for k in ['content', 'options', 'type', 'min_choices', 'max_choices'])
    
    if core_fields_updated:
        # 核心逻辑：如果此题被其他问卷使用（或者当前问卷已发布），触发版本分裂
        if len(question.get('used_in_surveys', [])) > 1 or survey['status'] != 'draft':
            new_q_id = ObjectId()
            new_question = question.copy()
            new_question['_id'] = new_q_id
            new_question['version'] = question.get('version', 1) + 1
            new_question['previous_version_id'] = question['_id']
            new_question['used_in_surveys'] = [ObjectId(survey_id_str)] # 新版本只被当前问卷使用
            
            # 应用修改
            if 'content' in data: new_question['content'] = data['content']
            if 'options' in data: new_question['options'] = data['options']
            
            questions_collection.insert_one(new_question)
            
            # 从老版本的 used_in_surveys 中移除当前问卷
            questions_collection.update_one(
                {'_id': question['_id']}, 
                {'$pull': {'used_in_surveys': ObjectId(survey_id_str)}}
            )
            # 更新当前问卷，使其指向新版本的题目
            surveys_collection.update_one(
                {'_id': ObjectId(survey_id_str), 'questions.question_id': ObjectId(question_id)},
                {'$set': {'questions.$.question_id': new_q_id}}
            )
        else:
            # 没有被复用，直接原位更新题目集合
            update_q_data = {}
            if 'content' in data: update_q_data['content'] = data['content']
            if 'options' in data: update_q_data['options'] = data['options']
            questions_collection.update_one({'_id': ObjectId(question_id)}, {'$set': update_q_data})

    return jsonify({'message': '题目更新成功'}), 200

# 【二阶段新增】从题库/历史复用题目
@app.route('/api/surveys/<survey_id>/reuse_question', methods=['POST'])
@login_required
@survey_owner_required
def reuse_question(survey_id, survey):
    data = request.get_json()
    source_q_id = data.get('question_id')
    
    if not source_q_id: return jsonify({'error': '需提供要复用的题目ID'}), 400
    question = questions_collection.find_one({'_id': ObjectId(source_q_id)})
    if not question: return jsonify({'error': '原题目不存在'}), 404
    
    # 建立关联
    questions_collection.update_one({'_id': question['_id']}, {'$addToSet': {'used_in_surveys': ObjectId(survey_id)}})
    
    survey_question_context = {
        'question_id': question['_id'],
        'order': len(survey.get('questions', [])) + 1,
        'is_required': False,
        'jumps': []
    }
    surveys_collection.update_one(
        {'_id': ObjectId(survey_id)}, 
        {'$push': {'questions': survey_question_context}, '$inc': {'question_count': 1}}
    )
    return jsonify({'message': '题目复用成功', 'question_id': str(question['_id'])}), 200

@app.route('/api/surveys/<survey_id>/publish', methods=['POST'])
@login_required
@survey_owner_required
def publish_survey(survey_id, survey):
    surveys_collection.update_one({'_id': ObjectId(survey_id)},{'$set': {'status': 'published', 'published_at': datetime.datetime.now()}})
    return jsonify({'message': '问卷发布成功'}), 200

@app.route('/api/surveys/<survey_id>/close', methods=['POST'])
@login_required
@survey_owner_required
def close_survey(survey_id, survey):
    surveys_collection.update_one({'_id': ObjectId(survey_id)},{'$set': {'status': 'closed'}})
    return jsonify({'message': '问卷已关闭'}), 200

@app.route('/api/fill_survey/<slug>', methods=['GET'])
def get_survey_for_fill(slug):
    survey = surveys_collection.find_one({'slug': slug})
    if not survey: return jsonify({'error': '问卷不存在'}), 404
    if survey['status'] != 'published': return jsonify({'error': '问卷尚未发布或已关闭'}), 400
    if survey.get('expire_at') and datetime.datetime.now() > survey['expire_at']: return jsonify({'error': '问卷已过期'}), 400
    
    # 【二阶段修改】
    merged_questions = Utils.merge_survey_questions(survey)
    return jsonify({'survey': survey, 'questions': merged_questions}), 200

@app.route('/api/surveys/<slug>/submit', methods=['POST'])
def submit_survey(slug):
    survey = surveys_collection.find_one({'slug': slug})
    if not survey or survey['status'] != 'published': return jsonify({'error': '问卷不存在或未发布'}), 404 if not survey else 400
    if survey.get('expire_at') and datetime.datetime.now() > survey['expire_at']: return jsonify({'error': '问卷已过期'}), 400
    if not survey['allow_multiple_submissions'] and 'user_id' in session:
        if answers_collection.find_one({'survey_id': survey['_id'], 'user_id': ObjectId(session['user_id'])}):
            return jsonify({'error': '您已经填写过此问卷'}), 400
    
    data = request.get_json()
    responses = data.get('responses', [])
    
    # 拿到合并后的完整问题结构用于校验
    merged_questions = Utils.merge_survey_questions(survey)
    questions_dict = {str(q['_id']): q for q in merged_questions}
    
    processed_responses = []
    for resp in responses:
        q_id_str = resp.get('question_id')
        if q_id_str not in questions_dict: return jsonify({'error': f'无效的问题ID: {q_id_str}'}), 400
            
        question = questions_dict[q_id_str]
        val, text = resp.get('value'), resp.get('text')
        q_name = f"第 {question['order']} 题 '{question['content']}'"

        is_valid, error_msg = QuestionValidator.validate(question, val, text, q_name)
        if not is_valid: return jsonify({'error': error_msg}), 400

        processed_responses.append({
            'question_id': ObjectId(q_id_str),
            'base_question_id': question.get('base_question_id'), # 【二阶段修改】记录 base_id 用于跨问卷统计
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
    if answer['user_id']: users_collection.update_one({'_id': answer['user_id']}, {'$push': {'submitted_answers': answer['_id']}})
    
    return jsonify({'message': '问卷提交成功'}), 201

@app.route('/api/surveys/<survey_id>/statistics', methods=['GET'])
@login_required
@survey_owner_required
def get_statistics(survey_id, survey):
    # 【二阶段修改】基于合并后的数据进行统计
    merged_questions = Utils.merge_survey_questions(survey)
    answers = list(answers_collection.find({'survey_id': ObjectId(survey_id)}))
    
    statistics = {}
    for question in merged_questions:
        q_id_str = str(question['_id'])
        statistics[q_id_str] = {
            'content': question['content'],
            'type': question['type'],
            'total_responses': 0,
            'results': {}
        }
        
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
                        try: values.append(float(val))
                        except: pass
                            
        if question['type'] in ['single_choice', 'multiple_choice']: statistics[q_id_str]['results'] = options
        elif question['type'] == 'text': statistics[q_id_str]['results'] = text_responses
        elif question['type'] == 'number':
            statistics[q_id_str]['results'] = {'values': values, 'average': round(sum(values) / len(values), 2) if values else 0}
            
    return jsonify({'statistics': statistics}), 200

@app.errorhandler(Exception)
def handle_exception(e):
    if isinstance(e, HTTPException): return e
    logger.error(f'系统发生未捕获异常：{str(e)}', exc_info=True)
    return jsonify({'error': '服务器内部错误'}), 500

if __name__ == '__main__':
    os.makedirs('static', exist_ok=True)
    app.run(debug=True, port=5000)