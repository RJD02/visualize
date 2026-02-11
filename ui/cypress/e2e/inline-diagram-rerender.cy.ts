const SESSION_ID = 'cypress-session-stable';
const IMAGE_ID = 'cypress-image-001';

const SAMPLE_SVG = `<?xml version="1.0" encoding="UTF-8"?>
<svg width="200" height="120" viewBox="0 0 200 120" xmlns="http://www.w3.org/2000/svg">
    <rect x="10" y="20" width="80" height="40" fill="#4f46e5" stroke="#1e1b4b" stroke-width="2" />
    <rect x="110" y="20" width="80" height="40" fill="#14b8a6" stroke="#0f766e" stroke-width="2" />
    <text x="50" y="50" font-size="10" fill="#fff" text-anchor="middle">API</text>
    <text x="150" y="50" font-size="10" fill="#fff" text-anchor="middle">DB</text>
</svg>`;

const buildSessionPayload = () => {
    const now = new Date().toISOString();
    return {
        session_id: SESSION_ID,
        messages: [
            {
                id: 'msg-user-1',
                role: 'user',
                content: 'Generate a component diagram',
                created_at: now,
            },
            {
                id: 'msg-assistant-1',
                role: 'assistant',
                content: 'Here is the latest diagram',
                created_at: now,
                message_type: 'image',
                image_id: IMAGE_ID,
                image_version: 1,
                diagram_type: 'component',
            },
        ],
        images: [
            {
                id: IMAGE_ID,
                version: 1,
                file_path: `/outputs/${IMAGE_ID}_component_1.svg`,
                created_at: now,
                diagram_type: 'component',
            },
        ],
        diagrams: [],
        plans: [],
        source_repo: null,
        source_commit: null,
    };
};

declare global {
    interface Window {
        __inlineDiagramRenderCounts?: Record<string, number>;
    }
}

describe('Inline diagram render stability', () => {
    it('does not re-render inline diagrams when typing into the chat input', () => {
        cy.intercept('POST', '/api/sessions', { session_id: SESSION_ID }).as('createSession');
        cy.intercept('POST', `/api/sessions/${SESSION_ID}/messages`, { id: 'msg-new' }).as('sendMessage');
        cy.intercept('GET', `/api/sessions/${SESSION_ID}`, (req) => {
            req.reply(buildSessionPayload());
        }).as('fetchSession');
        cy.intercept('GET', '/api/diagram/render*', { svg: SAMPLE_SVG }).as('renderSvg');

        cy.visit('/');

        cy.get('[data-cy="chat-input"]').as('chatInput').should('be.visible').clear().type('Please create a diagram', { delay: 0 });
        cy.get('[data-cy="send-button"]').should('be.enabled').click();

        cy.wait(['@createSession', '@sendMessage', '@fetchSession']);
        cy.wait('@renderSvg');

        cy.get('[data-cy="diagram-history-panel"] [data-cy="inline-diagram"]', { timeout: 10000 }).should('exist');

        cy.get('[data-cy="diagram-history-panel"] [data-cy="inline-diagram"]').last().invoke('attr', 'data-image-id').then((attr) => {
            const diagramId = attr as string | null;
            expect(diagramId, 'inline diagram id attribute').to.be.a('string').and.not.be.empty;

            cy.window().then((win) => {
                const baseline = win.__inlineDiagramRenderCounts?.[diagramId as string] || 0;
                expect(baseline, 'baseline render count').to.be.greaterThan(0);
                cy.wrap({ diagramId: diagramId as string, baseline }).as('renderSnapshot');
            });
        });

        const typingSequence = 'render-fidelity-check-12345';
        cy.get('@chatInput').clear().type(typingSequence, { delay: 0 });

        cy.wait(200);

        cy.get('@renderSnapshot').then(({ diagramId, baseline }: { diagramId: string; baseline: number }) => {
            cy.window().then((win) => {
                const after = win.__inlineDiagramRenderCounts?.[diagramId] || 0;
                expect(after, 'render count after typing').to.equal(baseline);
            });
        });
    });
});

export {};
