const { defineConfig } = require('cypress');

const DEFAULT_BASE_URL = process.env.CYPRESS_BASE_URL || 'http://localhost:5173';

module.exports = defineConfig({
    reporter: 'spec',
    video: false,
    retries: 1,
    e2e: {
        baseUrl: DEFAULT_BASE_URL,
        specPattern: 'cypress/e2e/**/*.cy.ts',
        supportFile: 'cypress/support/e2e.ts',
        defaultCommandTimeout: 60000,
        pageLoadTimeout: 180000,
        requestTimeout: 180000,
        viewportWidth: 1440,
        viewportHeight: 900,
        setupNodeEvents(on) {
            on('task', {
                log(message) {
                    console.log(message);
                    return null;
                },
            });
        },
    },
});
