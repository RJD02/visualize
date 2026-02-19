describe('Icon auto-assignment and injection', () => {
  it('injects icons for Postgres, Kafka and MinIO', () => {
    // Force-enable icon injection and debug on page load to avoid UI toggle flakiness
    cy.visit('http://127.0.0.1:5174/__test/diagram', {
      onBeforeLoad(win) {
        win.ENABLE_SVG_ICON_INJECTION = true;
        win.DEBUG_SVG_RENDER = true;
      }
    });
    // Wait for processing; the inline diagram should appear
    cy.get('[data-cy="inline-diagram"]', { timeout: 10000 }).should('exist');

    cy.get('[data-cy="inline-diagram"] svg').then(($svg) => {
      const svg = $svg[0];
      // Assert symbols include expected ids
      cy.wrap(svg).within(() => {
        cy.get('defs').should('exist');
        cy.get('defs symbol#fa_icon_postgres').should('exist');
        cy.get('defs symbol#fa_icon_kafka').should('exist');
        cy.get('defs symbol#fa_icon_minio').should('exist');
      });

      // Assert <use> elements referencing icons exist
      cy.wrap(svg).within(() => {
        cy.get('use[href*="postgres"]').should('exist');
        cy.get('use[href*="kafka"]').should('exist');
        cy.get('use[href*="minio"]').should('exist');
      });
    });
  });
});
