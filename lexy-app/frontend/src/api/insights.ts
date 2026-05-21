import { apiUrl } from './_baseUrl';
import { assertOkJson } from './_http';
import type {
    InsightCardsResponse,
    PrepViewData,
    GenerateExamplesResponse,
    GrammarRuleDetail,
    GrammarRuleExplainResponse,
} from '../types';

function authHeaders(token: string): HeadersInit {
    return { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };
}

export async function fetchInsightCards(
    token: string,
    language: string,
): Promise<InsightCardsResponse> {
    const params = new URLSearchParams({ language });
    const res = await fetch(apiUrl(`/api/v1/insights/cards?${params}`), {
        headers: authHeaders(token),
    });
    return assertOkJson<InsightCardsResponse>(res, 'Failed to fetch insight cards');
}

export async function fetchPrepData(
    token: string,
    itemId: number,
    itemType: string,
    language: string,
): Promise<PrepViewData> {
    const params = new URLSearchParams({
        item_id: String(itemId),
        item_type: itemType,
        language,
    });
    const res = await fetch(apiUrl(`/api/v1/insights/prep?${params}`), {
        headers: authHeaders(token),
    });
    return assertOkJson<PrepViewData>(res, 'Failed to fetch prep data');
}

export async function generateExamples(
    token: string,
    itemId: number,
    itemType: string,
    language: string,
): Promise<GenerateExamplesResponse> {
    const res = await fetch(apiUrl('/api/v1/insights/prep/generate-examples'), {
        method: 'POST',
        headers: authHeaders(token),
        body: JSON.stringify({ item_id: itemId, item_type: itemType, language }),
    });
    return assertOkJson<GenerateExamplesResponse>(res, 'Failed to generate examples');
}

export async function fetchGrammarRule(
    token: string,
    slug: string,
    language: string,
): Promise<GrammarRuleDetail> {
    const params = new URLSearchParams({ language });
    const res = await fetch(apiUrl(`/api/v1/insights/grammar/${slug}?${params}`), {
        headers: authHeaders(token),
    });
    return assertOkJson<GrammarRuleDetail>(res, 'Failed to fetch grammar rule');
}

export async function generateGrammarExplanation(
    token: string,
    slug: string,
    language: string,
): Promise<GrammarRuleExplainResponse> {
    const params = new URLSearchParams({ language });
    const res = await fetch(apiUrl(`/api/v1/insights/grammar/${slug}/explain?${params}`), {
        method: 'POST',
        headers: authHeaders(token),
    });
    return assertOkJson<GrammarRuleExplainResponse>(res, 'Failed to generate grammar explanation');
}
