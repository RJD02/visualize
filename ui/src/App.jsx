import { memo, useMemo, useState, useEffect, useRef } from 'react';

import DiagramViewer from './diagram/DiagramViewer.jsx';
import FeedbackModal from './diagram/FeedbackModal.jsx';

const normalizeSvg = (svg) => {
    if (!svg) return svg;
    return svg
        .replace(/xmlns=""([^"]+)""/g, 'xmlns="$1"')
        .replace(/<\s*ns\d+:/gi, '<')
        .replace(/<\/\s*ns\d+:/gi, '</')
        .replace(/\s+xmlns:ns\d+="[^"]*"/gi, '');
};

const svgCacheKey = (imageId, animated, enhanced) => `${imageId}:${animated ? 'anim' : 'static'}:${enhanced ? 'enhanced' : 'original'}`;

const fetchJson = async (url, options = {}, timeoutMs = 120000) => {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
    try {
        const res = await fetch(url, { ...options, signal: controller.signal });
        const data = await res.json().catch(() => null);
        if (!res.ok) {
            const errMsg = (data && (data.error || data.detail)) || res.statusText || 'Request failed';
            throw new Error(errMsg);
        }
        return data;
    } catch (err) {
        if (err && err.name === 'AbortError') {
            throw new Error('Request timed out. Please try again.');
        }
        throw err;
    } finally {
        clearTimeout(timeoutId);
    }
};

const fetchDiagramSvg = async (imageId, animated, enhanced) => {
    const url = `/api/diagram/render?format=svg&animated=${animated ? 'true' : 'false'}&enhanced=${enhanced ? 'true' : 'false'}&image_id=${imageId}`;
    const data = await fetchJson(url, { method: 'GET' });
    if (data && data.svg) data.svg = normalizeSvg(data.svg);
    return data;
};

const extractGithubUrl = (value) => {
    if (!value) return null;
    const match = value.match(/https?:\/\/github\.com\/[\w.-]+\/[\w.-]+/i);
    return match ? match[0] : null;
};

const resolveProviderLabel = (provider) => {
    if (!provider) return null;
    const normalized = String(provider).toLowerCase();
    if (normalized === 'llm_mermaid') return 'Mermaid (LLM)';
    if (normalized === 'llm_plantuml') return 'PlantUML (LLM)';
    if (normalized === 'plantuml') return 'PlantUML';
    if (normalized === 'mermaid') return 'Mermaid';
    if (normalized === 'structurizr') return 'Structurizr';
    if (normalized === 'auto') return 'Auto';
    return provider;
};

const diagramProvider = (image) => {
    if (!image) return null;
    const meta = image.ir_metadata || {};
    const provider = meta.rendering_service || meta.render_provider || meta.provider;
    return resolveProviderLabel(provider);
};

const DiffViewer = ({ before, after, label }) => {
    if (!before && !after) return null;
    const beforeLines = (before || '').split('\n');
    const afterLines = (after || '').split('\n');
    const max = Math.max(beforeLines.length, afterLines.length, 1);
    const limit = Math.min(max, 120);
    return (
        <div className="mt-3 border border-slate-800 rounded-xl overflow-hidden">
            <div className="text-[10px] uppercase tracking-wide bg-slate-900 px-3 py-1 text-slate-300">{label}</div>
            <div className="max-h-64 overflow-auto">
                {Array.from({ length: limit }).map((_, idx) => {
                    const left = beforeLines[idx] || '';
                    const right = afterLines[idx] || '';
                    const changed = left !== right;
                    return (
                        <div key={idx} className={`grid grid-cols-2 border-b border-slate-900 last:border-b-0 text-[11px] font-mono ${changed ? 'bg-slate-900/50' : 'bg-slate-950'}`}>
                            <pre className="p-2 whitespace-pre-wrap text-slate-300">{left}</pre>
                            <pre className="p-2 whitespace-pre-wrap text-slate-100 border-l border-slate-900">{right}</pre>
                        </div>
                    );
                })}
            </div>
            {max > limit ? (
                <div className="text-[10px] text-slate-500 px-3 py-1 bg-slate-900/60">Showing first {limit} lines</div>
            ) : null}
        </div>
    );
};

const JsonViewer = ({ title, data }) => {
    if (!data || (typeof data === 'object' && Object.keys(data).length === 0)) return null;
    const payload = typeof data === 'string' ? data : JSON.stringify(data, null, 2);
    return (
        <details className="mt-2 bg-slate-950/60 border border-slate-900 rounded-lg">
            <summary className="text-xs cursor-pointer px-3 py-2 text-indigo-300">{title}</summary>
            <pre className="p-3 text-[11px] whitespace-pre-wrap text-slate-100">{payload}</pre>
        </details>
    );
};

const StepsList = ({ steps }) => {
    if (!steps) return null;
    const normalized = Array.isArray(steps)
        ? steps
        : typeof steps === 'string'
            ? steps.split('\n').map((s) => s.trim()).filter(Boolean)
            : [];
    if (!normalized.length) return null;
    return (
        <div className="mt-2">
            <div className="text-[11px] uppercase tracking-wide text-slate-400">Execution Steps</div>
            <ol className="mt-1 list-decimal ml-5 text-[12px] text-slate-200 space-y-1">
                {normalized.map((step, idx) => (
                    <li key={idx}>{step}</li>
                ))}
            </ol>
        </div>
    );
};

const describePlanStep = (step) => {
    if (!step || typeof step !== 'object') {
        if (typeof step === 'string') return step;
        try {
            return JSON.stringify(step);
        } catch (err) {
            return 'Unstructured step';
        }
    }
    const tool = step.tool || step.action || step.name || 'Tool';
    const target = step.diagramType || step.target || step.goal || '';
    const description = step.description || step.summary || '';
    let summary = tool;
    if (target) summary += ` -> ${target}`;
    if (description) summary += ` — ${description}`;
    if (step.arguments && Object.keys(step.arguments).length) {
        try {
            const argsJson = JSON.stringify(step.arguments);
            const trimmed = argsJson.length > 160 ? `${argsJson.slice(0, 160)}...` : argsJson;
            summary += ` | args ${trimmed}`;
        } catch (err) {
            summary += ' | args {…}';
        }
    }
    return summary;
};

const PlanCard = ({ plan }) => {
    if (!plan) return null;
    const createdAt = plan.created_at ? new Date(plan.created_at).toLocaleString() : 'Unknown time';
    const requestText = plan.metadata && plan.metadata.user_message ? plan.metadata.user_message : '';
    const steps = Array.isArray(plan.plan_json) ? plan.plan_json.map(describePlanStep) : [];
    const shortId = plan.id ? String(plan.id).slice(0, 8) : '—';
    return (
        <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-3">
            <div className="flex items-center justify-between text-[11px] uppercase tracking-wide text-slate-500">
                <span>{plan.intent || 'Plan'}</span>
                <span>{createdAt}</span>
            </div>
            {requestText ? (
                <div className="mt-2 text-sm text-slate-100 whitespace-pre-wrap">{requestText}</div>
            ) : null}
            {steps.length ? (
                <StepsList steps={steps} />
            ) : (
                <div className="mt-2 text-xs text-slate-500">No steps recorded for this plan.</div>
            )}
            <div className="mt-2 flex flex-wrap gap-2 text-[10px] uppercase tracking-wide text-slate-500">
                <span>{plan.executed ? 'Executed' : 'Pending'}</span>
                <span className="text-slate-600">ID: {shortId}</span>
            </div>
            <JsonViewer title="Raw Plan" data={plan.plan_json} />
            <JsonViewer title="Plan Metadata" data={plan.metadata} />
        </div>
    );
};

const PlanDetail = ({ plan }) => {
    if (!plan) return null;
    const stepsSource = Array.isArray(plan.plan_json) ? plan.plan_json : (plan.plan_json?.plan || []);
    const steps = Array.isArray(stepsSource) ? stepsSource.map(describePlanStep) : [];
    const executions = Array.isArray(plan.executions) ? plan.executions : [];
    return (
        <div className="bg-slate-950/40 border border-slate-900 rounded-lg p-3 space-y-3">
            {steps.length ? <StepsList steps={steps} /> : <div className="text-[11px] text-slate-400">No recorded steps.</div>}
            {executions.length ? (
                <div>
                    <div className="text-[10px] uppercase tracking-wide text-slate-500 mb-1">Executions</div>
                    <ul className="space-y-1 text-[11px] text-slate-300">
                        {executions.map((exec) => {
                            const provider = resolveProviderLabel(
                                exec?.output?.rendering_service || exec?.arguments?.rendering_service || exec?.output?.format
                            );
                            return (
                                <li key={exec.id} className="border border-slate-900 rounded-md px-2 py-1">
                                    <span className="font-semibold text-slate-100">{exec.tool_name}</span>
                                    <span className="ml-2 text-slate-500">step {exec.step_index}</span>
                                    {provider ? (
                                        <span className="ml-2 text-emerald-300">{provider}</span>
                                    ) : null}
                                    {exec.audit_id ? (
                                        <span className="ml-2 text-indigo-300">audit {String(exec.audit_id).slice(0, 8)}</span>
                                    ) : null}
                                    {exec.duration_ms ? (
                                        <span className="ml-2 text-slate-500">{exec.duration_ms}ms</span>
                                    ) : null}
                                </li>
                            );
                        })}
                    </ul>
                </div>
            ) : null}
        </div>
    );
};

const InlineDiagram = memo(({ image, className = '', onClick, enhanced = true, cacheRef, animated = false, onBlockSelect }) => {
    const renderCountRef = useRef(0);
    renderCountRef.current += 1;
    const [svgMarkup, setSvgMarkup] = useState(null);
    const [error, setError] = useState(null);

    if (typeof window !== 'undefined' && window.Cypress && image?.id) {
        window.__inlineDiagramRenderCounts = window.__inlineDiagramRenderCounts || {};
        window.__inlineDiagramRenderCounts[image.id] = renderCountRef.current;
    }

    useEffect(() => {
        if (!image?.id) return;
        let cancelled = false;
        const cacheKey = svgCacheKey(image.id, animated, enhanced);
        const cacheStore = cacheRef?.current;
        if (cacheStore && cacheStore[cacheKey]) {
            setSvgMarkup(cacheStore[cacheKey]);
            setError(null);
            return;
        }
        setSvgMarkup(null);
        setError(null);
        (async () => {
            try {
                const data = await fetchDiagramSvg(image.id, animated, enhanced);
                if (cancelled) return;
                const svgContent = data?.svg || null;
                if (svgContent && cacheStore) cacheStore[cacheKey] = svgContent;
                setSvgMarkup(svgContent);
            } catch (err) {
                if (!cancelled) setError(err?.message || 'Unable to load SVG');
            }
        })();
        return () => {
            cancelled = true;
        };
    }, [image?.id, image?.version, animated, enhanced, cacheRef]);

    if (!image) return null;
    if (error) {
        return (
            <div className={`mt-2 text-xs text-rose-300 border border-rose-900 rounded-lg p-2 ${className}`}>
                Failed to load diagram: {error}
            </div>
        );
    }
    if (!svgMarkup) {
        return (
            <div className={`mt-2 text-xs text-slate-400 border border-slate-800/60 rounded-lg p-2 ${className}`}>
                Loading diagram...
            </div>
        );
    }
    return (
        <div
            data-image-id={image.id}
            style={{ cursor: onClick ? 'zoom-in' : 'default' }}
            onClick={onClick}
        >
            <DiagramViewer
                dataCy="inline-diagram"
                className={`inline-diagram mt-2 rounded-lg border border-slate-800 bg-black/20 ${className}`}
                svgMarkup={svgMarkup}
                onBlockSelect={onBlockSelect}
            />
        </div>
    );
}, (prev, next) => {
    const prevImage = prev.image || {};
    const nextImage = next.image || {};
    const sameImage = prevImage.id === nextImage.id && prevImage.version === nextImage.version;
    return sameImage
        && prev.enhanced === next.enhanced
        && prev.animated === next.animated
        && prev.className === next.className
        && prev.cacheRef === next.cacheRef;
});

const inferDiagramType = (filePath) => {
    if (!filePath) return 'diagram';
    const name = (filePath.split('/').pop() || '').replace(/\.(png|svg)$/i, '');
    const parts = name.split('_');
    if (parts.length >= 3) {
        return parts.slice(1, -1).join('_');
    }
    return 'diagram';
};

const selectImageForCommand = (message, imageList) => {
    if (!message || !imageList || !imageList.length) return null;
    const lowered = message.toLowerCase();
    const order = [...imageList].sort((a, b) => {
        if (a.version != null && b.version != null) return b.version - a.version;
        const aTime = a.created_at ? new Date(a.created_at).getTime() : 0;
        const bTime = b.created_at ? new Date(b.created_at).getTime() : 0;
        return bTime - aTime;
    });
    const matchByType = (type) => order.find((img) => inferDiagramType(img.file_path).includes(type));
    if (lowered.includes('component')) return matchByType('component') || order[0];
    if (lowered.includes('container')) return matchByType('container') || order[0];
    if (lowered.includes('system')) return matchByType('system_context') || order[0];
    if (lowered.includes('sequence')) return matchByType('sequence') || order[0];
    return order[0];
};

export default function App() {
    const [files, setFiles] = useState([]);
    const [sessionId, setSessionId] = useState(null);
    const [messages, setMessages] = useState([]);
    const [images, setImages] = useState([]);
    const [diagrams, setDiagrams] = useState([]);
    const [plans, setPlans] = useState([]);
    const [sourceRepo, setSourceRepo] = useState(null);
    const [sourceCommit, setSourceCommit] = useState(null);
    const [inputMsg, setInputMsg] = useState('');
    const [loading, setLoading] = useState(false);
    const [expandedImage, setExpandedImage] = useState(null);
    const [animationEnabled, setAnimationEnabled] = useState(false);
    const [enhancedEnabled, setEnhancedEnabled] = useState(true);
    const [expandedSvgMap, setExpandedSvgMap] = useState({});
    const [irMap, setIrMap] = useState({});
    const [irSaving, setIrSaving] = useState({});
    const [errorMsg, setErrorMsg] = useState('');
    const [inlineSvgToken, setInlineSvgToken] = useState(0);
    const [stylingAuditMap, setStylingAuditMap] = useState({});
    const [stylingAuditOpen, setStylingAuditOpen] = useState({});
    const [stylingAuditLoading, setStylingAuditLoading] = useState({});
    const [planDetailsMap, setPlanDetailsMap] = useState({});
    const [planDetailsVisible, setPlanDetailsVisible] = useState({});
    const [planDetailsLoading, setPlanDetailsLoading] = useState({});
    const [inlineAnimationMap, setInlineAnimationMap] = useState({});
    const [feedbackOpen, setFeedbackOpen] = useState(false);
    const [feedbackBlockId, setFeedbackBlockId] = useState(null);
    const [feedbackImageId, setFeedbackImageId] = useState(null);
    const inlineSvgCacheRef = useRef({});

    useEffect(() => {
        inlineSvgCacheRef.current = {};
        setInlineAnimationMap({});
    }, [sessionId]);

    useEffect(() => {
        if (!images || !images.length) return;
        setIrMap((prev) => {
            const next = { ...prev };
            images.forEach((img) => {
                if (img.ir_svg_text && !next[img.id]) {
                    next[img.id] = img.ir_svg_text;
                }
            });
            return next;
        });
    }, [images]);

    const toggleStylingPanel = async (imageId) => {
        setStylingAuditOpen((prev) => ({ ...prev, [imageId]: !prev[imageId] }));
        if (!stylingAuditMap[imageId] && !stylingAuditLoading[imageId]) {
            setStylingAuditLoading((prev) => ({ ...prev, [imageId]: true }));
            try {
                const audits = await fetchJson(`/api/diagrams/${imageId}/styling/audit`, { method: 'GET' });
                const ordered = Array.isArray(audits)
                    ? [...audits].sort((a, b) => new Date(b.created_at) - new Date(a.created_at))
                    : [];
                setStylingAuditMap((prev) => ({ ...prev, [imageId]: ordered }));
            } catch (err) {
                setStylingAuditMap((prev) => ({ ...prev, [imageId]: [] }));
            } finally {
                setStylingAuditLoading((prev) => ({ ...prev, [imageId]: false }));
            }
        }
    };

    const togglePlanDetails = async (planId) => {
        if (!planId) return;
        if (planDetailsVisible[planId]) {
            setPlanDetailsVisible((prev) => ({ ...prev, [planId]: false }));
            return;
        }
        if (!planDetailsMap[planId] && !planDetailsLoading[planId]) {
            setPlanDetailsLoading((prev) => ({ ...prev, [planId]: true }));
            try {
                const plan = await fetchJson(`/api/plans/${planId}`, { method: 'GET' });
                setPlanDetailsMap((prev) => ({ ...prev, [planId]: plan }));
            } catch (err) {
                setErrorMsg(err?.message || 'Failed to load plan history.');
                setPlanDetailsLoading((prev) => ({ ...prev, [planId]: false }));
                return;
            }
            setPlanDetailsLoading((prev) => ({ ...prev, [planId]: false }));
        }
        setPlanDetailsVisible((prev) => ({ ...prev, [planId]: true }));
    };

    useEffect(() => {
        // when expanding an image, prefetch the original static svg so toggle can switch quickly
        if (!expandedImage) return;
        let cancelled = false;
        (async () => {
            try {
                const data = await fetchDiagramSvg(expandedImage.id, false, false);
                const key = svgCacheKey(expandedImage.id, false, false);
                if (!cancelled) setExpandedSvgMap((p) => ({ ...p, [key]: data.svg }));
            } catch (e) {
                // ignore
            }
        })();
        // respect reduced motion preference by default
        try {
            const prefersReduce = typeof window !== 'undefined' && window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
            if (prefersReduce) setAnimationEnabled(false);
        } catch (e) { }
        return () => { cancelled = true; };
    }, [expandedImage]);

    const saveEditedIR = async (imageId) => {
        if (!imageId) return;
        const svg = irMap[imageId];
        if (!svg) return;
        setIrSaving((p) => ({ ...p, [imageId]: true }));
        try {
            const res = await fetch(`/api/images/${imageId}/ir`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ svg_text: svg, reason: 'edited via ui' }),
            });
            if (res.ok) {
                // refresh session to get updated images/messages
                if (sessionId) await refreshSession(sessionId);
            } else {
                const err = await res.json().catch(() => ({}));
                alert('Failed to save IR: ' + (err.error || res.statusText));
            }
        } catch (e) {
            alert('Failed to save IR: ' + e.message);
        }
        setIrSaving((p) => ({ ...p, [imageId]: false }));
    };

    const imageMap = useMemo(() => new Map((images || []).map((img) => [img.id, img])), [images]);

    const viewDiagramInline = async (img, enhanced = false) => {
        if (!img) return;
        setExpandedImage(img);
        setEnhancedEnabled(enhanced);
        setAnimationEnabled(false);
        setInlineAnimationMap((prev) => ({ ...prev, [img.id]: false }));
        try {
            const data = await fetchDiagramSvg(img.id, false, enhanced);
            const key = svgCacheKey(img.id, false, enhanced);
            setExpandedSvgMap((p) => ({ ...p, [key]: data.svg }));
            if (inlineSvgCacheRef.current) {
                inlineSvgCacheRef.current[key] = data.svg;
            }
        } catch (e) { /* ignore */ }
    };

    const animateDiagram = async (img) => {
        if (!img) return;
        setExpandedImage(img);
        setEnhancedEnabled(true);
        setAnimationEnabled(true);
        try {
            const data = await fetchDiagramSvg(img.id, true, true);
            const key = svgCacheKey(img.id, true, true);
            setExpandedSvgMap((p) => ({ ...p, [key]: data.svg }));
            if (inlineSvgCacheRef.current) {
                inlineSvgCacheRef.current[key] = data.svg;
            }
            setInlineAnimationMap((prev) => ({ ...prev, [img.id]: true }));
        } catch (e) { /* ignore */ }
    };

    const renderIrPanel = (image) => {
        if (!image?.id) return null;
        const currentValue = irMap[image.id];
        const hasPayload = currentValue || image.ir_svg_text;
        if (!hasPayload) return null;
        const value = currentValue ?? image.ir_svg_text ?? '';
        return (
            <div className="mt-3 rounded-xl border border-slate-900 bg-slate-950/70 p-3">
                <div className="text-[11px] uppercase tracking-wide text-slate-400">IR Source</div>
                <textarea
                    className="w-full text-[11px] whitespace-pre bg-slate-950 border border-slate-800 rounded-lg p-2 max-h-48 overflow-auto mt-2"
                    style={{ minHeight: 120 }}
                    value={value}
                    onChange={(e) => setIrMap((prev) => ({ ...prev, [image.id]: e.target.value }))}
                />
                <div className="mt-2 flex gap-2">
                    <button
                        className="text-xs text-emerald-300 hover:text-emerald-200"
                        onClick={() => saveEditedIR(image.id)}
                        disabled={irSaving[image.id]}
                    >
                        {irSaving[image.id] ? 'Saving...' : 'Save IR'}
                    </button>
                </div>
                {image.ir_metadata ? <JsonViewer title="IR Metadata" data={image.ir_metadata} /> : null}
            </div>
        );
    };
    const sortedImages = useMemo(() => {
        return [...(images || [])].sort((a, b) => {
            if (a.version != null && b.version != null) return a.version - b.version;
            const aTime = a.created_at ? new Date(a.created_at).getTime() : 0;
            const bTime = b.created_at ? new Date(b.created_at).getTime() : 0;
            return aTime - bTime;
        });
    }, [images]);

    const plansSorted = useMemo(() => {
        const parseTime = (value) => {
            if (!value) return 0;
            const ts = new Date(value).getTime();
            return Number.isNaN(ts) ? 0 : ts;
        };
        return [...(plans || [])].sort((a, b) => parseTime(b.created_at) - parseTime(a.created_at));
    }, [plans]);

    const timelineEvents = useMemo(() => {
        const parseTime = (value) => {
            if (!value) return 0;
            const ts = new Date(value).getTime();
            return Number.isNaN(ts) ? 0 : ts;
        };
        const messageEvents = (messages || []).map((m, idx) => ({
            type: 'message',
            ts: parseTime(m.created_at),
            payload: m,
            key: `message-${m.id || idx}`,
        }));
        const planEvents = (plans || []).map((plan, idx) => ({
            type: 'plan',
            ts: parseTime(plan.created_at) || (messageEvents.length + idx + 1),
            payload: plan,
            key: `plan-${plan.id || idx}`,
        }));
        return [...messageEvents, ...planEvents].sort((a, b) => a.ts - b.ts);
    }, [messages, plans]);

    const currentSvgKey = expandedImage ? svgCacheKey(expandedImage.id, animationEnabled, enhancedEnabled) : null;

    const createSession = async () => {
        const data = await fetchJson('/api/sessions', { method: 'POST' });
        setSessionId(data.session_id);
        return data.session_id;
    };

    useEffect(() => {
        if (typeof window === 'undefined') return;
        const params = new URLSearchParams(window.location.search);
        const seedSession = params.get('session');
        if (seedSession && seedSession !== sessionId) {
            setSessionId(seedSession);
            refreshSession(seedSession);
        }
    }, []);

    const refreshSession = async (id) => {
        const data = await fetchJson(`/api/sessions/${id}`);
        setMessages(data.messages || []);
        setImages(data.images || []);
        setDiagrams(data.diagrams || []);
        setPlans(data.plans || []);
        setSourceRepo(data.source_repo || null);
        setSourceCommit(data.source_commit || null);
        return data;
    };

    const openFeedback = (imageId, blockId) => {
        setFeedbackImageId(imageId);
        setFeedbackBlockId(blockId || null);
        setFeedbackOpen(true);
    };

    const submitFeedback = async ({ action, payload }) => {
        if (!feedbackImageId) return;
        try {
            await fetchJson('/api/feedback', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    diagram_id: feedbackImageId,
                    block_id: feedbackBlockId,
                    action,
                    payload,
                }),
            });
            if (sessionId) {
                const data = await refreshSession(sessionId);
                if (data?.images?.length) {
                    const latest = [...data.images].sort((a, b) => (b.version || 0) - (a.version || 0))[0];
                    if (latest) setExpandedImage(latest);
                }
            }
            setFeedbackOpen(false);
        } catch (err) {
            alert('Feedback failed: ' + (err?.message || err));
        }
    };

    const sendMessage = async () => {
        if (!inputMsg.trim()) return;
        setLoading(true);
        setErrorMsg('');
        try {
            const id = sessionId || await createSession();
            const rawMessage = inputMsg;
            const ghUrl = extractGithubUrl(inputMsg);
            if (files.length || ghUrl) {
                const form = new FormData();
                form.append('text', inputMsg);
                for (const f of files) form.append('files', f);
                if (ghUrl) form.append('github_url', ghUrl);
                await fetchJson(`/api/sessions/${id}/ingest`, { method: 'POST', body: form });
            }
            await fetchJson(`/api/sessions/${id}/messages`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ content: inputMsg })
            });
            setInputMsg('');
            setFiles([]);
            const sessionData = await refreshSession(id);

            const lastImage = selectImageForCommand(rawMessage, sessionData?.images || []);

            const lowered = (rawMessage || '').toLowerCase();
            const wantsAnimate = lowered.includes('animate');

            if (lastImage && wantsAnimate) {
                setExpandedImage(lastImage);
                setEnhancedEnabled(true);
                setAnimationEnabled(true);
                try {
                    const data = await fetchDiagramSvg(lastImage.id, true, true);
                    const key = svgCacheKey(lastImage.id, true, true);
                    setExpandedSvgMap((p) => ({ ...p, [key]: data.svg }));
                    if (inlineSvgCacheRef.current) {
                        inlineSvgCacheRef.current[key] = data.svg;
                    }
                    setInlineAnimationMap((prev) => ({ ...prev, [lastImage.id]: true }));
                    setInlineSvgToken((v) => v + 1);
                } catch (e) { /* ignore */ }
            }
        } catch (err) {
            setErrorMsg(err?.message || 'Failed to send message.');
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="min-h-screen bg-slate-950 text-slate-100">
            <div className="max-w-[96vw] 2xl:max-w-[1800px] mx-auto px-4 sm:px-6 py-6">
                <div className="flex items-center justify-between mb-5">
                    <div className="flex items-center gap-4">
                        <div className="text-2xl font-semibold tracking-tight">Architecture Copilot</div>
                        <div className="flex items-center gap-1 text-xs bg-slate-900 border border-slate-800 rounded-lg p-1">
                            <button
                                className={`px-2 py-1 rounded ${!enhancedEnabled ? 'bg-slate-700 text-white' : 'text-slate-300 hover:text-white'}`}
                                onClick={async () => {
                                    setEnhancedEnabled(false);
                                    setAnimationEnabled(false);
                                    if (!expandedImage) return;
                                    try {
                                        const data = await fetchDiagramSvg(expandedImage.id, false, false);
                                        const key = svgCacheKey(expandedImage.id, false, false);
                                        setExpandedSvgMap((p) => ({ ...p, [key]: data.svg }));
                                    } catch (err) { /* ignore */ }
                                }}
                            >
                                Original
                            </button>
                            <button
                                className={`px-2 py-1 rounded ${enhancedEnabled ? 'bg-indigo-500 text-white' : 'text-slate-300 hover:text-white'}`}
                                onClick={async () => {
                                    setEnhancedEnabled(true);
                                    if (!expandedImage) return;
                                    try {
                                        const data = await fetchDiagramSvg(expandedImage.id, animationEnabled, true);
                                        const key = svgCacheKey(expandedImage.id, animationEnabled, true);
                                        setExpandedSvgMap((p) => ({ ...p, [key]: data.svg }));
                                    } catch (err) { /* ignore */ }
                                }}
                            >
                                Enhanced
                            </button>
                        </div>
                        <label className="flex items-center gap-2 text-sm text-slate-300">
                            <input type="checkbox" checked={animationEnabled} onChange={async (e) => {
                                const on = e.target.checked;
                                if (!enhancedEnabled && on) return;
                                setAnimationEnabled(on);
                                // if currently showing inline svg for an expanded image, refresh it to match new mode
                                if (expandedImage) {
                                    try {
                                        const data = await fetchDiagramSvg(expandedImage.id, on, enhancedEnabled);
                                        const key = svgCacheKey(expandedImage.id, on, enhancedEnabled);
                                        setExpandedSvgMap((p) => ({ ...p, [key]: data.svg }));
                                    } catch (err) { /* ignore */ }
                                }
                            }} disabled={!enhancedEnabled} />
                            <span className="text-xs">Animation</span>
                        </label>
                    </div>
                    <div className="text-xs text-slate-400 text-right">
                        <div>{sessionId ? `Session: ${sessionId}` : 'No session yet'}</div>
                        {sourceRepo ? <div>Repo: {sourceRepo} {sourceCommit ? `(${sourceCommit.slice(0, 7)})` : ''}</div> : null}
                    </div>
                </div>
                <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-[2fr_1fr_1fr] gap-6">
                    <div className="flex flex-col h-[82vh] xl:col-span-2">
                        <div className="bg-slate-900/60 rounded-2xl p-4 border border-slate-800 flex-1 flex flex-col min-h-0">
                            <div className="flex items-center justify-between mb-3">
                                <div className="text-sm font-semibold">Chat</div>
                                <div className="text-[11px] text-slate-400">Share a story, architecture, or GitHub link.</div>
                            </div>
                            <div className="flex-1 overflow-y-auto space-y-5 text-sm pr-2 min-h-0">
                                {messages.length ? (
                                    timelineEvents.map((entry, idx) => {
                                        if (entry.type === 'plan') {
                                            const plan = entry.payload;
                                            const createdAt = plan.created_at ? new Date(plan.created_at).toLocaleString() : 'Recently';
                                            const steps = Array.isArray(plan.plan_json) ? plan.plan_json.map(describePlanStep) : [];
                                            const shortId = plan.id ? String(plan.id).slice(0, 8) : `plan-${idx}`;
                                            const metadata = plan.metadata || {};
                                            const request = metadata.user_message || metadata.instructions || '';
                                            const isVisible = plan.id ? planDetailsVisible[plan.id] : false;
                                            const isLoading = plan.id ? planDetailsLoading[plan.id] : false;
                                            const detailPlan = plan.id ? (planDetailsMap[plan.id] || null) : null;
                                            return (
                                                <div key={entry.key} className="text-slate-200">
                                                    <div className="mt-4 rounded-xl border border-indigo-900 bg-slate-950/70 p-3">
                                                        <div className="flex items-center justify-between text-[11px] uppercase tracking-wide text-indigo-300">
                                                            <span>Planner Steps</span>
                                                            <span className="text-slate-400">{createdAt}</span>
                                                        </div>
                                                        {request ? (
                                                            <div className="mt-2 text-sm text-slate-100 whitespace-pre-wrap">{request}</div>
                                                        ) : null}
                                                        {steps.length ? (
                                                            <StepsList steps={steps} />
                                                        ) : (
                                                            <div className="mt-2 text-xs text-slate-400">No recorded steps.</div>
                                                        )}
                                                        <div className="mt-2 flex gap-3 text-[11px] text-slate-400">
                                                            <span>{plan.intent || 'Plan'}</span>
                                                            <span className="text-slate-600">ID {shortId}</span>
                                                        </div>
                                                        {plan.id ? (
                                                            <div className="mt-2">
                                                                <button
                                                                    className="text-xs text-indigo-300 hover:text-indigo-100"
                                                                    onClick={() => togglePlanDetails(plan.id)}
                                                                >
                                                                    {isVisible ? 'Hide Plan History' : (isLoading ? 'Loading…' : 'Show Plan History')}
                                                                </button>
                                                                {isVisible ? (
                                                                    <div className="mt-2">
                                                                        {isLoading ? (
                                                                            <div className="text-[11px] text-slate-400">Loading plan...</div>
                                                                        ) : (
                                                                            <PlanDetail plan={detailPlan || plan} />
                                                                        )}
                                                                    </div>
                                                                ) : null}
                                                            </div>
                                                        ) : null}
                                                    </div>
                                                </div>
                                            );
                                        }
                                        const m = entry.payload;
                                        return (
                                            <div key={entry.key} className={m.role === 'user' ? 'text-indigo-200' : 'text-slate-200'}>
                                                <div className="text-[11px] uppercase tracking-wide text-slate-500">{m.role}</div>
                                                {m.content ? <div className="mt-1 whitespace-pre-wrap">{m.content}</div> : null}
                                                {(m.message_type === 'image' || m.image_id) && imageMap.get(m.image_id) ? (
                                                    <div className="mt-3 rounded-xl border border-slate-800 bg-slate-950/60 p-3">
                                                        <div className="text-[11px] text-slate-500">
                                                            Image v{m.image_version || imageMap.get(m.image_id).version} · {(m.diagram_type || imageMap.get(m.image_id)?.diagram_type || inferDiagramType(imageMap.get(m.image_id).file_path))}
                                                            {diagramProvider(imageMap.get(m.image_id)) ? ` · ${diagramProvider(imageMap.get(m.image_id))}` : ''}
                                                        </div>
                                                        <InlineDiagram
                                                            image={imageMap.get(m.image_id)}
                                                            className="max-w-full"
                                                            onClick={() => setExpandedImage(imageMap.get(m.image_id))}
                                                            cacheRef={inlineSvgCacheRef}
                                                            animated={!!inlineAnimationMap[m.image_id]}
                                                            onBlockSelect={(blockId) => openFeedback(m.image_id, blockId)}
                                                        />
                                                        <div className="mt-2 flex flex-wrap gap-2">
                                                            <button
                                                                className="text-xs text-indigo-300 hover:text-indigo-200"
                                                                onClick={() => toggleStylingPanel(m.image_id)}
                                                            >
                                                                {stylingAuditOpen[m.image_id] ? 'Hide Styling Plan' : 'View Styling Plan'}
                                                            </button>
                                                            <button
                                                                className="text-xs text-indigo-300 hover:text-indigo-200"
                                                                onClick={() => viewDiagramInline(imageMap.get(m.image_id), false)}
                                                            >
                                                                View Diagram
                                                            </button>
                                                            <button
                                                                className="text-xs text-indigo-300 hover:text-indigo-200"
                                                                onClick={() => viewDiagramInline(imageMap.get(m.image_id), true)}
                                                            >
                                                                Inline
                                                            </button>
                                                            <button
                                                                className="text-xs text-indigo-300 hover:text-indigo-200"
                                                                onClick={() => animateDiagram(imageMap.get(m.image_id))}
                                                            >
                                                                Animate
                                                            </button>
                                                            <a
                                                                className="text-xs text-indigo-300 hover:text-indigo-200"
                                                                href={imageMap.get(m.image_id)?.file_path || '#'}
                                                                target="_blank"
                                                                rel="noopener noreferrer"
                                                            >
                                                                Export
                                                            </a>
                                                        </div>
                                                        {stylingAuditOpen[m.image_id] ? (
                                                            <div className="mt-3 border border-indigo-900 rounded-xl bg-slate-950/70 p-3">
                                                                {stylingAuditLoading[m.image_id] ? (
                                                                    <div className="text-xs text-slate-400">Loading styling history...</div>
                                                                ) : ((stylingAuditMap[m.image_id] || []).length ? (
                                                                    (stylingAuditMap[m.image_id] || []).map((audit) => (
                                                                        <div key={audit.id} className="mb-4 last:mb-0 border border-slate-900 rounded-xl p-3 bg-slate-950/60">
                                                                            <div className="flex items-center justify-between text-[11px] text-slate-400">
                                                                                <div>{new Date(audit.created_at).toLocaleString()}</div>
                                                                                <span className="uppercase text-[10px] text-indigo-300">{audit.mode}</span>
                                                                            </div>
                                                                            <div className="mt-1 text-[10px] text-slate-500">
                                                                                Audit {String(audit.id).slice(0, 8)}
                                                                                {audit.plan_id ? ` · Plan ${String(audit.plan_id).slice(0, 8)}` : ''}
                                                                            </div>
                                                                            {audit.plan_id ? (
                                                                                <div className="mt-2 text-[11px] text-indigo-300 flex items-center gap-2">
                                                                                    <button
                                                                                        className="hover:text-indigo-100"
                                                                                        onClick={() => togglePlanDetails(audit.plan_id)}
                                                                                    >
                                                                                        {planDetailsVisible[audit.plan_id]
                                                                                            ? 'Hide Plan History'
                                                                                            : (planDetailsLoading[audit.plan_id] ? 'Loading…' : 'Show Plan History')}
                                                                                    </button>
                                                                                </div>
                                                                            ) : null}
                                                                            {audit.plan_id && planDetailsVisible[audit.plan_id] ? (
                                                                                <div className="mt-2">
                                                                                    {planDetailsLoading[audit.plan_id] ? (
                                                                                        <div className="text-[11px] text-slate-400">Loading plan...</div>
                                                                                    ) : (
                                                                                        <PlanDetail plan={planDetailsMap[audit.plan_id]} />
                                                                                    )}
                                                                                </div>
                                                                            ) : null}
                                                                            <div className="mt-2 text-sm text-slate-100 whitespace-pre-wrap">{audit.user_prompt || 'Styling applied automatically.'}</div>
                                                                            {audit.agent_reasoning ? (
                                                                                <div className="mt-2 text-xs text-slate-300 bg-slate-900/50 rounded-lg p-2">{audit.agent_reasoning}</div>
                                                                            ) : null}
                                                                            <StepsList steps={audit.execution_steps} />
                                                                            {audit.llm_diagram ? (
                                                                                <JsonViewer title="Original LLM Diagram" data={audit.llm_diagram} />
                                                                            ) : null}
                                                                            {audit.sanitized_diagram ? (
                                                                                <JsonViewer title="Sanitized Diagram" data={audit.sanitized_diagram} />
                                                                            ) : null}
                                                                            <JsonViewer title="Extracted Intent" data={audit.extracted_intent} />
                                                                            <JsonViewer title="Styling Plan" data={audit.styling_plan} />
                                                                            {audit.validation_warnings?.length ? (
                                                                                <JsonViewer title="Validation Warnings" data={audit.validation_warnings} />
                                                                            ) : null}
                                                                            {audit.blocked_tokens?.length ? (
                                                                                <JsonViewer title="Blocked Tokens" data={audit.blocked_tokens} />
                                                                            ) : null}
                                                                            <DiffViewer
                                                                                label={audit.svg_before || audit.svg_after ? 'SVG Diff' : 'Renderer Diff'}
                                                                                before={audit.svg_before || audit.renderer_input_before}
                                                                                after={audit.svg_after || audit.renderer_input_after}
                                                                            />
                                                                        </div>
                                                                    ))
                                                                ) : (
                                                                    <div className="text-xs text-slate-400">No styling history yet.</div>
                                                                ))}
                                                            </div>
                                                        ) : null}
                                                        {renderIrPanel(imageMap.get(m.image_id))}
                                                    </div>
                                                ) : null}
                                            </div>
                                        );
                                    })
                                ) : (
                                    <div className="text-slate-500">Ask for a diagram, paste a GitHub URL, or upload files.</div>
                                )}
                            </div>
                            {errorMsg ? (
                                <div className="mt-3 text-xs text-rose-300 bg-rose-950/40 border border-rose-900 rounded-lg p-2">
                                    {errorMsg}
                                </div>
                            ) : null}
                            <div className="mt-3 flex flex-col gap-2">
                                <textarea
                                    data-cy="chat-input"
                                    className="w-full rounded-lg bg-slate-950 border border-slate-800 p-3 text-sm"
                                    value={inputMsg}
                                    onChange={(e) => setInputMsg(e.target.value)}
                                    placeholder="Describe the diagram you want or request edits..."
                                    rows={3}
                                />
                                <div className="flex items-center justify-between">
                                    <input
                                        className="text-sm"
                                        type="file"
                                        multiple
                                        onChange={(e) => setFiles(Array.from(e.target.files || []))}
                                    />
                                    <button
                                        data-cy="send-button"
                                        className="bg-emerald-500 hover:bg-emerald-400 text-white rounded-lg px-4 py-2 text-sm"
                                        onClick={sendMessage}
                                        disabled={loading}
                                    >
                                        {loading ? 'Working...' : 'Send'}
                                    </button>
                                </div>
                            </div>
                        </div>
                    </div>
                    <div data-cy="diagram-history-panel" className="bg-slate-900/60 rounded-2xl p-4 border border-slate-800 h-[82vh] overflow-y-auto">
                        <div className="mb-4 border-b border-slate-800 pb-3 flex items-center justify-between">
                            <div>
                                <div className="text-[11px] uppercase tracking-wide text-slate-400">Diagram History</div>
                                <div className="text-xs text-slate-500">All diagrams are shown inline in chat. Click any image to expand.</div>
                            </div>
                            <div className="text-[11px] text-slate-500">{sortedImages.length} total</div>
                        </div>
                        {sortedImages.length ? (
                            <div className="space-y-4">
                                {sortedImages.map((img) => (
                                    <div key={img.id} className="rounded-xl border border-slate-800 bg-slate-950/60 p-3">
                                        <div className="text-[11px] text-slate-500">
                                            Image v{img.version} · {inferDiagramType(img.file_path)}
                                            {diagramProvider(img) ? ` · ${diagramProvider(img)}` : ''}
                                        </div>
                                        <InlineDiagram
                                            image={img}
                                            className="max-w-full"
                                            onClick={() => setExpandedImage(img)}
                                            cacheRef={inlineSvgCacheRef}
                                            animated={!!inlineAnimationMap[img.id]}
                                            onBlockSelect={(blockId) => openFeedback(img.id, blockId)}
                                        />
                                        <div className="mt-2 flex flex-wrap gap-2">
                                            <button
                                                className="text-xs text-indigo-300 hover:text-indigo-200"
                                                onClick={() => toggleStylingPanel(img.id)}
                                            >
                                                {stylingAuditOpen[img.id] ? 'Hide Styling Plan' : 'View Styling Plan'}
                                            </button>
                                            <button
                                                className="text-xs text-indigo-300 hover:text-indigo-200"
                                                onClick={() => viewDiagramInline(img, false)}
                                            >
                                                View Diagram
                                            </button>
                                            <button
                                                className="text-xs text-indigo-300 hover:text-indigo-200"
                                                onClick={() => viewDiagramInline(img, true)}
                                            >
                                                Inline
                                            </button>
                                            <button
                                                className="text-xs text-indigo-300 hover:text-indigo-200"
                                                onClick={() => animateDiagram(img)}
                                            >
                                                Animate
                                            </button>
                                            <a
                                                className="text-xs text-indigo-300 hover:text-indigo-200"
                                                href={`${img.file_path}`}
                                                target="_blank"
                                                rel="noopener noreferrer"
                                            >
                                                Export
                                            </a>
                                        </div>
                                        {stylingAuditOpen[img.id] ? (
                                            <div className="mt-3 border border-indigo-900 rounded-xl bg-slate-950/70 p-3">
                                                {stylingAuditLoading[img.id] ? (
                                                    <div className="text-xs text-slate-400">Loading styling history...</div>
                                                ) : ((stylingAuditMap[img.id] || []).length ? (
                                                    (stylingAuditMap[img.id] || []).map((audit) => (
                                                        <div key={audit.id} className="mb-4 last:mb-0 border border-slate-900 rounded-xl p-3 bg-slate-950/60">
                                                            <div className="flex items-center justify-between text-[11px] text-slate-400">
                                                                <div>{new Date(audit.created_at).toLocaleString()}</div>
                                                                <span className="uppercase text-[10px] text-indigo-300">{audit.mode}</span>
                                                            </div>
                                                            <div className="mt-1 text-[10px] text-slate-500">
                                                                Audit {String(audit.id).slice(0, 8)}
                                                                {audit.plan_id ? ` · Plan ${String(audit.plan_id).slice(0, 8)}` : ''}
                                                            </div>
                                                            {audit.plan_id ? (
                                                                <div className="mt-2 text-[11px] text-indigo-300 flex items-center gap-2">
                                                                    <button
                                                                        className="hover:text-indigo-100"
                                                                        onClick={() => togglePlanDetails(audit.plan_id)}
                                                                    >
                                                                        {planDetailsVisible[audit.plan_id]
                                                                            ? 'Hide Plan History'
                                                                            : (planDetailsLoading[audit.plan_id] ? 'Loading…' : 'Show Plan History')}
                                                                    </button>
                                                                </div>
                                                            ) : null}
                                                            {audit.plan_id && planDetailsVisible[audit.plan_id] ? (
                                                                <div className="mt-2">
                                                                    {planDetailsLoading[audit.plan_id] ? (
                                                                        <div className="text-[11px] text-slate-400">Loading plan...</div>
                                                                    ) : (
                                                                        <PlanDetail plan={planDetailsMap[audit.plan_id]} />
                                                                    )}
                                                                </div>
                                                            ) : null}
                                                            <div className="mt-2 text-sm text-slate-100 whitespace-pre-wrap">{audit.user_prompt || 'Styling applied automatically.'}</div>
                                                            {audit.agent_reasoning ? (
                                                                <div className="mt-2 text-xs text-slate-300 bg-slate-900/50 rounded-lg p-2">{audit.agent_reasoning}</div>
                                                            ) : null}
                                                            <StepsList steps={audit.execution_steps} />
                                                            {audit.llm_diagram ? (
                                                                <JsonViewer title="Original LLM Diagram" data={audit.llm_diagram} />
                                                            ) : null}
                                                            {audit.sanitized_diagram ? (
                                                                <JsonViewer title="Sanitized Diagram" data={audit.sanitized_diagram} />
                                                            ) : null}
                                                            <JsonViewer title="Extracted Intent" data={audit.extracted_intent} />
                                                            <JsonViewer title="Styling Plan" data={audit.styling_plan} />
                                                            {audit.validation_warnings?.length ? (
                                                                <JsonViewer title="Validation Warnings" data={audit.validation_warnings} />
                                                            ) : null}
                                                            {audit.blocked_tokens?.length ? (
                                                                <JsonViewer title="Blocked Tokens" data={audit.blocked_tokens} />
                                                            ) : null}
                                                            <DiffViewer
                                                                label={audit.svg_before || audit.svg_after ? 'SVG Diff' : 'Renderer Diff'}
                                                                before={audit.svg_before || audit.renderer_input_before}
                                                                after={audit.svg_after || audit.renderer_input_after}
                                                            />
                                                        </div>
                                                    ))
                                                ) : (
                                                    <div className="text-xs text-slate-400">No styling history yet.</div>
                                                ))}
                                            </div>
                                        ) : null}
                                        {renderIrPanel(img)}
                                    </div>
                                ))}
                            </div>
                        ) : (
                            <div className="text-slate-500 text-sm">No diagrams yet. Generate one to populate history.</div>
                        )}
                    </div>
                    <div className="bg-slate-900/60 rounded-2xl p-4 border border-slate-800 h-[82vh] overflow-y-auto">
                        <div className="mb-4 border-b border-slate-800 pb-3 flex items-center justify-between">
                            <div>
                                <div className="text-[11px] uppercase tracking-wide text-slate-400">Planner History</div>
                                <div className="text-xs text-slate-500">Every request generates a plan with ordered tool steps.</div>
                            </div>
                            <div className="text-[11px] text-slate-500">{plansSorted.length} plans</div>
                        </div>
                        {plansSorted.length ? (
                            <div className="space-y-4">
                                {plansSorted.map((plan) => (
                                    <PlanCard key={plan.id} plan={plan} />
                                ))}
                            </div>
                        ) : (
                            <div className="text-slate-500 text-sm">Plans will appear after you send your first request.</div>
                        )}
                    </div>
                </div>
            </div>

            {expandedImage ? (
                <div
                    className="fixed inset-0 bg-black/70 flex items-center justify-center z-50"
                    onClick={() => { setExpandedImage(null); setAnimationEnabled(false); }}
                >
                    <div
                        className="w-[94vw]"
                        style={{ maxHeight: '90vh', display: 'flex', flexDirection: 'column' }}
                        onClick={(e) => e.stopPropagation()}
                    >
                        <div className="flex items-center justify-between mb-2 text-slate-200 text-sm">
                            <span>Image v{expandedImage.version} · ID: {expandedImage.id.slice(0, 8)}</span>
                            <button className="px-2 py-1 rounded bg-slate-800" onClick={() => setExpandedImage(null)}>Close</button>
                        </div>
                        <div
                            className="bg-slate-950 rounded-lg border border-slate-800"
                            style={{ flex: 1, overflowY: 'auto', padding: 12, display: 'flex', justifyContent: 'center' }}
                        >
                            <div style={{ width: '100%' }}>
                                <div className="flex items-center justify-between mb-2">
                                    <div className="flex items-center gap-4">
                                        <div className="flex items-center gap-1 text-xs bg-slate-900 border border-slate-800 rounded-lg p-1">
                                            <button
                                                className={`px-2 py-1 rounded ${!enhancedEnabled ? 'bg-slate-700 text-white' : 'text-slate-300 hover:text-white'}`}
                                                onClick={async () => {
                                                    setEnhancedEnabled(false);
                                                    setAnimationEnabled(false);
                                                    if (!expandedImage) return;
                                                    try {
                                                        const data = await fetchDiagramSvg(expandedImage.id, false, false);
                                                        const key = svgCacheKey(expandedImage.id, false, false);
                                                        setExpandedSvgMap((p) => ({ ...p, [key]: data.svg }));
                                                    } catch (err) {
                                                        alert('Render failed: ' + err.message);
                                                    }
                                                }}
                                            >
                                                Original
                                            </button>
                                            <button
                                                className={`px-2 py-1 rounded ${enhancedEnabled ? 'bg-indigo-500 text-white' : 'text-slate-300 hover:text-white'}`}
                                                onClick={async () => {
                                                    setEnhancedEnabled(true);
                                                    if (!expandedImage) return;
                                                    try {
                                                        const data = await fetchDiagramSvg(expandedImage.id, animationEnabled, true);
                                                        const key = svgCacheKey(expandedImage.id, animationEnabled, true);
                                                        setExpandedSvgMap((p) => ({ ...p, [key]: data.svg }));
                                                    } catch (err) {
                                                        alert('Render failed: ' + err.message);
                                                    }
                                                }}
                                            >
                                                Enhanced
                                            </button>
                                        </div>
                                        <label className="flex items-center gap-2 text-sm">
                                            <input type="checkbox" checked={animationEnabled} onChange={async (e) => {
                                                const on = e.target.checked;
                                                // respects reduced motion preference
                                                const prefersReduce = typeof window !== 'undefined' && window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
                                                if (prefersReduce && on) {
                                                    alert('Animation disabled due to your system "reduced motion" preference.');
                                                    return;
                                                }
                                                if (!enhancedEnabled && on) return;
                                                setAnimationEnabled(on);
                                                if (!expandedImage) return;
                                                // fetch rendered svg from server
                                                try {
                                                    const data = await fetchDiagramSvg(expandedImage.id, on, enhancedEnabled);
                                                    const key = svgCacheKey(expandedImage.id, on, enhancedEnabled);
                                                    setExpandedSvgMap((p) => ({ ...p, [key]: data.svg }));
                                                } catch (err) {
                                                    alert('Render failed: ' + err.message);
                                                }
                                            }} disabled={!enhancedEnabled} />
                                            <span className="text-xs">Animation</span>
                                        </label>
                                    </div>
                                    <div className="text-xs text-slate-400">
                                        Image v{expandedImage.version} · {inferDiagramType(expandedImage.file_path)}
                                        {diagramProvider(expandedImage) ? ` · ${diagramProvider(expandedImage)}` : ''}
                                    </div>
                                </div>
                                <div style={{ textAlign: 'center' }}>
                                    {currentSvgKey && expandedSvgMap[currentSvgKey] ? (
                                        <DiagramViewer
                                            key={`${currentSvgKey}-${inlineSvgToken}`}
                                            className="inline-diagram inline-diagram--modal"
                                            svgMarkup={expandedSvgMap[currentSvgKey]}
                                            onBlockSelect={(blockId) => expandedImage && openFeedback(expandedImage.id, blockId)}
                                        />
                                    ) : (
                                        <div className="text-sm text-slate-400">Loading inline SVG…</div>
                                    )}
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            ) : null}
            <FeedbackModal
                open={feedbackOpen}
                blockId={feedbackBlockId}
                onClose={() => setFeedbackOpen(false)}
                onSubmit={submitFeedback}
            />
        </div>
    );
}
