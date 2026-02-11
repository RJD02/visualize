const PROMPT = `https://github.com/RJD02/job-portal-go\nCan you generate a diagram with orange and blue blocks, for this GitHub repo`;

const ORANGE_SWATCHES = ['#FFA500', '#ff9800', 'rgb(255, 165, 0)'];
const BLUE_SWATCHES = ['#0000FF', '#2196f3', 'rgb(33, 150, 243)'];
const ORANGE_REGEX = /#FFA500|#ff9800|rgb\(255,\s*165,\s*0\)/i;
const BLUE_REGEX = /#0000FF|#2196f3|rgb\(33,\s*150,\s*243\)/i;

const escapeRegex = (value: string) => value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

const findTokens = (svgText: string, tokens: string[]) =>
    tokens.filter((token) => new RegExp(escapeRegex(token), 'i').test(svgText));

const buildDiagnosticReport = (params: {
    inlineSvg: boolean;
    inlineImgCount: number;
    styleTagPresent: boolean;
    svgText: string;
    orangeTokens: string[];
    blueTokens: string[];
    missing: string[];
}) => {
    const { inlineSvg, inlineImgCount, styleTagPresent, svgText, orangeTokens, blueTokens, missing } = params;
    const lines = [
        '❌ Diagram styling verification failed',
        `  • SVG inline: ${inlineSvg ? 'YES' : 'NO'}`,
        `  • <img> detected: ${inlineImgCount > 0 ? 'YES' : 'NO'}`,
        `  • <style> in SVG: ${styleTagPresent ? 'YES' : 'NO'}`,
        `  • Found colors: ${[...orangeTokens, ...blueTokens].filter(Boolean).join(', ') || 'None'}`,
        `  • Missing requested colors: ${missing.join(', ')}`,
        '',
        'SVG snippet:',
        svgText.slice(0, 500),
        '',
        'Codex Self-Debug: Inspect this report to decide whether styling intent extraction, the styling agent plan, SVG embedding, or inline rendering regressed before proposing a fix and re-running the suite.',
    ];
    return lines.join('\n');
};

describe('Diagram styling regression', () => {
    it('renders inline SVG with requested orange and blue colors', () => {
        cy.visit('/');

        cy.get('[data-cy="chat-input"]').should('be.visible').clear().type(PROMPT, { delay: 0 });
        cy.get('[data-cy="send-button"]').should('be.enabled').click();

        cy.log('Waiting for inline SVG diagram to appear');
        cy.get('[data-cy="diagram-history-panel"] [data-cy="inline-diagram"]', { timeout: 240000 }).should('exist');
        cy.get('[data-cy="diagram-history-panel"] img', { timeout: 0 }).should('not.exist');

        cy.get('[data-cy="diagram-history-panel"] [data-cy="inline-diagram"]').last().then(($container) => {
            const svgText = ($container.html() || '').trim();
            const inlineSvg = /<svg[\s>]/i.test(svgText);
            const inlineImgCount = Cypress.$('[data-cy="diagram-history-panel"] img').length;
            const styleTagPresent = /<style[\s\S]*?>/i.test(svgText);
            const orangeTokens = findTokens(svgText, ORANGE_SWATCHES);
            const blueTokens = findTokens(svgText, BLUE_SWATCHES);
            const hasOrange = ORANGE_REGEX.test(svgText);
            const hasBlue = BLUE_REGEX.test(svgText);

            if (!inlineSvg || !hasOrange || !hasBlue) {
                const missing: string[] = [];
                if (!inlineSvg) missing.push('INLINE_SVG');
                if (!hasOrange) missing.push('ORANGE');
                if (!hasBlue) missing.push('BLUE');
                const report = buildDiagnosticReport({
                    inlineSvg,
                    inlineImgCount,
                    styleTagPresent,
                    svgText,
                    orangeTokens,
                    blueTokens,
                    missing,
                });
                return cy.task('log', report).then(() => {
                    throw new Error('Inline SVG missing requested colors or structure');
                });
            }

            cy.log('✅ Diagram styling verification passed: inline SVG contains requested orange and blue colors.');
        });
    });
});
