describe('Startup smoke: API + UI', () => {
  it('serves health endpoint and renders UI shell', () => {
    cy.request('/health').then((resp) => {
      expect(resp.status).to.eq(200);
      expect(resp.body).to.have.property('status', 'ok');
    });

    cy.visit('/');
    cy.contains('Architecture Copilot', { timeout: 30000 }).should('be.visible');
    cy.get('[data-cy="chat-input"]', { timeout: 30000 }).should('be.visible');
    cy.get('[data-cy="send-button"]', { timeout: 30000 }).should('be.visible');
  });
});
