// =====================================================
// SVG ANIMATION DIAGNOSTIC SCRIPT
// Run this in the browser console on localhost:5173
// =====================================================

console.log('=== STEP 1: SVG STRUCTURE CHECK ===');
const svgs = document.querySelectorAll('svg');
console.log(`✓ SVG elements found: ${svgs.length}`);

if (svgs.length === 0) {
    console.error('❌ NO SVG FOUND! Make sure you:');
    console.error('   1. Generated a diagram');
    console.error('   2. Clicked on a diagram to open the modal');
    console.error('   3. Enabled "Inline SVG" checkbox');
    console.error('   4. Enabled "Animation" checkbox');
    console.error('Then run this script again.');
} else {
    const svg = svgs[0];
    console.log(`✓ SVG is inline: ${svg.tagName === 'svg'}`);
    
    const svgStyles = svg.querySelectorAll('style');
    console.log(`✓ <style> tags in SVG: ${svgStyles.length}`);
    
    if (svgStyles.length > 0) {
        const styleContent = svgStyles[0].textContent;
        const hasKeyframes = styleContent.includes('@keyframes');
        const hasAnimationRules = styleContent.includes('animation:');
        console.log(`✓ Has @keyframes: ${hasKeyframes}`);
        console.log(`✓ Has animation rules: ${hasAnimationRules}`);
        
        if (hasKeyframes) {
            const keyframeMatches = styleContent.match(/@keyframes\s+[\w-]+/g) || [];
            console.log(`✓ Total @keyframes rules: ${keyframeMatches.length}`);
            console.log('   First few:', keyframeMatches.slice(0, 3));
        }
    }
    
    console.log('\n=== STEP 2: DOM REALITY CHECK ===');
    const svgGroups = svg.querySelectorAll('g');
    console.log(`✓ SVG <g> elements: ${svgGroups.length}`);
    
    const testSelectors = [
        '#title_text',
        '#node_browser_rect',
        '#node_browser_text',
        '#edge_browser_router_line',
        '#zone_external_rect'
    ];
    
    console.log('\nTesting animation target selectors:');
    testSelectors.forEach(selector => {
        const matches = svg.querySelectorAll(selector);
        const found = matches.length > 0;
        console.log(`${found ? '✓' : '❌'} ${selector}: ${matches.length} match(es)`);
        
        if (found) {
            const computed = window.getComputedStyle(matches[0]);
            const animName = computed.animationName;
            const animDur = computed.animationDuration;
            console.log(`     → animation-name: ${animName === 'none' ? '❌ NONE' : '✓ ' + animName}`);
            console.log(`     → animation-duration: ${animDur === '0s' ? '❌ 0s' : '✓ ' + animDur}`);
        }
    });
    
    console.log('\n=== STEP 3: MOTION PREFERENCES ===');
    const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    console.log(`${prefersReducedMotion ? '⚠️' : '✓'} Prefers reduced motion: ${prefersReducedMotion}`);
    if (prefersReducedMotion) {
        console.warn('⚠️  Your system has "reduced motion" enabled. Animations may be disabled.');
    }
    
    console.log('\n=== STEP 3: FORCE VISUAL CHANGE TEST ===');
    console.log('Attempting to manually modify first <g> element...');
    const firstG = svg.querySelector('g');
    if (firstG) {
        const originalOpacity = window.getComputedStyle(firstG).opacity;
        firstG.style.opacity = '0.2';
        setTimeout(() => {
            console.log(`✓ Changed opacity from ${originalOpacity} to 0.2`);
            console.log('   Look at the diagram - did you see a visual change?');
            console.log('   If NO change visible, the SVG may not be rendering correctly.');
            
            // Restore
            setTimeout(() => {
                firstG.style.opacity = '';
                console.log('✓ Restored original opacity');
            }, 2000);
        }, 100);
    }
    
    console.log('\n=== STEP 4: INJECT TEST ANIMATION ===');
    console.log('Run this command to test if animations CAN work:');
    console.log(`
        const testStyle = document.createElement("style");
        testStyle.id = "diagnostic-animation";
        testStyle.textContent = \`
            svg g rect {
                animation: debugblink 1s infinite alternate !important;
            }
            @keyframes debugblink {
                from { opacity: 1; }
                to { opacity: 0.3; }
            }
        \`;
        document.querySelector("svg").appendChild(testStyle);
        console.log("✓ Test animation injected! All <rect> elements should blink.");
    `);
}

console.log('\n=== DIAGNOSTIC COMPLETE ===');
console.log('Next steps:');
console.log('1. Review the output above');
console.log('2. If animation-name shows "none", the animations are not being applied');
console.log('3. Run the STEP 4 test command to verify animations CAN work');
console.log('4. Check the backend API response for the animated SVG');
