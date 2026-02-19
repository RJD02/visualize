describe('Icon Injection (INLINE mode only)', () => {
  it('injects icons into node groups for requested nodes', () => {
    cy.visit('/__test/diagram', {
      onBeforeLoad(win) {
        win.DEBUG_SVG_RENDER = true;
        // request a broader set of icon injections
        win.__test_icon_requests = [
          { nodeText: 'Postgres', iconKey: 'postgres' },
          { nodeText: 'Vault', iconKey: 'vault' },
          { nodeText: 'MinIO', iconKey: 'minio' },
          { nodeText: 'Druid', iconKey: 'druid' },
          { nodeText: 'Kafka topics', iconKey: 'kafka' },
          { nodeText: 'Spark', iconKey: 'spark' },
          { nodeText: 'Trino', iconKey: 'trino' }
        ];
        // enable injection feature
        win.ENABLE_SVG_ICON_INJECTION = true;
      }
    });

    cy.get('[data-cy=inline-diagram]', { timeout: 20000 }).should('exist').then(($el) => {
      // ensure inline svg
      cy.wrap($el).find('svg').should('have.length.greaterThan', 0);
      // check that a <use> element was injected for requested icons
      cy.wrap($el).find('use').should('have.length.at.least', 5);
      // assert specific icons present in markup
      cy.wrap($el).find('svg').then(($svg) => {
        const html = $svg.prop('outerHTML');
        expect(html).to.include('fa_icon_postgres');
        expect(html).to.include('fa_icon_vault');
        expect(html).to.include('fa_icon_minio');
        expect(html).to.include('fa_icon_druid');
        expect(html).to.include('fa_icon_kafka');
      });
    });
  });
});
