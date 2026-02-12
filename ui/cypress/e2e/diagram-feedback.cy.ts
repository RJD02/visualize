describe('Diagram feedback loop', () => {
  it('applies edit_text feedback and re-renders diagram', () => {
    const apiBase = Cypress.env('API_BASE_URL') || 'http://localhost:8000';
    const uiBase = Cypress.env('UI_BASE_URL') || 'http://localhost:8000';

    cy.request(`${apiBase}/api/demo/diagram`).then((resp) => {
      const { session_id, image_id } = resp.body;
      cy.visit(`${uiBase}/?session=${session_id}`);

      cy.contains('Image v', { timeout: 15000 }).should('exist');
      cy.contains('View Diagram').click();

      cy.get('.inline-diagram--modal [data-block-id="block-api"]', { timeout: 15000 })
        .click({ force: true });

      cy.get('#feedback-action').select('edit_text');
      cy.get('#feedback-text').clear().type('Auth Service Updated');
      cy.get('#submit-feedback').click();

      cy.contains('Auth Service Updated', { timeout: 15000 }).should('exist');

      cy.request(`${apiBase}/api/ir/${image_id}/history`).then((historyResp) => {
        const history = historyResp.body.history || [];
        expect(history.length).to.be.greaterThan(1);
      });
    });
  });
});
