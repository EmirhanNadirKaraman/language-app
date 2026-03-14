import { useState, useEffect, useRef, useCallback } from 'react';
import type { SearchResult } from '../types';
import { fetchSearch } from '../api/search';

const PAGE_SIZE = 20;

export function useSearch() {
  const [terms, setTerms] = useState<string[]>([]);
  const [language, setLanguage] = useState<string | null>(null);
  const [results, setResults] = useState<SearchResult[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [offset, setOffset] = useState(0);

  const abortRef = useRef<AbortController | null>(null);
  const query = terms.join(' ');

  const runSearch = useCallback(async (q: string, lang: string | null, off: number, append: boolean) => {
    if (!q.trim()) {
      setResults([]);
      setTotal(0);
      return;
    }

    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setLoading(true);
    setError(null);

    try {
      const data = await fetchSearch(q, lang, PAGE_SIZE, off, controller.signal);
      setResults(prev => append ? [...prev, ...data.results] : data.results);
      setTotal(data.total);
    } catch (e: unknown) {
      if (e instanceof Error && e.name !== 'AbortError') setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    setOffset(0);
    runSearch(query, language, 0, false);
  }, [query, language, runSearch]);

  const addTerm = useCallback((word: string) => {
    setTerms(prev => prev.includes(word) ? prev : [...prev, word]);
  }, []);

  const removeTerm = useCallback((index: number) => {
    setTerms(prev => prev.filter((_, i) => i !== index));
  }, []);

  const loadMore = () => {
    const newOffset = offset + PAGE_SIZE;
    setOffset(newOffset);
    runSearch(query, language, newOffset, true);
  };

  const hasMore = results.length < total;

  return { terms, query, addTerm, removeTerm, language, setLanguage, results, total, loading, error, hasMore, loadMore };
}
