describe('Diagram Render Mode Detection', () => {
  it('detects exactly one rendering mode (INLINE or IMG) and logs it', () => {
    cy.visit('/__test/diagram', {
      onBeforeLoad(win) {
        // enable debug instrumentation
        win.DEBUG_SVG_RENDER = true;
      }
    });

    // Wait for inline diagram container to appear
    cy.get('[data-cy=inline-diagram]', { timeout: 20000 }).should('exist').then(($el) => {
      const hasSvg = $el.find('svg').length > 0;
      const hasImgLike = $el.find('img,object,embed,iframe').length > 0;
      // Assert exactly one mode is true
      expect(hasSvg || hasImgLike).to.equal(true);
      expect(!(hasSvg && hasImgLike)).to.equal(true);
      const mode = hasSvg ? 'INLINE' : 'IMG';
      cy.log('diagramRenderMode:' + mode);
    });
  });
});
