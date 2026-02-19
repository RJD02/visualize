/**
 * App.jsx — specs_v42: Unified Chat Architecture
 *
 * Single chat window. All output (diagram, animation, analysis, text, actions)
 * rendered as typed blocks inside message bubbles. No panels, no modal overlays.
 * All interactions go through POST /api/chat.
 */
import React, { memo, useEffect, useRef, useState } from 'react';
import DiagramViewer from './diagram/DiagramViewer.jsx';
import FeedbackModal from './diagram/FeedbackModal.jsx';
import TestDiagramPage from './__test__/TestDiagramPage.jsx';

// ---------------------------------------------------------------------------
// Utilities
// ---------------------------------------------------------------------------

const normalizeSvg = (svg) => {
    if (!svg) return svg;
    return svg
        .replace(/xmlns=""([^"]+)""/g, 'xmlns="$1"')
        .replace(/<\s*ns\d+:/gi, '<')
        .replace(/<\/\s*ns\d+:/gi, '</')
        .replace(/\s+xmlns:ns\d+="[^"]*"/gi, '');
};

const svgCacheKey = (imageId, animated, enhanced) =>
    `${imageId}:${animated ? 'anim' : 'static'}:${enhanced ? 'enhanced' : 'original'}`;

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
        if (err && err.name === 'AbortError') throw new Error('Request timed out. Please try again.');
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

// ---------------------------------------------------------------------------
// InlineDiagram — fetches and caches SVG, unchanged from original
// ---------------------------------------------------------------------------

const InlineDiagram = memo(
    ({ image, className = '', onClick, enhanced = true, cacheRef, animated = false, onBlockSelect }) => {
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
            return () => { cancelled = true; };
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
    },
    (prev, next) => {
        const prevImage = prev.image || {};
        const nextImage = next.image || {};
        const sameImage = prevImage.id === nextImage.id && prevImage.version === nextImage.version;
        return (
            sameImage &&
            prev.enhanced === next.enhanced &&
            prev.animated === next.animated &&
            prev.className === next.className &&
            prev.cacheRef === next.cacheRef
        );
    }
);

// ---------------------------------------------------------------------------
// Block renderers — one per block_type
// ---------------------------------------------------------------------------

// If the test route is requested, render deterministic test page (dev-only)
if (typeof window !== 'undefined' && window.location && window.location.pathname === '/__test/diagram') {
    const root = document.getElementById('root');
    // Render minimal React root for the test page
    import('react-dom/client').then(({ createRoot }) => {
        createRoot(root).render(React.createElement(TestDiagramPage));
    });
}


/** block_type: "text" — render markdown-like text */
function TextBlock({ payload }) {
    const text = payload?.markdown || payload?.text || '';
    if (!text) return null;
    return (
        <div className="mt-1 whitespace-pre-wrap text-slate-100 text-sm leading-relaxed">
            {text}
        </div>
    );
}

/** block_type: "diagram" — renders SVG inline via InlineDiagram */
function DiagramBlock({ payload, cacheRef, onBlockSelect }) {
    const imageId = payload?.image_id;
    const diagramType = payload?.diagram_type || 'diagram';
    const irVersion = payload?.ir_version;
    if (!imageId) return null;
    // Construct a minimal image-like object for InlineDiagram
    const imageObj = { id: imageId, version: irVersion ?? 1, diagram_type: diagramType };
    return (
        <div className="mt-3 rounded-xl border border-slate-800 bg-slate-950/60 p-3">
            <div className="text-[11px] text-slate-500 mb-1">
                {diagramType}{irVersion != null ? ` · v${irVersion}` : ''}
            </div>
            <InlineDiagram
                image={imageObj}
                className="max-w-full"
                cacheRef={cacheRef}
                animated={false}
                enhanced={true}
                onBlockSelect={onBlockSelect ? (blockId) => onBlockSelect(imageId, blockId) : undefined}
            />
        </div>
    );
}

/** block_type: "animation" — same as diagram but animated=true */
function AnimationBlock({ payload, cacheRef, onBlockSelect }) {
    const imageId = payload?.image_id;
    const diagramType = payload?.diagram_type || 'diagram';
    const irVersion = payload?.ir_version;
    if (!imageId) return null;
    const imageObj = { id: imageId, version: irVersion ?? 1, diagram_type: diagramType };
    return (
        <div className="mt-3 rounded-xl border border-indigo-900 bg-slate-950/60 p-3">
            <div className="text-[11px] text-indigo-400 mb-1">
                Animated · {diagramType}
            </div>
            <InlineDiagram
                image={imageObj}
                className="max-w-full"
                cacheRef={cacheRef}
                animated={true}
                enhanced={true}
                onBlockSelect={onBlockSelect ? (blockId) => onBlockSelect(imageId, blockId) : undefined}
            />
        </div>
    );
}

/** block_type: "analysis" — structured analysis card */
function AnalysisBlock({ payload }) {
    const score = payload?.score ?? payload?.quality_score ?? null;
    const issues = Array.isArray(payload?.issues) ? payload.issues : [];
    const patches = Array.isArray(payload?.suggested_patches) ? payload.suggested_patches : [];
    return (
        <div className="mt-3 rounded-xl border border-amber-900 bg-slate-950/60 p-3 text-sm">
            <div className="text-[11px] uppercase tracking-wide text-amber-400 mb-2">Architecture Analysis</div>
            {score != null && (
                <div className="flex items-center gap-2 mb-2">
                    <span className="text-slate-300 text-xs">Quality Score:</span>
                    <span className={`font-semibold ${score >= 80 ? 'text-emerald-400' : score >= 50 ? 'text-amber-400' : 'text-rose-400'}`}>
                        {typeof score === 'number' ? score.toFixed(1) : score}
                    </span>
                </div>
            )}
            {issues.length > 0 && (
                <div className="mt-2">
                    <div className="text-[11px] uppercase tracking-wide text-slate-400 mb-1">Issues</div>
                    <ul className="space-y-1">
                        {issues.map((issue, i) => (
                            <li key={i} className="text-xs text-rose-300 bg-rose-950/30 rounded px-2 py-1">
                                {typeof issue === 'string' ? issue : JSON.stringify(issue)}
                            </li>
                        ))}
                    </ul>
                </div>
            )}
            {patches.length > 0 && (
                <div className="mt-2">
                    <div className="text-[11px] uppercase tracking-wide text-slate-400 mb-1">Suggested Patches</div>
                    <ul className="space-y-1">
                        {patches.map((patch, i) => (
                            <li key={i} className="text-xs text-emerald-300 bg-emerald-950/30 rounded px-2 py-1">
                                {typeof patch === 'string' ? patch : JSON.stringify(patch)}
                            </li>
                        ))}
                    </ul>
                </div>
            )}
        </div>
    );
}

/** block_type: "action" — clickable action buttons */
function ActionBlock({ payload, onAction }) {
    const actions = Array.isArray(payload?.actions) ? payload.actions : [];
    const label = payload?.label;
    if (!actions.length && !label) return null;
    return (
        <div className="mt-3 flex flex-wrap gap-2">
            {label && <span className="text-xs text-slate-400 self-center">{label}</span>}
            {actions.map((action, i) => (
                <button
                    key={i}
                    className="text-xs bg-indigo-700 hover:bg-indigo-600 text-white rounded px-3 py-1"
                    onClick={() => onAction && onAction(action)}
                >
                    {action.label || action.type || 'Action'}
                </button>
            ))}
        </div>
    );
}

// ---------------------------------------------------------------------------
// MessageBubble — renders a full chat envelope or a plain user message
// ---------------------------------------------------------------------------

function MessageBubble({ entry, cacheRef, onBlockSelect, onAction }) {
    // Plain user message (optimistic, pre-response)
    if (entry.role === 'user') {
        return (
            <div className="text-indigo-200">
                <div className="text-[11px] uppercase tracking-wide text-slate-500">you</div>
                <div className="mt-1 whitespace-pre-wrap text-sm">{entry.content}</div>
            </div>
        );
    }

    // Assistant envelope
    const envelope = entry.envelope;
    if (!envelope) return null;

    return (
        <div className="text-slate-200">
            <div className="text-[11px] uppercase tracking-wide text-slate-500">assistant</div>
            {envelope.blocks.map((block, i) => {
                switch (block.block_type) {
                    case 'text':
                        return <TextBlock key={i} payload={block.payload} />;
                    case 'diagram':
                        return (
                            <DiagramBlock
                                key={i}
                                payload={block.payload}
                                cacheRef={cacheRef}
                                onBlockSelect={onBlockSelect}
                            />
                        );
                    case 'animation':
                        return (
                            <AnimationBlock
                                key={i}
                                payload={block.payload}
                                cacheRef={cacheRef}
                                onBlockSelect={onBlockSelect}
                            />
                        );
                    case 'analysis':
                        return <AnalysisBlock key={i} payload={block.payload} />;
                    case 'action':
                        return <ActionBlock key={i} payload={block.payload} onAction={onAction} />;
                    default:
                        return null;
                }
            })}
        </div>
    );
}

// ---------------------------------------------------------------------------
// App — root component
// ---------------------------------------------------------------------------

export default function App() {
    const [files, setFiles] = useState([]);
    const [sessionId, setSessionId] = useState(null);
    // chatMessages: array of { role:'user', content } | { role:'assistant', envelope: ChatEnvelope }
    const [chatMessages, setChatMessages] = useState([]);
    const [inputMsg, setInputMsg] = useState('');
    const [loading, setLoading] = useState(false);
    const [errorMsg, setErrorMsg] = useState('');
    const [feedbackOpen, setFeedbackOpen] = useState(false);
    const [feedbackImageId, setFeedbackImageId] = useState(null);
    const [feedbackBlockId, setFeedbackBlockId] = useState(null);
    const inlineSvgCacheRef = useRef({});
    const messagesEndRef = useRef(null);

    // Clear SVG cache when session changes
    useEffect(() => {
        inlineSvgCacheRef.current = {};
    }, [sessionId]);

    // Auto-scroll to bottom on new messages
    useEffect(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [chatMessages]);

    // Restore session from URL param
    useEffect(() => {
        if (typeof window === 'undefined') return;
        const params = new URLSearchParams(window.location.search);
        const seedSession = params.get('session');
        if (seedSession) {
            setSessionId(seedSession);
        }
    }, []);

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
            setFeedbackOpen(false);
        } catch (err) {
            alert('Feedback failed: ' + (err?.message || err));
        }
    };

    const sendMessage = async () => {
        if (!inputMsg.trim()) return;
        setLoading(true);
        setErrorMsg('');

        const rawMessage = inputMsg;

        // Optimistic user message
        setChatMessages((prev) => [...prev, { role: 'user', content: rawMessage }]);
        setInputMsg('');
        setFiles([]);

        try {
            // Resolve or create session
            let activeSessionId = sessionId;
            if (!activeSessionId) {
                const sessionData = await fetchJson('/api/sessions', { method: 'POST' });
                activeSessionId = sessionData.session_id;
                setSessionId(activeSessionId);
            }

            // Ingest files / GitHub URL if provided
            const ghUrl = extractGithubUrl(rawMessage);
            if (files.length || ghUrl) {
                const form = new FormData();
                form.append('text', rawMessage);
                for (const f of files) form.append('files', f);
                if (ghUrl) form.append('github_url', ghUrl);
                await fetchJson(`/api/sessions/${activeSessionId}/ingest`, { method: 'POST', body: form });
            }

            // Single orchestration call
            const envelope = await fetchJson('/api/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: rawMessage, session_id: activeSessionId }),
            });

            // Update sessionId from envelope (in case it was auto-created)
            if (envelope?.session_id && !sessionId) {
                setSessionId(envelope.session_id);
            }

            // Append assistant envelope message
            setChatMessages((prev) => [...prev, { role: 'assistant', envelope }]);
        } catch (err) {
            setErrorMsg(err?.message || 'Failed to send message.');
            // Remove optimistic user message on failure
            setChatMessages((prev) => prev.slice(0, -1));
        } finally {
            setLoading(false);
        }
    };

    const handleKeyDown = (e) => {
        if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
            sendMessage();
        }
    };

    return (
        <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col">
            {/* Header */}
            <div className="border-b border-slate-800 px-6 py-3 flex items-center justify-between shrink-0">
                <div className="text-xl font-semibold tracking-tight">Architecture Copilot</div>
                <div className="text-xs text-slate-500">
                    {sessionId ? `Session: ${sessionId.slice(0, 8)}…` : 'No session yet'}
                </div>
            </div>

            {/* Chat window — fills remaining height */}
            <div className="flex-1 flex flex-col max-w-4xl w-full mx-auto px-4 py-4 min-h-0">
                {/* Message list */}
                <div className="flex-1 overflow-y-auto space-y-6 pr-2 min-h-0">
                    {chatMessages.length === 0 && (
                        <div className="text-slate-500 text-sm mt-8 text-center">
                            Describe a system, paste a GitHub URL, or upload a file to get started.
                        </div>
                    )}
                    {chatMessages.map((entry, idx) => (
                        <MessageBubble
                            key={idx}
                            entry={entry}
                            cacheRef={inlineSvgCacheRef}
                            onBlockSelect={openFeedback}
                            onAction={(action) => {
                                // Action blocks can trigger chat messages
                                if (action?.type === 'send_message' && action?.message) {
                                    setInputMsg(action.message);
                                }
                            }}
                        />
                    ))}
                    <div ref={messagesEndRef} />
                </div>

                {/* Error */}
                {errorMsg && (
                    <div className="mt-3 text-xs text-rose-300 bg-rose-950/40 border border-rose-900 rounded-lg p-2">
                        {errorMsg}
                    </div>
                )}

                {/* Input bar */}
                <div className="mt-4 shrink-0">
                    <textarea
                        data-cy="chat-input"
                        className="w-full rounded-lg bg-slate-900 border border-slate-800 p-3 text-sm resize-none focus:outline-none focus:border-indigo-700"
                        value={inputMsg}
                        onChange={(e) => setInputMsg(e.target.value)}
                        onKeyDown={handleKeyDown}
                        placeholder="Describe the diagram you want, request edits, or say 'animate this'…"
                        rows={3}
                    />
                    <div className="flex items-center justify-between mt-2">
                        <input
                            className="text-sm text-slate-400"
                            type="file"
                            multiple
                            onChange={(e) => setFiles(Array.from(e.target.files || []))}
                        />
                        <button
                            data-cy="send-button"
                            className="bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg px-5 py-2 text-sm font-medium disabled:opacity-50"
                            onClick={sendMessage}
                            disabled={loading}
                        >
                            {loading ? 'Working…' : 'Send'}
                        </button>
                    </div>
                    <div className="mt-1 text-[11px] text-slate-600">Ctrl+Enter to send</div>
                </div>
            </div>

            {/* Feedback modal — unchanged */}
            <FeedbackModal
                open={feedbackOpen}
                blockId={feedbackBlockId}
                onClose={() => setFeedbackOpen(false)}
                onSubmit={submitFeedback}
            />
        </div>
    );
}
