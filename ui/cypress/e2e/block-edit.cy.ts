/**
 * Block-level editing E2E tests.
 *
 * Uses the deterministic /api/demo/diagram endpoint to seed a session
 * with known blocks ("block-client" = "Client", "block-api" = "API"),
 * then exercises the FeedbackModal for edit_text, style, and hide actions.
 */

const apiBase = () => Cypress.env('API_BASE_URL') || 'http://localhost:8000';
const uiBase = () => Cypress.env('UI_BASE_URL') || 'http://localhost:8000';

/** Create a demo session via the API and return { session_id, image_id }. */
function seedDemo() {
    return cy.request(`${apiBase()}/api/demo/diagram`).then((resp) => {
        expect(resp.status).to.eq(200);
        expect(resp.body).to.have.property('session_id');
        expect(resp.body).to.have.property('image_id');
        return resp.body as { session_id: string; image_id: string };
    });
}

/** Navigate to the session and wait for the diagram to be visible. */
function openSession(sessionId: string) {
    cy.visit(`${uiBase()}/?session=${sessionId}`);
    // Wait for at least one diagram image to appear in the history panel
    cy.contains('Image v', { timeout: 30000 }).should('exist');
}

/** Click "View Diagram" to expand the modal, then wait for SVG to render. */
function expandDiagram() {
    cy.contains('View Diagram').click();
    cy.get('.inline-diagram--modal svg', { timeout: 15000 }).should('exist');
}

/** Click on a block inside the expanded modal diagram. */
function clickBlock(blockId: string) {
    cy.get(`.inline-diagram--modal [data-block-id="${blockId}"]`, { timeout: 15000 })
        .should('exist')
        .click({ force: true });
}

