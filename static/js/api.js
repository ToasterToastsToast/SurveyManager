async function api(url, method = 'GET', data = null) {
    const options = { method, headers: { 'Content-Type': 'application/json' } };
    if (data) options.body = JSON.stringify(data);
    const res = await fetch(url, options);
    const result = await res.json();
    if (!res.ok) {
        if (!(url === '/api/me' && res.status === 401)) {
            alert(result.error || '请求失败');
        }
        throw new Error(result.error);
    }
    return result;
}

export async function checkAuth() {
    try {
        const user = await api('/api/me');
        return user;
    } catch (e) {
        return null;
    }
}

export async function login(username, password) {
    return await api('/api/login', 'POST', { username, password });
}

export async function register(username, password, email) {
    return await api('/api/register', 'POST', { username, password, email });
}

export async function logout() {
    return await api('/api/logout', 'POST');
}

export async function getMySurveys() {
    return await api('/api/my_surveys');
}

export async function createSurvey(title, description, isAnonymous, allowMultipleSubmissions, expireAt) {
    return await api('/api/surveys', 'POST', {
        title,
        description,
        is_anonymous: isAnonymous,
        allow_multiple_submissions: allowMultipleSubmissions,
        expire_at: expireAt ? new Date(expireAt).toISOString() : null
    });
}

export async function getSurveyDetail(surveyId) {
    return await api('/api/surveys/' + surveyId);
}

export async function publishSurvey(surveyId) {
    return await api(`/api/surveys/${surveyId}/publish`, 'POST');
}

export async function closeSurvey(surveyId) {
    return await api(`/api/surveys/${surveyId}/close`, 'POST');
}

export async function addQuestion(surveyId, questionData) {
    return await api(`/api/surveys/${surveyId}/questions`, 'POST', questionData);
}

export async function updateQuestion(questionId, data) {
    return await api(`/api/questions/${questionId}`, 'PUT', data);
}

export async function getFillSurvey(slug) {
    return await api('/api/fill_survey/' + slug);
}

export async function submitSurvey(slug, responses) {
    return await api(`/api/surveys/${slug}/submit`, 'POST', { responses });
}

export async function getSurveyStatistics(surveyId) {
    return await api(`/api/surveys/${surveyId}/statistics`);
}