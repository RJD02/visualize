const PROMPT = `https://github.com/RJD02/job-portal-go\nCan you generate a diagram with black blocks, white text, and a pinkish blue background for this GitHub repo?`;

const WHITE_REGEX = /#F8F9FA|#FFFFFF|rgb\(248,\s*249,\s*250\)/i;
const BLACK_REGEX = /#000000|#0A0A0A|rgb\(0,\s*0,\s*0\)/i;
const TEXT_FILL_REGEX = /<text[^>]+fill="[^"]*(#F8F9FA|#FFFFFF)/i;
const STYLE_TEXT_REGEX = /text\s*\{[^}]*fill:\s*(#F8F9FA|#FFFFFF|rgb\(248,\s*249,\s*250\))/i;

const buildDiagnosticReport = (svgText: string, notes: string[]) => {
    const lines = [
        '❌ Diagram text color verification failed',
        `  • Notes: ${notes.join(', ')}`,
        '',
        'SVG snippet:',
        svgText.slice(0, 600),
        '',
        'Codex Self-Debug: Inspect the inline SVG snippet to diagnose whether styling intent parsing, styling plan execution, or SVG embedding regressed before retrying.',
    ];
    return lines.join('\n');
};

describe('Diagram text styling regression', () => {
    it('renders black blocks with white text when the user asks for it', () => {
        cy.visit('/');

        cy.get('[data-cy="chat-input"]').should('be.visible').clear().type(PROMPT, { delay: 0 });
        cy.get('[data-cy="send-button"]').should('be.enabled').click();

        cy.log('Waiting for inline SVG diagram to appear');
        cy.get('[data-cy="diagram-history-panel"] [data-cy="inline-diagram"]', { timeout: 240000 }).should('exist');
        cy.get('[data-cy="diagram-history-panel"] img', { timeout: 0 }).should('not.exist');

        cy.get('[data-cy="diagram-history-panel"] [data-cy="inline-diagram"]').last().then(($container) => {
            const svgText = ($container.html() || '').trim();
            const hasWhiteFill = WHITE_REGEX.test(svgText) && (TEXT_FILL_REGEX.test(svgText) || STYLE_TEXT_REGEX.test(svgText));
            const hasBlackBlocks = BLACK_REGEX.test(svgText);

            if (!hasWhiteFill || !hasBlackBlocks) {
                const notes: string[] = [];
                if (!hasWhiteFill) notes.push('WHITE_TEXT_MISSING');
                if (!hasBlackBlocks) notes.push('BLACK_BLOCKS_MISSING');
                const report = buildDiagnosticReport(svgText, notes);
                return cy.task('log', report).then(() => {
                    throw new Error('Inline SVG is missing requested white text or black blocks');
                });
            }

            cy.log('✅ Diagram text styling verification passed: white text detected inside black blocks.');
        });
    });
});