describe('Block-level editing', () => {
    // ──────────────────────────────────────────────
    // 1. edit_text – rename a block
    // ──────────────────────────────────────────────
    it('renames a block via edit_text feedback', () => {
        seedDemo().then(({ session_id, image_id }) => {
            openSession(session_id);
            expandDiagram();

            // Click the "block-api" block
            clickBlock('block-api');

            // FeedbackModal should appear
            cy.get('#feedback-action', { timeout: 5000 }).should('be.visible');

            // Select "Edit Text" (default) and type new name
            cy.get('#feedback-action').select('edit_text');
            cy.get('#feedback-text').clear().type('Auth Service');
            cy.get('#submit-feedback').click();

            // The updated SVG should contain the new label
            cy.contains('Auth Service', { timeout: 15000 }).should('exist');

            // Verify via IR history API that a new version was created
            cy.request(`${apiBase()}/api/ir/${image_id}/history`).then((histResp) => {
                const history = histResp.body.history || [];
                expect(history.length).to.be.greaterThan(1);
            });
        });
    });

    // ──────────────────────────────────────────────
    // 2. style – change block color
    // ──────────────────────────────────────────────
    it('changes block color via style feedback', () => {
        seedDemo().then(({ session_id, image_id }) => {
            openSession(session_id);
            expandDiagram();
            clickBlock('block-client');

            cy.get('#feedback-action', { timeout: 5000 }).should('be.visible');
            cy.get('#feedback-action').select('style');

            // The color picker should appear
            cy.get('#feedback-color', { timeout: 3000 }).should('be.visible');
            // Set color to red - must use nativeInputValueSetter to trigger React's onChange
            cy.get('#feedback-color').then(($input) => {
                const nativeSetter = Object.getOwnPropertyDescriptor(
                    window.HTMLInputElement.prototype, 'value',
                )!.set!;
                nativeSetter.call($input[0], '#ff0000');
                $input[0].dispatchEvent(new Event('input', { bubbles: true }));
                $input[0].dispatchEvent(new Event('change', { bubbles: true }));
            });
            cy.get('#submit-feedback').click();

            // After feedback the modal should close
            cy.get('#feedback-action', { timeout: 5000 }).should('not.exist');

            // Verify via IR history that a styled version was created
            cy.request(`${apiBase()}/api/ir/${image_id}/history`).then((histResp) => {
                const history: any[] = histResp.body.history || [];
                expect(history.length).to.be.greaterThan(1);
                // Latest version (first in desc order) should have the color
                const latest = history[0];
                const blocks = latest?.ir?.diagram?.blocks || [];
                const clientBlock = blocks.find((b: any) => b.id === 'block-client');
                expect(clientBlock).to.exist;
                expect(clientBlock.style).to.have.property('color', '#ff0000');
            });
        });
    });

    // ──────────────────────────────────────────────
    // 3. hide – hide a block
    // ──────────────────────────────────────────────
    it('hides a block via hide feedback', () => {
        seedDemo().then(({ session_id, image_id }) => {
            openSession(session_id);
            expandDiagram();
            clickBlock('block-api');

            cy.get('#feedback-action', { timeout: 5000 }).should('be.visible');
            cy.get('#feedback-action').select('hide');
            cy.get('#submit-feedback').click();

            // After feedback the modal should close
            cy.get('#feedback-action', { timeout: 5000 }).should('not.exist');

            // Verify via IR history that the block was hidden
            cy.request(`${apiBase()}/api/ir/${image_id}/history`).then((histResp) => {
                const history: any[] = histResp.body.history || [];
                expect(history.length).to.be.greaterThan(1);
                const latest = history[0];
                const blocks = latest?.ir?.diagram?.blocks || [];
                const apiBlock = blocks.find((b: any) => b.id === 'block-api');
                expect(apiBlock).to.exist;
                expect(apiBlock.hidden).to.eq(true);
            });
        });
    });

    // ──────────────────────────────────────────────
    // 4. Verify API-only feedback round-trip (no UI)
    // ──────────────────────────────────────────────
    it('applies edit_text feedback via direct API call', () => {
        seedDemo().then(({ session_id, image_id }) => {
            cy.request({
                method: 'POST',
                url: `${apiBase()}/api/feedback`,
                headers: { 'Content-Type': 'application/json' },
                body: {
                    diagram_id: image_id,
                    block_id: 'block-api',
                    action: 'edit_text',
                    payload: { text: 'Gateway API' },
                },
            }).then((resp) => {
                expect(resp.status).to.eq(200);
                expect(resp.body.status).to.eq('ok');
                expect(resp.body).to.have.property('image_id');

                // The returned IR should have the updated text
                const blocks = resp.body?.ir?.ir?.diagram?.blocks || [];
                const apiBlock = blocks.find((b: any) => b.id === 'block-api');
                expect(apiBlock).to.exist;
                expect(apiBlock.text).to.eq('Gateway API');
            });
        });
    });

    // ──────────────────────────────────────────────
    // 5. API-only: style feedback
    // ──────────────────────────────────────────────
    it('applies style feedback via direct API call', () => {
        seedDemo().then(({ session_id, image_id }) => {
            cy.request({
                method: 'POST',
                url: `${apiBase()}/api/feedback`,
                headers: { 'Content-Type': 'application/json' },
                body: {
                    diagram_id: image_id,
                    block_id: 'block-client',
                    action: 'style',
                    payload: { style: { color: '#00ff00' } },
                },
            }).then((resp) => {
                expect(resp.status).to.eq(200);
                const blocks = resp.body?.ir?.ir?.diagram?.blocks || [];
                const clientBlock = blocks.find((b: any) => b.id === 'block-client');
                expect(clientBlock).to.exist;
                expect(clientBlock.style.color).to.eq('#00ff00');
            });
        });
    });

    // ──────────────────────────────────────────────
    // 6. API-only: hide + show round-trip
    // ──────────────────────────────────────────────
    it('hides and then shows a block via API calls', () => {
        seedDemo().then(({ session_id, image_id }) => {
            // Hide
            cy.request({
                method: 'POST',
                url: `${apiBase()}/api/feedback`,
                headers: { 'Content-Type': 'application/json' },
                body: {
                    diagram_id: image_id,
                    block_id: 'block-api',
                    action: 'hide',
                    payload: {},
                },
            }).then((hideResp) => {
                expect(hideResp.status).to.eq(200);
                const newImageId = hideResp.body.image_id;

                // Show — note: use the NEW image_id returned by hide
                cy.request({
                    method: 'POST',
                    url: `${apiBase()}/api/feedback`,
                    headers: { 'Content-Type': 'application/json' },
                    body: {
                        diagram_id: newImageId,
                        block_id: 'block-api',
                        action: 'show',
                        payload: {},
                    },
                }).then((showResp) => {
                    expect(showResp.status).to.eq(200);
                    const blocks = showResp.body?.ir?.ir?.diagram?.blocks || [];
                    const apiBlock = blocks.find((b: any) => b.id === 'block-api');
                    expect(apiBlock).to.exist;
                    expect(apiBlock.hidden).to.eq(false);
                });
            });
        });
    });
});
