#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import requests
import random
import string
import json
from datetime import datetime

# API基础URL
BASE_URL = 'http://localhost:5000'

class SurveyAPITest:
    def __init__(self):
        self.session = requests.Session()
        self.test_username = None
        self.test_password = None
        self.survey_id = None
        self.survey_slug = None
        self.question_ids = []
    
    def generate_random_string(self, length=8):
        """生成随机字符串"""
        return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))
    
    def register_and_login(self):
        """注册测试账号并登录"""
        print("\n=== 第一步：注册测试账号并登录 ===")
        
        # 生成随机用户名
        self.test_username = f"test_{self.generate_random_string()}"
        self.test_password = "password123"
        
        # 注册
        register_data = {
            'username': self.test_username,
            'password': self.test_password,
            'email': f"{self.test_username}@example.com"
        }
        
        response = self.session.post(f'{BASE_URL}/api/register', json=register_data)
        print(f"注册状态码: {response.status_code}")
        print(f"注册响应: {response.json()}")
        
        # 登录
        login_data = {
            'username': self.test_username,
            'password': self.test_password
        }
        
        response = self.session.post(f'{BASE_URL}/api/login', json=login_data)
        print(f"登录状态码: {response.status_code}")
        print(f"登录响应: {response.json()}")
        
        if response.status_code == 200:
            print("✓ 注册和登录成功")
            return True
        else:
            print("✗ 注册或登录失败")
            return False
    
    def create_survey(self):
        """创建新问卷"""
        print("\n=== 第二步：创建新问卷 ===")
        
        survey_data = {
            'title': f"测试问卷_{self.generate_random_string()}",
            'description': "这是一个自动化测试问卷",
            'is_anonymous': False,
            'allow_multiple_submissions': True
        }
        
        response = self.session.post(f'{BASE_URL}/api/surveys', json=survey_data)
        print(f"创建问卷状态码: {response.status_code}")
        print(f"创建问卷响应: {response.json()}")
        
        if response.status_code == 201:
            data = response.json()
            self.survey_id = data.get('survey_id')
            self.survey_slug = data.get('slug')
            print(f"✓ 问卷创建成功，ID: {self.survey_id}, Slug: {self.survey_slug}")
            return True
        else:
            print("✗ 问卷创建失败")
            return False
    
    def add_questions(self):
        """添加题目"""
        print("\n=== 第三步：添加题目 ===")
        
        # 添加单选题
        single_choice_data = {
            'type': 'single_choice',
            'content': '你最喜欢的颜色是什么？',
            'is_required': True,
            'options': [
                {'value': '1', 'text': '红色'},
                {'value': '2', 'text': '蓝色'},
                {'value': '3', 'text': '绿色'},
                {'value': '4', 'text': '黄色'}
            ]
        }
        
        response = self.session.post(f'{BASE_URL}/api/surveys/{self.survey_id}/questions', json=single_choice_data)
        print(f"添加单选题状态码: {response.status_code}")
        print(f"添加单选题响应: {response.json()}")
        if response.status_code == 201:
            self.question_ids.append(response.json().get('question_id'))
        
        # 添加多选题（带最少/最多选择限制）
        multiple_choice_data = {
            'type': 'multiple_choice',
            'content': '你喜欢哪些运动？（至少选1项，最多选3项）',
            'is_required': True,
            'min_choices': 1,
            'max_choices': 3,
            'options': [
                {'value': '1', 'text': '篮球'},
                {'value': '2', 'text': '足球'},
                {'value': '3', 'text': '游泳'},
                {'value': '4', 'text': '跑步'},
                {'value': '5', 'text': '健身'}
            ]
        }
        
        response = self.session.post(f'{BASE_URL}/api/surveys/{self.survey_id}/questions', json=multiple_choice_data)
        print(f"添加多选题状态码: {response.status_code}")
        print(f"添加多选题响应: {response.json()}")
        if response.status_code == 201:
            self.question_ids.append(response.json().get('question_id'))
        
        # 添加数字题（带数值范围限制）
        number_data = {
            'type': 'number',
            'content': '请输入你的年龄（18-60岁）',
            'is_required': True,
            'min_value': 18,
            'max_value': 60,
            'is_integer': True
        }
        
        response = self.session.post(f'{BASE_URL}/api/surveys/{self.survey_id}/questions', json=number_data)
        print(f"添加数字题状态码: {response.status_code}")
        print(f"添加数字题响应: {response.json()}")
        if response.status_code == 201:
            self.question_ids.append(response.json().get('question_id'))
        
        print(f"✓ 已添加 {len(self.question_ids)} 道题目")
        return len(self.question_ids) >= 3
    
    def publish_survey(self):
        """发布问卷"""
        print("\n=== 第四步：发布问卷 ===")
        
        response = self.session.post(f'{BASE_URL}/api/surveys/{self.survey_id}/publish')
        print(f"发布问卷状态码: {response.status_code}")
        print(f"发布问卷响应: {response.json()}")
        
        if response.status_code == 200:
            print("✓ 问卷发布成功")
            return True
        else:
            print("✗ 问卷发布失败")
            return False
    
    def batch_submit_survey(self, count=10):
        """批量提交问卷"""
        print(f"\n=== 第五步：批量提交问卷（{count}次）===")
        
        for i in range(count):
            print(f"\n提交第 {i+1} 次")
            
            # 生成随机但符合限制的答案
            responses = [
                # 单选题：随机选择一个选项
                {
                    'question_id': self.question_ids[0],
                    'value': str(random.randint(1, 4))
                },
                # 多选题：随机选择1-3个选项
                {
                    'question_id': self.question_ids[1],
                    'value': random.sample(['1', '2', '3', '4', '5'], random.randint(1, 3))
                },
                # 数字题：随机选择18-60之间的整数
                {
                    'question_id': self.question_ids[2],
                    'value': random.randint(18, 60)
                }
            ]
            
            submit_data = {
                'responses': responses
            }
            
            response = self.session.post(f'{BASE_URL}/api/surveys/{self.survey_slug}/submit', json=submit_data)
            print(f"提交状态码: {response.status_code}")
            print(f"提交响应: {response.json()}")
            
            if response.status_code != 201:
                print(f"✗ 第 {i+1} 次提交失败")
                return False
        
        print(f"✓ 成功提交 {count} 次问卷")
        return True
    
    def test_invalid_submission(self):
        """测试不合法提交"""
        print("\n=== 第六步：测试不合法提交 ===")
        
        # 构造不合法的提交：必填题为空
        invalid_responses = [
            # 单选题：留空
            {
                'question_id': self.question_ids[0],
                'value': None
            },
            # 多选题：选择1个选项
            {
                'question_id': self.question_ids[1],
                'value': ['1']
            },
            # 数字题：超出范围
            {
                'question_id': self.question_ids[2],
                'value': 17  # 小于最小值18
            }
        ]
        
        submit_data = {
            'responses': invalid_responses
        }
        
        response = self.session.post(f'{BASE_URL}/api/surveys/{self.survey_slug}/submit', json=submit_data)
        print(f"不合法提交状态码: {response.status_code}")
        print(f"不合法提交响应: {response.json()}")
        
        if response.status_code == 400:
            print("✓ 成功拦截不合法提交")
            return True
        else:
            print("✗ 未能拦截不合法提交")
            return False
    
    def run_all_tests(self):
        """运行所有测试步骤"""
        print("开始执行API自动化测试")
        print("=" * 60)
        
        # 执行测试步骤
        steps = [
            ("注册和登录", self.register_and_login),
            ("创建问卷", self.create_survey),
            ("添加题目", self.add_questions),
            ("发布问卷", self.publish_survey),
            ("批量提交", self.batch_submit_survey),
            ("测试不合法提交", self.test_invalid_submission)
        ]
        
        all_passed = True
        for step_name, step_func in steps:
            if not step_func():
                all_passed = False
                print(f"\n❌ {step_name} 失败，测试中断")
                break
            print("-" * 60)
        
        if all_passed:
            print("\n🎉 所有测试步骤执行成功！")
        else:
            print("\n❌ 测试执行失败")

if __name__ == '__main__':
    test = SurveyAPITest()
    test.run_all_tests()
