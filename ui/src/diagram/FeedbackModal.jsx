import { useState, useEffect } from 'react';

const ACTIONS = [
    { value: 'edit_text', label: 'Edit Text' },
    { value: 'reposition', label: 'Reposition' },
    { value: 'style', label: 'Style' },
    { value: 'hide', label: 'Hide' },
    { value: 'show', label: 'Show' },
    { value: 'annotate', label: 'Annotate' },
];

export default function FeedbackModal({ open, blockId, onClose, onSubmit }) {
    const [action, setAction] = useState('edit_text');
    const [text, setText] = useState('');
    const [color, setColor] = useState('#2563eb');
    const [x, setX] = useState('');
    const [y, setY] = useState('');

    useEffect(() => {
        if (open) {
            setText('');
            setX('');
            setY('');
        }
    }, [open]);

    if (!open) return null;

    const payload = () => {
        if (action === 'edit_text') return { text };
        if (action === 'reposition') {
            const bbox = {};
            if (x !== '') bbox.x = Number(x);
            if (y !== '') bbox.y = Number(y);
            return { bbox };
        }
        if (action === 'style') return { style: { color } };
        if (action === 'annotate') return { annotations: { note: text } };
        return {};
    };

    return (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50">
            <div className="bg-slate-950 border border-slate-800 rounded-xl p-4 w-[320px]">
                <div className="text-sm text-slate-200 font-semibold">Block Feedback</div>
                <div className="text-xs text-slate-400 mt-1">Block: {blockId || 'diagram'}</div>
                <div className="mt-3">
                    <label className="text-xs text-slate-400">Action</label>
                    <select
                        id="feedback-action"
                        className="w-full mt-1 bg-slate-900 border border-slate-800 rounded px-2 py-1 text-xs"
                        value={action}
                        onChange={(e) => setAction(e.target.value)}
                    >
                        {ACTIONS.map((a) => (
                            <option key={a.value} value={a.value}>{a.label}</option>
                        ))}
                    </select>
                </div>
                {(action === 'edit_text' || action === 'annotate') && (
                    <div className="mt-3">
                        <label className="text-xs text-slate-400">Text</label>
                        <input
                            id="feedback-text"
                            className="w-full mt-1 bg-slate-900 border border-slate-800 rounded px-2 py-1 text-xs"
                            value={text}
                            onChange={(e) => setText(e.target.value)}
                        />
                    </div>
                )}
                {action === 'style' && (
                    <div className="mt-3">
                        <label className="text-xs text-slate-400">Color</label>
                        <input
                            id="feedback-color"
                            type="color"
                            className="w-full mt-1"
                            value={color}
                            onChange={(e) => setColor(e.target.value)}
                        />
                    </div>
                )}
                {action === 'reposition' && (
                    <div className="mt-3 grid grid-cols-2 gap-2">
                        <div>
                            <label className="text-xs text-slate-400">X</label>
                            <input
                                id="feedback-x"
                                className="w-full mt-1 bg-slate-900 border border-slate-800 rounded px-2 py-1 text-xs"
                                value={x}
                                onChange={(e) => setX(e.target.value)}
                            />
                        </div>
                        <div>
                            <label className="text-xs text-slate-400">Y</label>
                            <input
                                id="feedback-y"
                                className="w-full mt-1 bg-slate-900 border border-slate-800 rounded px-2 py-1 text-xs"
                                value={y}
                                onChange={(e) => setY(e.target.value)}
                            />
                        </div>
                    </div>
                )}
                <div className="mt-4 flex gap-2 justify-end">
                    <button className="text-xs text-slate-400" onClick={onClose}>Cancel</button>
                    <button
                        id="submit-feedback"
                        className="text-xs bg-indigo-600 text-white px-3 py-1 rounded"
                        onClick={() => onSubmit({ action, payload: payload() })}
                    >
                        Submit
                    </button>
                </div>
            </div>
        </div>
    );
}
