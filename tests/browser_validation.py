"""Browser-based validation of SVG animations using Playwright.

This script validates that animations work correctly in a real browser environment.
It tests:
1. Animation CSS is properly injected
2. Animations are visible (not too subtle)
3. Animations run continuously (infinite)
4. Reduced motion preference is respected
"""
import asyncio
import subprocess
import sys
import time
from pathlib import Path

# Try to import playwright
try:
    from playwright.async_api import async_playwright
except ImportError:
    print("Playwright not installed. Install with: pip install playwright && playwright install")
    sys.exit(1)


# Test SVG with animations
TEST_SVG = '''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 200">
    <rect id="node1" x="10" y="80" width="100" height="40" fill="#60a5fa"/>
    <text x="60" y="105" text-anchor="middle" fill="white">Start</text>
    
    <rect id="node2" x="150" y="80" width="100" height="40" fill="#60a5fa"/>
    <text x="200" y="105" text-anchor="middle" fill="white">Process</text>
    
    <rect id="node3" x="290" y="80" width="100" height="40" fill="#60a5fa"/>
    <text x="340" y="105" text-anchor="middle" fill="white">End</text>
    
    <line id="edge1" x1="110" y1="100" x2="150" y2="100" stroke="#94a3b8" stroke-width="2"/>
    <line id="edge2" x1="250" y1="100" x2="290" y2="100" stroke="#94a3b8" stroke-width="2"/>
</svg>'''


