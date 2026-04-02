import Alpine from 'https://cdn.jsdelivr.net/npm/alpinejs@3.13.3/dist/module.esm.js';
import { checkAuth, login, register, logout, getMySurveys, createSurvey, getSurveyDetail, publishSurvey, closeSurvey, addQuestion, updateQuestion, getFillSurvey, submitSurvey as apiSubmitSurvey, getSurveyStatistics } from './api.js';

function initApp() {
    return {
        // 状态管理
        currentUserId: null,
        currentSurveyId: null,
        currentFillSlug: null,
        currentQuestions: [],
        currentQuestionIndex: 0,
        allResponses: {},
        jumpSettingQId: null,
        user: null,
        surveys: [],
        currentSurvey: null,
        currentSurveyQuestions: [],
        surveyStatistics: {},
        fillSurveyData: null,
        
        // 表单数据
        loginUsername: '',
        loginPassword: '',
        regUsername: '',
        regPassword: '',
        regEmail: '',
        surveyTitle: '',
        surveyDesc: '',
        surveyAnon: false,
        surveyMulti: false,
        surveyExpire: '',
        qType: 'single_choice',
        qContent: '',
        qOptions: '',
        minChoices: '',
        maxChoices: '',
        minLength: '',
        maxLength: '',
        minValue: '',
        maxValue: '',
        isInteger: false,
        qRequired: false,
        jumpCondition: 'equals',
        jumpValue: '',
        jumpTarget: 'null',
        
        // 视图状态
        currentTab: 'my-surveys',
        showJumpModal: false,
        
        // 初始化
        async init() {
            const urlParams = new URLSearchParams(window.location.search);
            const slug = urlParams.get('slug');
            if (slug) {
                await this.loadFillSurvey(slug);
            } else {
                await this.checkAuthStatus();
                await this.loadMySurveys();
            }
        },
        
        // 认证相关
        async checkAuthStatus() {
            const user = await checkAuth();
            if (user) {
                this.user = user;
                this.currentUserId = user.user_id;
            }
        },
        
        async login() {
            await login(this.loginUsername, this.loginPassword);
            await this.checkAuthStatus();
            await this.loadMySurveys();
            this.currentTab = 'my-surveys';
        },
        
        async register() {
            await register(this.regUsername, this.regPassword, this.regEmail);
            alert('注册成功，请登录');
            this.currentTab = 'login';
        },
        
        async logout() {
            await logout();
            location.href = '/';
        },
        
        // 问卷管理
        async loadMySurveys() {
            if (!this.currentUserId) {
                this.surveys = [];
                return;
            }
            this.surveys = await getMySurveys();
        },
        
        async createSurvey() {
            const res = await createSurvey(
                this.surveyTitle,
                this.surveyDesc,
                this.surveyAnon,
                this.surveyMulti,
                this.surveyExpire
            );
            await this.viewSurvey(res.survey_id);
        },
        
        async viewSurvey(id) {
            this.currentSurveyId = id;
            const data = await getSurveyDetail(id);
            this.currentSurvey = data.survey;
            this.currentSurveyQuestions = data.questions;
            this.currentTab = 'survey-detail';
        },
        
        async publishSurvey(id) {
            await publishSurvey(id);
            alert('发布成功！');
            await this.viewSurvey(id);
        },
        
        async closeSurvey(id) {
            if (confirm('确定要关闭此问卷吗？关闭后将无法继续收集数据。')) {
                await closeSurvey(id);
                alert('问卷已关闭！');
                await this.viewSurvey(id);
            }
        },
        
        async addQuestion() {
            // 验证文本题的长度设置
            if (this.qType === 'text') {
                const minLength = parseInt(this.minLength) || 0;
                const maxLength = parseInt(this.maxLength) || null;
                if (maxLength !== null && maxLength < minLength) {
                    alert('文本题的最大字数不能小于最小字数');
                    return;
                }
            }
            
            // 验证数字题的数值范围设置
            if (this.qType === 'number') {
                const minValue = parseFloat(this.minValue) || null;
                const maxValue = parseFloat(this.maxValue) || null;
                if (minValue !== null && maxValue !== null && maxValue < minValue) {
                    alert('数字题的最大值不能小于最小值');
                    return;
                }
            }
            
            const optionsRaw = this.qOptions;
            const options = optionsRaw.split('\n').filter(l => l.includes('|')).map(l => {
                const [val, text] = l.split('|');
                return { value: val.trim(), text: text.trim(), id: val.trim() };
            });
            
            const questionData = {
                type: this.qType,
                content: this.qContent,
                is_required: this.qRequired,
                options: options,
                min_choices: parseInt(this.minChoices) || null,
                max_choices: parseInt(this.maxChoices) || null,
                min_length: parseInt(this.minLength) || null,
                max_length: parseInt(this.maxLength) || null,
                min_value: parseFloat(this.minValue) || null,
                max_value: parseFloat(this.maxValue) || null,
                is_integer: this.isInteger
            };
            
            await addQuestion(this.currentSurveyId, questionData);
            await this.viewSurvey(this.currentSurveyId);
            
            // 重置表单
            this.qContent = '';
            this.qOptions = '';
            this.minChoices = '';
            this.maxChoices = '';
            this.minLength = '';
            this.maxLength = '';
            this.minValue = '';
            this.maxValue = '';
            this.isInteger = false;
            this.qRequired = false;
        },
        
        // 跳转规则设置
        async showJumpSettings(qId, order) {
            this.jumpSettingQId = qId;
            const data = await getSurveyDetail(this.currentSurveyId);
            this.jumpTarget = 'null';
            this.showJumpModal = true;
        },
        
        async saveJumpRule() {
            const jumps = [{
                logic: 'and',
                conditions: [{ condition: this.jumpCondition, value: this.jumpValue }],
                target_question_id: this.jumpTarget === 'null' ? null : this.jumpTarget
            }];
            
            await updateQuestion(this.jumpSettingQId, { jumps });
            alert('跳转规则保存成功');
            this.showJumpModal = false;
            await this.viewSurvey(this.currentSurveyId);
        },
        
        // 填写问卷
        showFillPrompt() {
            const slug = prompt('请输入问卷的 Slug:');
            if (slug) this.loadFillSurvey(slug);
        },
        
        async loadFillSurvey(slug) {
            try {
                this.currentFillSlug = slug;
                const data = await getFillSurvey(slug);
                this.fillSurveyData = data;
                // 去重处理，确保每个问题只出现一次
                const uniqueQuestions = [];
                const questionIds = new Set();
                for (const question of data.questions) {
                    if (!questionIds.has(question._id)) {
                        questionIds.add(question._id);
                        uniqueQuestions.push(question);
                    }
                }
                // 按照order字段排序，确保问题顺序正确
                uniqueQuestions.sort((a, b) => a.order - b.order);
                this.currentQuestions = uniqueQuestions;
                this.currentQuestionIndex = 0;
                this.allResponses = {};
                this.currentTab = 'fill-survey';
            } catch (error) {
                if (window.location.search) {
                    document.body.innerHTML = `<div style="text-align:center; padding:50px;"><h2>无法打开此问卷</h2><p>${error.message}</p><a href="/">返回主页</a></div>`;
                }
            }
        },
        
        validateAndSaveCurrentAnswer() {
            const q = this.currentQuestions[this.currentQuestionIndex];
            let val = null;
            let text = null;
            
            if (q.type === 'single_choice') {
                const checked = document.querySelector(`input[name="fill-q-${q._id}"]:checked`);
                val = checked ? checked.value : null;
            } else if (q.type === 'multiple_choice') {
                val = Array.from(document.querySelectorAll(`input[name="fill-q-${q._id}"]:checked`)).map(i => i.value);
            } else if (q.type === 'text') {
                val = document.getElementById(`fill-q-text-${q._id}`).value;
                text = val;
            } else if (q.type === 'number') {
                val = document.getElementById(`fill-q-num-${q._id}`).value;
            }
            
            const qName = `第 ${q.order} 题`;
            
            // 必填校验
            const isEmpty = !val || (Array.isArray(val) && val.length === 0) || (typeof val === 'string' && val.trim() === '');
            if (q.is_required && isEmpty) {
                alert(`${qName} 是必填项`); return false;
            }
            
            // 限制校验
            if (!isEmpty) {
                if (q.type === 'multiple_choice') {
                    if (q.min_choices && val.length < q.min_choices) { alert(`${qName} 最少需要选择 ${q.min_choices} 项`); return false; }
                    if (q.max_choices && val.length > q.max_choices) { alert(`${qName} 最多只能选择 ${q.max_choices} 项`); return false; }
                }
                if (q.type === 'text') {
                    if (q.min_length && val.length < q.min_length) { alert(`${qName} 最少输入 ${q.min_length} 个字符`); return false; }
                    if (q.max_length && val.length > q.max_length) { alert(`${qName} 最多输入 ${q.max_length} 个字符`); return false; }
                }
                if (q.type === 'number') {
                    const num = parseFloat(val);
                    if (isNaN(num)) { alert(`${qName} 必须是数字`); return false; }
                    if (q.is_integer && !Number.isInteger(num)) { alert(`${qName} 必须是整数`); return false; }
                    if (q.min_value !== null && num < q.min_value) { alert(`${qName} 不能小于 ${q.min_value}`); return false; }
                    if (q.max_value !== null && num > q.max_value) { alert(`${qName} 不能大于 ${q.max_value}`); return false; }
                }
            }
            
            this.allResponses[q._id] = { question_id: q._id, value: val, text: text };
            return true;
        },
        
        goToNextQuestion() {
            if (!this.validateAndSaveCurrentAnswer()) return;
            
            const q = this.currentQuestions[this.currentQuestionIndex];
            const answer = this.allResponses[q._id];
            
            // 判断跳转逻辑
            if (q.jumps && q.jumps.length > 0 && answer.value !== null && answer.value !== "") {
                for (let jump of q.jumps) {
                    let matched = false;
                    for (let cond of jump.conditions) {
                        const targetVal = String(cond.value);
                        
                        if (Array.isArray(answer.value)) {
                            // 多选题的包含判定
                            if (cond.condition === 'equals' || cond.condition === 'contains') {
                                if (answer.value.includes(targetVal)) matched = true;
                            }
                        } else {
                            // 单选或填空的判定
                            const userVal = String(answer.value);
                            if (cond.condition === 'equals' && userVal === targetVal) matched = true;
                            if (cond.condition === 'contains' && userVal.includes(targetVal)) matched = true;
                        }
                    }
                    
                    if (matched) {
                        if (jump.target_question_id === null) {
                            this.currentQuestionIndex = this.currentQuestions.length;
                            return;
                        } else {
                            const targetIdx = this.currentQuestions.findIndex(que => que._id === jump.target_question_id);
                            if (targetIdx !== -1) {
                                this.currentQuestionIndex = targetIdx;
                                return;
                            }
                        }
                    }
                }
            }
            
            // 默认进入物理顺序上的下一题
            if (this.currentQuestionIndex < this.currentQuestions.length - 1) {
                this.currentQuestionIndex++;
            } else {
                this.currentQuestionIndex = this.currentQuestions.length;
            }
        },
        
        async submitSurvey() {
            // 这里只需要发送前端真实填过的题目
            const responses = Object.values(this.allResponses).filter(r => r.value !== null && r.value !== "" && !(Array.isArray(r.value) && r.value.length === 0));
            await apiSubmitSurvey(this.currentFillSlug, responses);
            alert('提交成功！感谢您的参与。');
            window.location.href = '/';
        },
        
        // 统计结果
        async viewStats(id) {
            this.currentSurveyId = id; // 同步更新当前选中的问卷 ID
            const data = await getSurveyStatistics(id);
            this.surveyStatistics = data.statistics;
            this.currentTab = 'stats';
        }
    };
}

Alpine.data('app', initApp);
Alpine.start();