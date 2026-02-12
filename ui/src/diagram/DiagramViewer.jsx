
export default function DiagramViewer({ svgMarkup, className = '', onBlockSelect, dataCy }) {
    if (!svgMarkup) return null;
    return (
        <div
            data-cy={dataCy}
            className={className}
            onClick={(e) => {
                if (!onBlockSelect) return;
                const target = e.target.closest('[data-block-id]');
                if (target) {
                    const blockId = target.getAttribute('data-block-id');
                    if (blockId) {
                        e.stopPropagation();
                        onBlockSelect(blockId);
                    }
                }
            }}
            dangerouslySetInnerHTML={{ __html: svgMarkup }}
        />
    );
}
