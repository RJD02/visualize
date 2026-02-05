import { useMemo, useState, useEffect } from 'react';

const inferDiagramType = (filePath) => {
    if (!filePath) return 'diagram';
    const name = (filePath.split('/').pop() || '').replace(/\.(png|svg)$/i, '');
    const parts = name.split('_');
    if (parts.length >= 3) {
        return parts.slice(1, -1).join('_');
    }
    return 'diagram';
};

export default function App() {
    const [files, setFiles] = useState([]);
    const [sessionId, setSessionId] = useState(null);
    const [messages, setMessages] = useState([]);
    const [images, setImages] = useState([]);
    const [diagrams, setDiagrams] = useState([]);
    const [sourceRepo, setSourceRepo] = useState(null);
    const [sourceCommit, setSourceCommit] = useState(null);
    const [inputMsg, setInputMsg] = useState('');
    const [loading, setLoading] = useState(false);
    const [expandedImage, setExpandedImage] = useState(null);
    const [animationEnabled, setAnimationEnabled] = useState(false);
    const [enhancedEnabled, setEnhancedEnabled] = useState(true);
    const [expandedSvgMap, setExpandedSvgMap] = useState({});
    const [inlineSvgEnabled, setInlineSvgEnabled] = useState(true);
    const [irMap, setIrMap] = useState({});
    const [irOpen, setIrOpen] = useState({});
    const [irSaving, setIrSaving] = useState({});
    const [errorMsg, setErrorMsg] = useState('');
    const [inlineSvgToken, setInlineSvgToken] = useState(0);

    const extractGithubUrl = (value) => {
        if (!value) return null;
        const match = value.match(/https?:\/\/github\.com\/[\w.-]+\/[\w.-]+/i);
        return match ? match[0] : null;
    };

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

    const normalizeSvg = (svg) => {
        if (!svg) return svg;
        return svg.replace(/xmlns=\"\"([^\"]+)\"\"/g, 'xmlns="$1"');
    };

    const svgCacheKey = (imageId, animated, enhanced) => `${imageId}:${animated ? 'anim' : 'static'}:${enhanced ? 'enhanced' : 'original'}`;

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

    const fetchDiagramSvg = async (imageId, animated, enhanced) => {
        const url = `/api/diagram/render?format=svg&animated=${animated ? 'true' : 'false'}&enhanced=${enhanced ? 'true' : 'false'}&image_id=${imageId}`;
        const data = await fetchJson(url, { method: 'GET' });
        if (data && data.svg) data.svg = normalizeSvg(data.svg);
        return data;
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

    const toggleIr = async (imageId) => {
        if (!imageId) return;
        if (irOpen[imageId]) {
            setIrOpen((prev) => ({ ...prev, [imageId]: false }));
            return;
        }
        if (!irMap[imageId]) {
            const res = await fetch(`/api/images/${imageId}/ir`);
            if (res.ok) {
                const data = await res.json();
                setIrMap((prev) => ({ ...prev, [imageId]: data.svg_text }));
            } else {
                setIrMap((prev) => ({ ...prev, [imageId]: 'IR not available.' }));
            }
        }
        setIrOpen((prev) => ({ ...prev, [imageId]: true }));
    };

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
    const sortedImages = useMemo(() => {
        return [...(images || [])].sort((a, b) => {
            if (a.version != null && b.version != null) return a.version - b.version;
            const aTime = a.created_at ? new Date(a.created_at).getTime() : 0;
            const bTime = b.created_at ? new Date(b.created_at).getTime() : 0;
            return aTime - bTime;
        });
    }, [images]);

    const currentSvgKey = expandedImage ? svgCacheKey(expandedImage.id, animationEnabled, enhancedEnabled) : null;

    const createSession = async () => {
        const data = await fetchJson('/api/sessions', { method: 'POST' });
        setSessionId(data.session_id);
        return data.session_id;
    };

    const refreshSession = async (id) => {
        const data = await fetchJson(`/api/sessions/${id}`);
        setMessages(data.messages || []);
        setImages(data.images || []);
        setDiagrams(data.diagrams || []);
        setSourceRepo(data.source_repo || null);
        setSourceCommit(data.source_commit || null);
        return data;
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
            const wantsShowIr = /show\s+i\s*r|show\s+ir|show\s+the\s+ir/.test(lowered);

            if (lastImage && (wantsAnimate || wantsShowIr)) {
                setExpandedImage(lastImage);
            }
            if (lastImage && wantsAnimate) {
                setInlineSvgEnabled(true);
                setEnhancedEnabled(true);
                setAnimationEnabled(true);
                try {
                    const data = await fetchDiagramSvg(lastImage.id, true, true);
                    const key = svgCacheKey(lastImage.id, true, true);
                    setExpandedSvgMap((p) => ({ ...p, [key]: data.svg }));
                    setInlineSvgToken((v) => v + 1);
                } catch (e) { /* ignore */ }
            }
            if (lastImage && wantsShowIr) {
                try {
                    await toggleIr(lastImage.id);
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
            <div className="max-w-6xl mx-auto px-6 py-6">
                <div className="flex items-center justify-between mb-5">
                    <div className="flex items-center gap-4">
                        <div className="text-2xl font-semibold tracking-tight">Architecture Copilot</div>
                        <div className="flex items-center gap-1 text-xs bg-slate-900 border border-slate-800 rounded-lg p-1">
                            <button
                                className={`px-2 py-1 rounded ${!enhancedEnabled ? 'bg-slate-700 text-white' : 'text-slate-300 hover:text-white'}`}
                                onClick={async () => {
                                    setEnhancedEnabled(false);
                                    setAnimationEnabled(false);
                                    if (!expandedImage || !inlineSvgEnabled) return;
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
                                    if (!expandedImage || !inlineSvgEnabled) return;
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
                                if (on) setInlineSvgEnabled(true);
                                // if currently showing inline svg for an expanded image, refresh it to match new mode
                                if (expandedImage && inlineSvgEnabled) {
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
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                    <div className="flex flex-col h-[82vh]">
                        <div className="bg-slate-900/60 rounded-2xl p-4 border border-slate-800 flex-1 flex flex-col min-h-0">
                            <div className="flex items-center justify-between mb-3">
                                <div className="text-sm font-semibold">Chat</div>
                                <div className="text-[11px] text-slate-400">Share a story, architecture, or GitHub link.</div>
                            </div>
                            <div className="flex-1 overflow-y-auto space-y-5 text-sm pr-2 min-h-0">
                                {messages.length ? (
                                    messages.map((m, idx) => (
                                        <div key={m.id || idx} className={m.role === 'user' ? 'text-indigo-200' : 'text-slate-200'}>
                                            <div className="text-[11px] uppercase tracking-wide text-slate-500">{m.role}</div>
                                            {m.content ? <div className="mt-1 whitespace-pre-wrap">{m.content}</div> : null}
                                            {(m.message_type === 'image' || m.image_id) && imageMap.get(m.image_id) ? (
                                                <div className="mt-3 rounded-xl border border-slate-800 bg-slate-950/60 p-3">
                                                    <div className="text-[11px] text-slate-500">
                                                        Image v{m.image_version || imageMap.get(m.image_id).version} · {m.diagram_type || inferDiagramType(imageMap.get(m.image_id).file_path)}
                                                    </div>
                                                    <img
                                                        src={`${imageMap.get(m.image_id).file_path}?v=${m.image_version || imageMap.get(m.image_id).version}`}
                                                        className="mt-2 rounded-lg border border-slate-800 max-w-full cursor-zoom-in"
                                                        onClick={() => setExpandedImage(imageMap.get(m.image_id))}
                                                    />
                                                    <button
                                                        className="mt-3 text-xs text-indigo-300 hover:text-indigo-200"
                                                        onClick={() => toggleIr(m.image_id)}
                                                    >
                                                        {irOpen[m.image_id] ? 'Hide IR' : 'Show IR'}
                                                    </button>
                                                    <div className="mt-2 flex gap-2">
                                                        <button
                                                            className="text-xs text-indigo-300 hover:text-indigo-200"
                                                            onClick={async () => {
                                                                const img = imageMap.get(m.image_id);
                                                                if (!img) return;
                                                                setExpandedImage(img);
                                                                setInlineSvgEnabled(true);
                                                                setEnhancedEnabled(true);
                                                                setAnimationEnabled(true);
                                                                try {
                                                                    const data = await fetchDiagramSvg(img.id, true, true);
                                                                    const key = svgCacheKey(img.id, true, true);
                                                                    setExpandedSvgMap((p) => ({ ...p, [key]: data.svg }));
                                                                } catch (e) { /* ignore */ }
                                                            }}
                                                        >
                                                            Animate
                                                        </button>
                                                        <button
                                                            className="text-xs text-indigo-300 hover:text-indigo-200"
                                                            onClick={async () => {
                                                                const img = imageMap.get(m.image_id);
                                                                if (!img) return;
                                                                setExpandedImage(img);
                                                                setInlineSvgEnabled(true);
                                                                setEnhancedEnabled(true);
                                                                setAnimationEnabled(false);
                                                                try {
                                                                    const data = await fetchDiagramSvg(img.id, false, true);
                                                                    const key = svgCacheKey(img.id, false, true);
                                                                    setExpandedSvgMap((p) => ({ ...p, [key]: data.svg }));
                                                                } catch (e) { /* ignore */ }
                                                            }}
                                                        >
                                                            Inline
                                                        </button>
                                                    </div>
                                                    {irOpen[m.image_id] ? (
                                                        <div className="mt-2">
                                                            <textarea
                                                                className="w-full text-[11px] whitespace-pre-wrap bg-slate-950 border border-slate-800 rounded-lg p-2 max-h-48 overflow-auto"
                                                                style={{ minHeight: 120 }}
                                                                value={irMap[m.image_id] || ''}
                                                                onChange={(e) => setIrMap((prev) => ({ ...prev, [m.image_id]: e.target.value }))}
                                                            />
                                                            <div className="mt-2 flex gap-2">
                                                                <button
                                                                    className="text-xs text-emerald-300 hover:text-emerald-200"
                                                                    onClick={() => saveEditedIR(m.image_id)}
                                                                    disabled={irSaving[m.image_id]}
                                                                >
                                                                    {irSaving[m.image_id] ? 'Saving...' : 'Save IR'}
                                                                </button>
                                                            </div>
                                                        </div>
                                                    ) : null}
                                                </div>
                                            ) : null}
                                        </div>
                                    ))
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
                    <div className="bg-slate-900/60 rounded-2xl p-4 border border-slate-800 h-[82vh] overflow-y-auto">
                        <div className="text-sm font-semibold mb-2">Diagram History</div>
                        <div className="text-xs text-slate-400 mb-4">All diagrams are shown inline in chat. Click any image to expand.</div>
                        {sortedImages.length ? (
                            <div className="space-y-4">
                                {sortedImages.map((img) => (
                                    <div key={img.id} className="rounded-xl border border-slate-800 bg-slate-950/60 p-3">
                                        <div className="text-[11px] text-slate-500">
                                            Image v{img.version} · {inferDiagramType(img.file_path)}
                                        </div>
                                        <img
                                            src={`${img.file_path}?v=${img.version}`}
                                            className="mt-2 rounded-lg border border-slate-800 max-w-full cursor-zoom-in"
                                            onClick={() => setExpandedImage(img)}
                                        />
                                        <button
                                            className="mt-3 text-xs text-indigo-300 hover:text-indigo-200"
                                            onClick={() => toggleIr(img.id)}
                                        >
                                            {irOpen[img.id] ? 'Hide IR' : 'Show IR'}
                                        </button>
                                        <div className="mt-2 flex gap-2">
                                            <button
                                                className="text-xs text-indigo-300 hover:text-indigo-200"
                                                onClick={async () => {
                                                    setExpandedImage(img);
                                                    setInlineSvgEnabled(true);
                                                    setEnhancedEnabled(true);
                                                    setAnimationEnabled(true);
                                                    try {
                                                        const data = await fetchDiagramSvg(img.id, true, true);
                                                        const key = svgCacheKey(img.id, true, true);
                                                        setExpandedSvgMap((p) => ({ ...p, [key]: data.svg }));
                                                    } catch (e) { /* ignore */ }
                                                }}
                                            >
                                                Animate
                                            </button>
                                            <button
                                                className="text-xs text-indigo-300 hover:text-indigo-200"
                                                onClick={async () => {
                                                    setExpandedImage(img);
                                                    setInlineSvgEnabled(true);
                                                    setEnhancedEnabled(true);
                                                    setAnimationEnabled(false);
                                                    try {
                                                        const data = await fetchDiagramSvg(img.id, false, true);
                                                        const key = svgCacheKey(img.id, false, true);
                                                        setExpandedSvgMap((p) => ({ ...p, [key]: data.svg }));
                                                    } catch (e) { /* ignore */ }
                                                }}
                                            >
                                                Inline
                                            </button>
                                        </div>
                                        {irOpen[img.id] ? (
                                            <div className="mt-2">
                                                <textarea
                                                    className="w-full text-[11px] whitespace-pre-wrap bg-slate-950 border border-slate-800 rounded-lg p-2 max-h-48 overflow-auto"
                                                    style={{ minHeight: 120 }}
                                                    value={irMap[img.id] || ''}
                                                    onChange={(e) => setIrMap((prev) => ({ ...prev, [img.id]: e.target.value }))}
                                                />
                                                <div className="mt-2 flex gap-2">
                                                    <button
                                                        className="text-xs text-emerald-300 hover:text-emerald-200"
                                                        onClick={() => saveEditedIR(img.id)}
                                                        disabled={irSaving[img.id]}
                                                    >
                                                        {irSaving[img.id] ? 'Saving...' : 'Save IR'}
                                                    </button>
                                                </div>
                                            </div>
                                        ) : null}
                                    </div>
                                ))}
                            </div>
                        ) : (
                            <div className="text-slate-500 text-sm">No diagrams yet. Generate one to populate history.</div>
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
                                                    if (!expandedImage || !inlineSvgEnabled) return;
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
                                                    if (!expandedImage || !inlineSvgEnabled) return;
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
                                                if (on) setInlineSvgEnabled(true);
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
                                        <label className="flex items-center gap-2 text-sm">
                                            <input type="checkbox" checked={inlineSvgEnabled} onChange={async (e) => {
                                                const on = e.target.checked;
                                                setInlineSvgEnabled(on);
                                                if (!expandedImage) return;
                                                if (!on) {
                                                    // switching back to <img>, keep svg cached but don't render inline
                                                    return;
                                                }
                                                // ensure we have an inline svg to render; fetch static or animated depending on animationEnabled
                                                try {
                                                    const data = await fetchDiagramSvg(expandedImage.id, animationEnabled, enhancedEnabled);
                                                    const key = svgCacheKey(expandedImage.id, animationEnabled, enhancedEnabled);
                                                    setExpandedSvgMap((p) => ({ ...p, [key]: data.svg }));
                                                } catch (err) {
                                                    alert('Render failed: ' + err.message);
                                                }
                                            }} />
                                            <span className="text-xs">Inline SVG</span>
                                        </label>
                                    </div>
                                    <div className="text-xs text-slate-400">
                                        Image v{expandedImage.version} · {inferDiagramType(expandedImage.file_path)}
                                    </div>
                                </div>
                                <div style={{ textAlign: 'center' }}>
                                    {inlineSvgEnabled && currentSvgKey && expandedSvgMap[currentSvgKey] ? (
                                        <div
                                            key={`${currentSvgKey}-${inlineSvgToken}`}
                                            dangerouslySetInnerHTML={{ __html: expandedSvgMap[currentSvgKey] }}
                                        />
                                    ) : (
                                        <img
                                            key={`${expandedImage.id}-${expandedImage.version}`}
                                            src={`${expandedImage.file_path}?v=${expandedImage.version}`}
                                            className="block"
                                            style={{
                                                maxWidth: '100%',
                                                width: '100%',
                                                height: 'auto',
                                                display: 'block',
                                            }}
                                            alt={`Image v${expandedImage.version}`}
                                        />
                                    )}
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            ) : null}
        </div>
    );
}