def create_test_html() -> str:
    """Create test HTML with animated SVG."""
    from src.animation.svg_structural_analyzer import analyze_svg
    from src.animation.animation_plan_schema import (
        AnimationPlanV2,
        AnimationSequence,
        ElementAnimation,
        AnimationType,
        ANIMATION_PRESETS,
    )
    from src.animation.animation_executor import inject_animation
    
    # Analyze and create plan
    graph = analyze_svg(TEST_SVG, "test-svg")
    
    elements = []
    delay = 0.0
    gap = 0.1
    
    for node in graph.nodes:
        preset = ANIMATION_PRESETS["node_pulse"]
        elements.append(ElementAnimation(
            element_id=node.id,
            selector=f"#{node.id}",
            element_type=node.element_type,
            animation_type=preset["animation_type"],
            delay=delay,
            duration=preset["duration"],
            iterations=preset["iterations"],
            direction=preset["direction"],
        ))
        delay += gap
    
    for edge in graph.edges:
        preset = ANIMATION_PRESETS["edge_flow"]
        elements.append(ElementAnimation(
            element_id=edge.id,
            selector=f"#{edge.id}",
            element_type=edge.element_type,
            animation_type=preset["animation_type"],
            delay=delay,
            duration=preset["duration"],
            iterations=preset["iterations"],
            direction=preset["direction"],
        ))
        delay += gap
    
    plan = AnimationPlanV2(
        plan_id="browser-test-plan",
        svg_id="test-svg",
        diagram_type="flowchart",
        description="Browser validation test",
        style="professional",
        sequences=[
            AnimationSequence(
                name="main",
                description="Main sequence",
                elements=elements,
            )
        ],
    )
    
    animated_svg = inject_animation(TEST_SVG, plan, use_js=True)
    
    return f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Animation Browser Test</title>
    <style>
        body {{
            background: #0f172a;
            color: white;
            font-family: sans-serif;
            padding: 20px;
        }}
        .container {{
            background: #1e293b;
            border: 1px solid #334155;
            border-radius: 8px;
            padding: 20px;
            max-width: 600px;
            margin: 0 auto;
        }}
        #test-results {{
            margin-top: 20px;
            padding: 10px;
            background: #0f172a;
            border-radius: 4px;
            font-family: monospace;
            font-size: 12px;
        }}
        .pass {{ color: #34d399; }}
        .fail {{ color: #f87171; }}
    </style>
</head>
<body>
    <h1>SVG Animation Browser Test</h1>
    <div class="container">
        {animated_svg}
    </div>
    <div id="test-results"></div>
    <script>
        const results = document.getElementById('test-results');
        const tests = [];
        
        function log(msg, pass) {{
            tests.push({{ msg, pass }});
            const div = document.createElement('div');
            div.className = pass ? 'pass' : 'fail';
            div.textContent = (pass ? '✓ ' : '✗ ') + msg;
            results.appendChild(div);
        }}
        
        function runTests() {{
            // Test 1: Check animations exist
            const anims = window.__svgAnimations;
            const hasAnimations = anims && anims['test-svg'] && anims['test-svg'].length > 0;
            log('JavaScript animations registered', hasAnimations);
            
            // Test 2: Check CSS animations
            const node1 = document.getElementById('node1');
            const style = window.getComputedStyle(node1);
            const hasAnimation = style.animation && style.animation !== 'none';
            log('CSS animation applied to node1', hasAnimation);
            
            // Test 3: Check animation is infinite
            const isInfinite = style.animationIterationCount === 'infinite';
            log('Animation iteration is infinite', isInfinite);
            
            // Test 4: Check animation duration is reasonable
            const duration = parseFloat(style.animationDuration) || 0;
            const durationOk = duration > 0 && duration < 10;
            log('Animation duration is reasonable (' + duration + 's)', durationOk);
            
            // Test 5: Check for reduced motion media query
            const styleEl = document.querySelector('style');
            const styleText = styleEl ? styleEl.textContent : '';
            const hasReducedMotion = styleText.includes('prefers-reduced-motion');
            log('Reduced motion media query present', hasReducedMotion);
            
            // Summary
            const passed = tests.filter(t => t.pass).length;
            const total = tests.length;
            const summary = document.createElement('div');
            summary.style.marginTop = '10px';
            summary.style.fontWeight = 'bold';
            summary.className = passed === total ? 'pass' : 'fail';
            summary.textContent = `Tests: ${{passed}}/${{total}} passed`;
            summary.id = 'summary';
            results.appendChild(summary);
            
            // Set data attribute for Playwright to read
            document.body.setAttribute('data-tests-passed', passed);
            document.body.setAttribute('data-tests-total', total);
        }}
        
        // Run after animations initialize
        setTimeout(runTests, 500);
    </script>
</body>
</html>'''


async def run_browser_tests():
    """Run browser-based animation validation tests."""
    print("=" * 60)
    print("SVG Animation Browser Validation")
    print("=" * 60)
    
    # Create test HTML
    html_content = create_test_html()
    test_file = Path("/tmp/animation_browser_test.html")
    test_file.write_text(html_content)
    print(f"Created test file: {test_file}")
    
    # Run with Playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        # Load test page
        await page.goto(f"file://{test_file}")
        
        # Wait for tests to complete
        await page.wait_for_selector("#summary", timeout=5000)
        
        # Get results
        passed = await page.evaluate("parseInt(document.body.getAttribute('data-tests-passed'))")
        total = await page.evaluate("parseInt(document.body.getAttribute('data-tests-total'))")
        
        # Get individual test results
        test_elements = await page.query_selector_all("#test-results > div:not(#summary)")
        print("\nTest Results:")
        print("-" * 40)
        for el in test_elements:
            text = await el.inner_text()
            print(text)
        
        print("-" * 40)
        print(f"Summary: {passed}/{total} tests passed")
        
        # Screenshot for debugging
        screenshot_path = Path("/tmp/animation_test_screenshot.png")
        await page.screenshot(path=str(screenshot_path))
        print(f"Screenshot saved: {screenshot_path}")
        
        await browser.close()
        
        return passed == total


async def test_reduced_motion():
    """Test that reduced motion preference disables animations."""
    print("\n" + "=" * 60)
    print("Testing Reduced Motion Preference")
    print("=" * 60)
    
    html_content = create_test_html()
    test_file = Path("/tmp/animation_browser_test.html")
    test_file.write_text(html_content)
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            reduced_motion="reduce"
        )
        page = await context.new_page()
        
        await page.goto(f"file://{test_file}")
        await page.wait_for_timeout(500)
        
        # Check if animations are disabled
        node1 = await page.query_selector("#node1")
        animation = await page.evaluate(
            "getComputedStyle(document.getElementById('node1')).animation"
        )
        
        # With reduced motion, animation should be "none"
        is_disabled = animation == "none" or not animation
        
        print(f"Animation value with reduced motion: {animation}")
        print(f"Animations disabled: {is_disabled}")
        
        await browser.close()
        
        return is_disabled


async def test_animation_visibility():
    """Test that animations have visible changes."""
    print("\n" + "=" * 60)
    print("Testing Animation Visibility")
    print("=" * 60)
    
    html_content = create_test_html()
    test_file = Path("/tmp/animation_browser_test.html")
    test_file.write_text(html_content)
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        await page.goto(f"file://{test_file}")
        
        # Take screenshots at different times to compare
        await page.wait_for_timeout(100)
        screenshot1 = await page.screenshot()
        
        await page.wait_for_timeout(1000)
        screenshot2 = await page.screenshot()
        
        # Screenshots should be different if animation is working
        is_different = screenshot1 != screenshot2
        
        print(f"Animation causes visual changes: {is_different}")
        
        await browser.close()
        
        return is_different


async def main():
    """Run all browser validation tests."""
    print("\n" + "=" * 60)
    print("STARTING BROWSER VALIDATION SUITE")
    print("=" * 60 + "\n")
    
    results = []
    
    # Test 1: Basic functionality
    try:
        result = await run_browser_tests()
        results.append(("Basic Animation Tests", result))
    except Exception as e:
        print(f"Error running basic tests: {e}")
        results.append(("Basic Animation Tests", False))
    
    # Test 2: Reduced motion
    try:
        result = await test_reduced_motion()
        results.append(("Reduced Motion Support", result))
    except Exception as e:
        print(f"Error testing reduced motion: {e}")
        results.append(("Reduced Motion Support", False))
    
    # Test 3: Visual changes
    try:
        result = await test_animation_visibility()
        results.append(("Animation Visibility", result))
    except Exception as e:
        print(f"Error testing visibility: {e}")
        results.append(("Animation Visibility", False))
    
    # Summary
    print("\n" + "=" * 60)
    print("VALIDATION SUMMARY")
    print("=" * 60)
    
    all_passed = True
    for name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"  {status}: {name}")
        if not passed:
            all_passed = False
    
    print("=" * 60)
    if all_passed:
        print("All browser validation tests PASSED!")
        return 0
    else:
        print("Some browser validation tests FAILED!")
        return 1


if __name__ == "__main__":
    # Add project root to path
    import os
    project_root = Path(__file__).parent.parent
    sys.path.insert(0, str(project_root))
    
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
